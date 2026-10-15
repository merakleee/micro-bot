from __future__ import annotations

from collections.abc import Generator
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.errors import AppError
from app.main import create_app
from app.routes import chat as chat_route


ADMIN_HEADERS = {
    "X-Admin-Key": "test-admin-key",
}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    monkeypatch.setenv("MEMBER_TOKEN", "member-secret")
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "10485760")

    get_settings.cache_clear()

    application = create_app()

    with TestClient(
        application,
        raise_server_exceptions=False,
    ) as test_client:
        yield test_client

    get_settings.cache_clear()


def assert_json_error(
    response,
    expected_status: int | None = None,
    expected_code: str | None = None,
) -> None:
    if expected_status is not None:
        assert response.status_code == expected_status
    else:
        assert response.status_code < 500

    content_type = response.headers.get("content-type", "")
    assert content_type.startswith("application/json")

    payload = response.json()

    assert isinstance(payload, dict)
    assert "error" in payload
    assert isinstance(payload["error"], dict)
    assert "code" in payload["error"]
    assert "message" in payload["error"]

    if expected_code is not None:
        assert payload["error"]["code"] == expected_code

    body = response.text.lower()

    assert "<html" not in body
    assert "traceback" not in body


def patch_successful_retrieval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retrieved_result = SimpleNamespace(
        text="MicroClub is a student science club.",
        doc_id="doc-1",
        title="About",
        visibility="public",
        chunk_index=0,
        score=0.95,
    )

    monkeypatch.setattr(
        chat_route,
        "get_embedder",
        lambda: object(),
    )

    monkeypatch.setattr(
        chat_route,
        "get_vector_store",
        lambda: object(),
    )

    monkeypatch.setattr(
        chat_route,
        "detect_language",
        lambda text: "en",
    )

    monkeypatch.setattr(
        chat_route,
        "retrieve",
        lambda *args, **kwargs: SimpleNamespace(
            query="What is MicroClub?",
            results=[retrieved_result],
            best_score=0.95,
            threshold=0.79,
        ),
    )

    monkeypatch.setattr(
        chat_route,
        "build_grounded_prompt",
        lambda chunks, question, language: SimpleNamespace(
            messages=[
                {
                    "role": "system",
                    "content": "Answer from the context.",
                },
                {
                    "role": "user",
                    "content": question,
                },
            ],
            included_results=chunks,
        ),
    )


def test_empty_bearer_token_rejected(client: TestClient):
    response = client.get(
        "/api/v1/documents",
        headers={
            "Authorization": "Bearer ",
        },
    )

    assert_json_error(
        response,
        expected_status=401,
        expected_code="unauthorized",
    )


@pytest.mark.parametrize(
    "authorization",
    [
        "Bearer",
        "Bearer ",
        "bearer ",
        "Basic abc",
        "invalid-token",
    ],
)
def test_malformed_bearer_tokens_rejected(
    client: TestClient,
    authorization: str,
):
    response = client.get(
        "/api/v1/documents",
        headers={
            "Authorization": authorization,
        },
    )

    assert_json_error(
        response,
        expected_status=401,
        expected_code="unauthorized",
    )


def test_invalid_json_returns_json_error(client: TestClient):
    response = client.post(
        "/api/v1/chat",
        content=b'{"message": ',
        headers={
            "Content-Type": "application/json",
        },
    )

    assert_json_error(response)


def test_invalid_chat_shape_returns_json_error(client: TestClient):
    response = client.post(
        "/api/v1/chat",
        json={
            "unexpected": "field",
        },
    )

    assert_json_error(response)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"message": ""},
        {"message": "   "},
        {"message": 123},
        {"message": None},
        {"message": "a" * 2001},
    ],
)
def test_invalid_chat_payload_returns_json_error(
    client: TestClient,
    payload: dict,
):
    response = client.post(
        "/api/v1/chat",
        json=payload,
    )

    assert_json_error(response)


def test_wrong_content_type_returns_json_error(client: TestClient):
    response = client.post(
        "/api/v1/chat",
        content=b'{"message": "hello"}',
        headers={
            "Content-Type": "text/plain",
        },
    )

    assert_json_error(response)


def test_form_data_returns_json_error(client: TestClient):
    response = client.post(
        "/api/v1/chat",
        data={
            "message": "hello",
        },
    )

    assert_json_error(response)


