from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.errors import AppError
from app.main import create_app
from app.routes import chat as chat_route
from app.vector_store import SearchResult
from app.conversation_memory import conversation_memory


@pytest.fixture(autouse=True)
def clear_conversation_memory():
    conversation_memory._conversations.clear()
    yield
    conversation_memory._conversations.clear()


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


def fake_completion(*args, **kwargs):
    return SimpleNamespace(
        content="MicroClub information retrieved.",
        prompt_tokens=10,
        completion_tokens=5,
        llm_calls=1,
    )


def patch_chat_dependencies(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        chat_route,
        "get_vector_store",
        lambda: object(),
    )
    monkeypatch.setattr(
        chat_route,
        "create_chat_completion",
        fake_completion,
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
    patch_chat_dependencies(monkeypatch)

    response = client.post(
        "/api/v1/chat",
        json={
            "message": "What is Micro Club?",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["answer"] == "MicroClub information retrieved."
    assert body["grounded"] is True
    assert body["usage"] == {
        "llm_calls": 1,
        "prompt_tokens": 10,
        "completion_tokens": 5,
    }
    assert len(body["conversation_id"]) == 10
    assert body["conversation_id"].startswith("c_")

    assert body["sources"] == [
        {
            "doc_id": "doc-123",
            "title": "About Micro Club",
            "snippet": "This is retrieved context.",
        }
    ]

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
    patch_chat_dependencies(monkeypatch)

    response = client.post(
        "/api/v1/chat",
        headers={
            "Authorization": "Bearer test-member-token",
        },
        json={
            "message": "What are the member benefits?",
        },
    )

    if response.status_code == 401:
        pytest.skip(
            "Set MEMBER_TOKEN=test-member-token to run the "
            "authenticated-member route test."
        )

    assert response.status_code == 200
    assert captured["access_level"] == "members"

    body = response.json()

    assert body["sources"] == [
        {
            "doc_id": "members-doc",
            "title": "Members Information",
            "snippet": "This is retrieved context.",
        }
    ]


def test_chat_returns_refusal_when_retrieval_is_below_threshold(
    client,
    monkeypatch,
):
    llm_calls: list[bool] = []

    def fail_if_called(*args, **kwargs):
        llm_calls.append(True)
        raise AssertionError(
            "The LLM must not be called when retrieval is refused."
        )

    def refusing_retrieve(*args, **kwargs):
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
    monkeypatch.setattr(
        chat_route,
        "create_chat_completion",
        fail_if_called,
    )
    monkeypatch.setattr(
        chat_route,
        "detect_language",
        lambda text: "en",
    )

    response = client.post(
        "/api/v1/chat",
        json={
            "message": "Question unrelated to the indexed corpus",
        },
    )

    assert response.status_code == 200
    assert response.json()["grounded"] is False
    assert response.json()["sources"] == []
    assert response.json()["usage"] == {
        "llm_calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
    }
    assert response.json()["answer"] == (
        "I don't know based on the available information."
    )
    assert response.json()["conversation_id"].startswith("c_")
    assert isinstance(response.json()["latency_ms"], int)
    assert response.json()["latency_ms"] >= 0
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
    patch_chat_dependencies(monkeypatch)

    response = client.post(
        "/api/v1/chat",
        json={
            "message": "Existing conversation",
            "conversation_id": "conversation-123",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["conversation_id"] == "conversation-123"
    assert body["answer"] == "MicroClub information retrieved."
    assert body["grounded"] is True
    assert body["usage"]["llm_calls"] == 1


def test_chat_passes_detected_language_to_prompt(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, object] = {}
    retrieved_result = make_result(score=0.91)

    monkeypatch.setattr(
        chat_route,
        "detect_language",
        lambda text: "fr",
    )

    monkeypatch.setattr(
        chat_route,
        "retrieve",
        lambda *args, **kwargs: SimpleNamespace(
            query="Que fait le club ?",
            results=[retrieved_result],
            best_score=0.91,
            threshold=0.79,
        ),
    )

    def fake_prompt_builder(
        chunks,
        question,
        language,
    ):
        captured["language"] = language

        return SimpleNamespace(
            messages=[
                {
                    "role": "system",
                    "content": "Répondez en français.",
                },
                {
                    "role": "user",
                    "content": "context",
                },
            ],
            included_results=chunks,
        )

    monkeypatch.setattr(
        chat_route,
        "build_grounded_prompt",
        fake_prompt_builder,
    )

    def fake_french_completion(*args, **kwargs):
        captured["messages"] = args[0]
        captured["temperature"] = kwargs["temperature"]
        captured["max_tokens"] = kwargs["max_tokens"]

        return SimpleNamespace(
            content="Le club organise des événements.",
            prompt_tokens=10,
            completion_tokens=8,
            llm_calls=1,
        )

    monkeypatch.setattr(
        chat_route,
        "create_chat_completion",
        fake_french_completion,
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
            "message": "Que fait le club ?",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["answer"] == "Le club organise des événements."
    assert body["grounded"] is True
    assert captured["language"] == "fr"
    assert captured["temperature"] == 0.1
    assert captured["max_tokens"] == 300
    assert captured["messages"][0]["content"] == (
        "Répondez en français."
    )


def test_chat_returns_clean_error_when_llm_fails(
    client,
    monkeypatch,
):
    retrieved_result = make_result(score=0.92)

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
            best_score=0.92,
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

    def failing_completion(*args, **kwargs):
        raise AppError(
            503,
            "llm_unavailable",
            "The language model is unavailable.",
        )

    monkeypatch.setattr(
        chat_route,
        "create_chat_completion",
        failing_completion,
    )

    response = client.post(
        "/api/v1/chat",
        json={
            "message": "What is MicroClub?",
        },
    )

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "llm_unavailable",
            "message": "The language model is unavailable.",
        }
    }

    def test_chat_follow_up_uses_previous_question_for_retrieval(
        client,
        monkeypatch,
    ):
        conversation_id = "conversation-follow-up"
        queries = []

        retrieved_result = make_result(
            score=0.92,
            title="Events",
            doc_id="events-doc",
        )

        def fake_retrieve(
            query,
            access_level,
            k,
            *,
            embedder,
            store,
        ):
            queries.append(query)

            return SimpleNamespace(
                query=query,
                results=[retrieved_result],
                best_score=0.92,
                threshold=0.79,
            )

        monkeypatch.setattr(
            chat_route,
            "retrieve",
            fake_retrieve,
        )
        patch_chat_dependencies(monkeypatch)

        first_response = client.post(
            "/api/v1/chat",
            json={
                "conversation_id": conversation_id,
                "message": "What events does MicroClub organize?",
            },
        )

        second_response = client.post(
            "/api/v1/chat",
            json={
                "conversation_id": conversation_id,
                "message": "Where are they held?",
            },
        )

        assert first_response.status_code == 200
        assert second_response.status_code == 200
        assert len(queries) == 2

        assert queries[0] == (
            "What events does MicroClub organize?"
        )
        assert queries[1] == (
            "What events does MicroClub organize? "
            "Where are they held?"
        )

    def test_public_reusing_members_conversation_does_not_reuse_members_context(
        client,
        monkeypatch,
    ):
        conversation_id = "conversation-access-change"
        calls = []

        members_result = make_result(
            score=0.95,
            doc_id="members-doc",
            title="Members",
            visibility="members",
        )
        public_result = make_result(
            score=0.90,
            doc_id="public-doc",
            title="Public",
            visibility="public",
        )

        def fake_retrieve(
            query,
            access_level,
            k,
            *,
            embedder,
            store,
        ):
            calls.append(
                {
                    "query": query,
                    "access_level": access_level,
                }
            )

            result = (
                members_result
                if access_level == "members"
                else public_result
            )

            return SimpleNamespace(
                query=query,
                results=[result],
                best_score=0.95,
                threshold=0.79,
            )

        monkeypatch.setattr(
            chat_route,
            "retrieve",
            fake_retrieve,
        )
        patch_chat_dependencies(monkeypatch)

        members_response = client.post(
            "/api/v1/chat",
            headers={
                "Authorization": "Bearer member-secret",
            },
            json={
                "conversation_id": conversation_id,
                "message": "What are the member benefits?",
            },
        )

        if members_response.status_code == 401:
            pytest.skip(
                "Set MEMBER_TOKEN=member-secret to run this test."
            )

        public_response = client.post(
            "/api/v1/chat",
            json={
                "conversation_id": conversation_id,
                "message": "Tell me more.",
            },
        )

        assert members_response.status_code == 200
        assert public_response.status_code == 200
        assert len(calls) == 2

        assert calls[0]["access_level"] == "members"
        assert calls[1]["access_level"] == "public"

        assert calls[0]["query"] == (
            "What are the member benefits?"
        )

        assert calls[1]["query"] == "Tell me more."
        assert "member benefits" not in calls[1]["query"]

        public_body = public_response.json()

        assert public_body["sources"] == [
            {
                "doc_id": "public-doc",
                "title": "Public",
                "snippet": "This is retrieved context.",
            }
        ]
        assert all(
            source["doc_id"] != "members-doc"
            for source in public_body["sources"]
        )
