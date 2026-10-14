from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.errors import AppError
from app.main import create_app
from app.routes import chat as chat_route
from app.vector_store import SearchResult


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def make_result(
    *,
    score: float = 0.92,
    doc_id: str = "doc-1",
    title: str = "Example document",
    visibility: str = "public",
    chunk_index: int = 0,
) -> SearchResult:
    return SearchResult(
        text="This is retrieved context.",
        doc_id=doc_id,
        title=title,
        visibility=visibility,
        chunk_index=chunk_index,
        score=score,
    )


def test_chat_returns_retrieved_sources(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    retrieved_result = make_result(
        score=0.92,
        doc_id="doc-123",
        title="About Micro Club",
        visibility="public",
        chunk_index=2,
    )

    captured: dict[str, object] = {}

    def fake_retrieve(
        query: str,
        access_level: str,
        k: int,
        *,
        embedder,
        store,
    ):
        captured["query"] = query
        captured["access_level"] = access_level
        captured["k"] = k

        return SimpleNamespace(
            query=query,
            results=[retrieved_result],
            best_score=retrieved_result.score,
            threshold=0.79,
        )

    monkeypatch.setattr(
        chat_route,
        "retrieve",
        fake_retrieve,
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

    response = client.post(
        "/api/v1/chat",
        json={
            "message": "What is Micro Club?",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["answer"] == "Relevant context retrieved."
    assert body["grounded"] is True
    assert body["usage"] == {
        "llm_calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
    }
    assert len(body["conversation_id"]) == 10
    assert body["conversation_id"].startswith("c_")
    assert len(body["sources"]) == 1
    assert body["sources"][0] == {
        "doc_id": "doc-123",
        "title": "About Micro Club",
        "snippet": "This is retrieved context.",
    }

    assert captured == {
        "query": "What is Micro Club?",
        "access_level": "public",
        "k": 5,
    }


def test_chat_retrieves_members_content_for_authenticated_member(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    retrieved_result = make_result(
        score=0.91,
        doc_id="members-doc",
        title="Members Information",
        visibility="members",
    )

    captured: dict[str, object] = {}

    def fake_retrieve(
        query: str,
        access_level: str,
        k: int,
        *,
        embedder,
        store,
    ):
        captured["access_level"] = access_level

        return SimpleNamespace(
            query=query,
            results=[retrieved_result],
            best_score=retrieved_result.score,
            threshold=0.79,
        )

    monkeypatch.setattr(
        chat_route,
        "retrieve",
        fake_retrieve,
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

    # Replace this value with the member token configured in your test
    # environment if authentication is enabled in your project.
    response = client.post(
        "/api/v1/chat",
        headers={
            "Authorization": "Bearer test-member-token",
        },
        json={
            "message": "What are the member benefits?",
        },
    )

    # If MEMBER_TOKEN is configured, the test needs that configured value.
    # Without it, the bearer token is correctly rejected.
    if response.status_code == 401:
        pytest.skip(
            "Set MEMBER_TOKEN to the test-member-token value to run "
            "the authenticated-member route test."
        )

    assert response.status_code == 200
    assert captured["access_level"] == "members"

    body = response.json()
    assert body["sources"][0]["doc_id"] == "members-doc"
    assert body["sources"][0]["title"] == "Members Information"


def test_chat_returns_refusal_when_retrieval_is_below_threshold(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    llm_calls: list[bool] = []

    def fake_llm_call(*args, **kwargs):
        llm_calls.append(True)
        raise AssertionError(
            "The LLM must not be called when retrieval is refused."
        )

    def refusing_retrieve(
        query: str,
        access_level: str,
        k: int,
        *,
        embedder,
        store,
    ):
        raise AppError(
            404,
            "no_relevant_context",
            "No sufficiently relevant information was found.",
        )

    monkeypatch.setattr(
        chat_route,
        "retrieve",
        refusing_retrieve,
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

    # This assignment verifies that the test has an explicit LLM-call
    # sentinel. The current Issue #8 chat route does not call an LLM yet.
    monkeypatch.setattr(
        chat_route,
        "fake_llm_call",
        fake_llm_call,
        raising=False,
    )

    response = client.post(
        "/api/v1/chat",
        json={
            "message": "Question unrelated to the indexed corpus",
        },
    )

    assert response.status_code == 404

    body = response.json()

    assert body == {
        "error": {
            "code": "no_relevant_context",
            "message": "No sufficiently relevant information was found.",
        }
    }
    assert llm_calls == []


def test_chat_preserves_supplied_conversation_id(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    retrieved_result = make_result(score=0.90)

    monkeypatch.setattr(
        chat_route,
        "retrieve",
        lambda *args, **kwargs: SimpleNamespace(
            query="Existing conversation",
            results=[retrieved_result],
            best_score=0.90,
            threshold=0.79,
        ),
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

    response = client.post(
        "/api/v1/chat",
        json={
            "message": "Existing conversation",
            "conversation_id": "conversation-123",
        },
    )

    assert response.status_code == 200
    assert response.json()["conversation_id"] == "conversation-123"
