import pytest
from fastapi.testclient import TestClient
from app.config import get_settings
from app.main import create_app
from types import SimpleNamespace
from app.routes import chat as chat_route


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("MEMBER_TOKEN", "member-secret")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    get_settings.cache_clear()
    app = create_app()

    @app.get("/boom")
    def boom():
        raise RuntimeError("secret internals")

    yield TestClient(app, raise_server_exceptions=False)
    get_settings.cache_clear()


def assert_error(resp, status, code):
    assert resp.status_code == status
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json()["error"]["code"] == code


def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_chat_public_ok(client, mock_chat_pipeline):
    response = client.post(
        "/api/v1/chat",
        json={"message": "How do I join MC?"},
    )

    assert response.status_code == 200

    body = response.json()

    assert body["answer"] == "Test answer"
    assert body["grounded"] is True
    assert body["usage"]["llm_calls"] == 1


def test_chat_message_too_long(client):
    r = client.post("/api/v1/chat", json={"message": "a" * 2001})
    assert_error(r, 422, "validation_error")


def test_chat_empty_message(client):
    r = client.post("/api/v1/chat", json={"message": "   "})
    assert_error(r, 422, "validation_error")


def test_chat_bad_token(client):
    r = client.post("/api/v1/chat", json={"message": "hi"},
                    headers={"Authorization": "Bearer wrong"})
    assert_error(r, 401, "unauthorized")


def test_chat_good_token(client, mock_chat_pipeline):
    response = client.post(
        "/api/v1/chat",
        json={"message": "hi"},
        headers={"Authorization": "Bearer member-secret"},
    )

    assert response.status_code == 200

    body = response.json()

    assert body["answer"] == "Test answer"
    assert body["grounded"] is True
    assert body["usage"]["llm_calls"] == 1


def test_unknown_route_is_json(client):
    assert_error(client.get("/nope"), 404, "not_found")


def test_wrong_method_is_json(client):
    assert_error(client.get("/api/v1/chat"), 405, "method_not_allowed")


def test_unexpected_exception_hides_internals(client):
    r = client.get("/boom")
    assert_error(r, 500, "internal_error")
    assert "secret internals" not in r.text


@pytest.fixture
def mock_chat_pipeline(monkeypatch):
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
        "retrieve",
        lambda *args, **kwargs: SimpleNamespace(
            query="test question",
            results=[],
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
                    "content": "test system prompt",
                },
                {
                    "role": "user",
                    "content": question,
                },
            ],
            included_results=[],
        ),
    )

    monkeypatch.setattr(
        chat_route,
        "create_chat_completion",
        lambda *args, **kwargs: SimpleNamespace(
            content="Test answer",
            prompt_tokens=10,
            completion_tokens=5,
            llm_calls=1,
        ),
    )