def test_llm_unavailable_returns_json_error(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    patch_successful_retrieval(monkeypatch)

    monkeypatch.setattr(
        chat_route,
        "create_chat_completion",
        lambda *args, **kwargs: (
            _raise_app_error(
                503,
                "llm_unavailable",
                "The language model is unavailable.",
            )
        ),
    )

    response = client.post(
        "/api/v1/chat",
        json={
            "message": "What is MicroClub?",
        },
    )

    assert_json_error(
        response,
        expected_status=503,
        expected_code="llm_unavailable",
    )


def test_upstream_rate_limit_returns_json_error(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    patch_successful_retrieval(monkeypatch)

    monkeypatch.setattr(
        chat_route,
        "create_chat_completion",
        lambda *args, **kwargs: (
            _raise_app_error(
                429,
                "rate_limited",
                "The language model is rate limited.",
            )
        ),
    )

    response = client.post(
        "/api/v1/chat",
        json={
            "message": "What is MicroClub?",
        },
    )

    assert_json_error(
        response,
        expected_status=429,
        expected_code="rate_limited",
    )


def test_unexpected_chat_exception_returns_json_error(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        chat_route,
        "retrieve",
        lambda *args, **kwargs: (
            _raise_runtime_error("synthetic retrieval failure")
        ),
    )

    response = client.post(
        "/api/v1/chat",
        json={
            "message": "What is MicroClub?",
        },
    )

    assert_json_error(
        response,
        expected_status=500,
        expected_code="internal_error",
    )

    assert "synthetic retrieval failure" not in response.text


def test_upload_without_file_returns_json_error(
    client: TestClient,
):
    response = client.post(
        "/api/v1/documents",
        headers=ADMIN_HEADERS,
        data={
            "visibility": "public",
        },
    )

    assert_json_error(response)


def test_upload_with_missing_visibility_returns_json_error(
    client: TestClient,
):
    response = client.post(
        "/api/v1/documents",
        headers=ADMIN_HEADERS,
        files={
            "file": (
                "club.md",
                b"# MicroClub\n\nWelcome.",
                "text/markdown",
            ),
        },
    )

    assert_json_error(response)


def test_invalid_visibility_returns_json_error(
    client: TestClient,
):
    response = client.post(
        "/api/v1/documents",
        headers=ADMIN_HEADERS,
        data={
            "visibility": "everyone",
        },
        files={
            "file": (
                "club.md",
                b"# MicroClub\n\nWelcome.",
                "text/markdown",
            ),
        },
    )

    assert_json_error(
        response,
        expected_status=422,
        expected_code="validation_error",
    )


def test_unsupported_upload_returns_json_error(
    client: TestClient,
):
    response = client.post(
        "/api/v1/documents",
        headers=ADMIN_HEADERS,
        data={
            "visibility": "public",
        },
        files={
            "file": (
                "payload.exe",
                b"not a supported document",
                "application/octet-stream",
            ),
        },
    )

    assert_json_error(
        response,
        expected_status=415,
        expected_code="unsupported_file_type",
    )


def test_binary_upload_returns_json_error(
    client: TestClient,
):
    binary_content = bytes(range(256)) * 100

    response = client.post(
        "/api/v1/documents",
        headers=ADMIN_HEADERS,
        data={
            "visibility": "public",
        },
        files={
            "file": (
                "broken.txt",
                binary_content,
                "text/plain",
            ),
        },
    )

    assert_json_error(response)


def test_large_upload_returns_json_error(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "4")
    get_settings.cache_clear()

    response = client.post(
        "/api/v1/documents",
        headers=ADMIN_HEADERS,
        data={
            "visibility": "public",
        },
        files={
            "file": (
                "large.md",
                b"more than four bytes",
                "text/markdown",
            ),
        },
    )

    assert_json_error(
        response,
        expected_status=413,
        expected_code="file_too_large",
    )

    get_settings.cache_clear()


def test_missing_admin_key_returns_json_error(
    client: TestClient,
):
    response = client.post(
        "/api/v1/documents",
        data={
            "visibility": "public",
        },
        files={
            "file": (
                "club.md",
                b"# MicroClub",
                "text/markdown",
            ),
        },
    )

    assert_json_error(
        response,
        expected_status=401,
        expected_code="unauthorized",
    )


def test_invalid_admin_key_returns_json_error(
    client: TestClient,
):
    response = client.post(
        "/api/v1/documents",
        headers={
            "X-Admin-Key": "wrong-admin-key",
        },
        data={
            "visibility": "public",
        },
        files={
            "file": (
                "club.md",
                b"# MicroClub",
                "text/markdown",
            ),
        },
    )

    assert_json_error(
        response,
        expected_status=401,
        expected_code="unauthorized",
    )


def test_unknown_route_returns_json_error(
    client: TestClient,
):
    response = client.get("/api/v1/does-not-exist")

    assert_json_error(
        response,
        expected_status=404,
        expected_code="not_found",
    )


def test_wrong_method_returns_json_error(
    client: TestClient,
):
    response = client.get("/api/v1/chat")

    assert_json_error(
        response,
        expected_status=405,
        expected_code="method_not_allowed",
    )


def _raise_app_error(
    status_code: int,
    code: str,
    message: str,
):
    raise AppError(status_code, code, message)


def _raise_runtime_error(message: str):
    raise RuntimeError(message)
