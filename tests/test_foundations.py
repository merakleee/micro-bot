import pytest
from fastapi.testclient import TestClient
from app.config import get_settings
from app.main import create_app


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


def test_chat_public_ok(client):
    r = client.post("/api/v1/chat", json={"message": "How do I join MC?"})
    assert r.status_code == 200
    assert r.json()["conversation_id"].startswith("c_")


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


def test_chat_good_token(client):
    r = client.post("/api/v1/chat", json={"message": "hi"},
                    headers={"Authorization": "Bearer member-secret"})
    assert r.status_code == 200


def test_unknown_route_is_json(client):
    assert_error(client.get("/nope"), 404, "not_found")


def test_wrong_method_is_json(client):
    assert_error(client.get("/api/v1/chat"), 405, "method_not_allowed")


def test_unexpected_exception_hides_internals(client):
    r = client.get("/boom")
    assert_error(r, 500, "internal_error")
    assert "secret internals" not in r.text
