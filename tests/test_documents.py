from __future__ import annotations

from pathlib import Path
from typing import Sequence

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from app.config import get_settings
from app.main import create_app
from app.routes import documents
from app.vector_store import QdrantVectorStore


ADMIN_HEADERS = {"X-Admin-Key": "test-admin-key"}


class FakeEmbedder:
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0]


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "registry.sqlite3"))
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "10485760")
    get_settings.cache_clear()
    test_store = QdrantVectorStore(client=QdrantClient(location=":memory:"))
    monkeypatch.setattr(documents, "get_embedder", FakeEmbedder)
    monkeypatch.setattr(documents, "get_vector_store", lambda: test_store)
    with TestClient(create_app()) as test_client:
        yield test_client, test_store
    test_store.close()
    get_settings.cache_clear()


def upload(client: TestClient, *, filename="club.md", content=b"# Club\n\nWelcome.", visibility="public"):
    return client.post(
        "/api/v1/documents",
        headers=ADMIN_HEADERS,
        data={"visibility": visibility},
        files={"file": (filename, content, "application/octet-stream")},
    )


@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        ("get", "/api/v1/documents", {}),
        ("post", "/api/v1/documents", {
            "data": {"visibility": "public"},
            "files": {"file": ("club.md", b"# Club", "text/markdown")},
        }),
        ("delete", "/api/v1/documents/unknown", {}),
    ],
)
def test_all_document_operations_require_admin(client, method, path, kwargs):
    test_client, _ = client

    response = getattr(test_client, method)(path, **kwargs)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_upload_rejects_invalid_visibility(client):
    test_client, _ = client

    response = upload(test_client, visibility="secret")

    assert response.status_code == 422
    assert response.json()["error"] == {
        "code": "validation_error",
        "message": "visibility must be public or members.",
    }


def test_upload_rejects_unsupported_file_type(client):
    test_client, _ = client

    response = upload(test_client, filename="club.txt")

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_file_type"


def test_upload_rejects_file_over_configured_size(client, monkeypatch):
    test_client, _ = client
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "4")
    get_settings.cache_clear()

    response = upload(test_client, content=b"more than four bytes")

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "file_too_large"


def test_get_lists_uploaded_documents(client):
    test_client, _ = client
    created = upload(test_client)
    assert created.status_code == 201

    response = test_client.get("/api/v1/documents", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["doc_id"] == created.json()["doc_id"]
    assert response.json()[0]["visibility"] == "public"
    assert response.json()[0]["status"] == "ready"
    assert "content_hash" not in response.json()[0]


def test_delete_unknown_document_returns_404(client):
    test_client, _ = client

    response = test_client.delete(
        "/api/v1/documents/unknown",
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_delete_then_search_returns_no_document_chunks(client):
    test_client, store = client
    created = upload(test_client)
    doc_id = created.json()["doc_id"]
    before = store.search([1.0, 0.0], access_level="public")
    assert any(result.doc_id == doc_id for result in before)

    response = test_client.delete(
        f"/api/v1/documents/{doc_id}",
        headers=ADMIN_HEADERS,
    )

    after = store.search([1.0, 0.0], access_level="public")
    assert response.status_code == 200
    assert response.json() == {"doc_id": doc_id, "deleted": True}
    assert all(result.doc_id != doc_id for result in after)
