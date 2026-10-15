from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.errors import AppError
from app.main import create_app
from app.request_logging import _access_logger
from app.routes import chat as chat_route


@pytest.fixture
def logged_client(monkeypatch: pytest.MonkeyPatch):
    entries: list[str] = []

    class CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            entries.append(record.getMessage())

    handler = CaptureHandler()
    _access_logger.addHandler(handler)
    monkeypatch.setenv("MEMBER_TOKEN", "test-member-secret")
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as client:
            yield client, entries
    finally:
        _access_logger.removeHandler(handler)
        get_settings.cache_clear()


def _log_entry(entries: list[str], response) -> dict:
    assert len(entries) == 1
    entry = json.loads(entries[0])
    assert entry["request_id"] == response.headers["x-request-id"]
    assert entry["status"] == response.status_code
    assert entry["latency_ms"] >= 0
    return entry


def _patch_chat(monkeypatch: pytest.MonkeyPatch, *, completion=None) -> None:
    monkeypatch.setattr(chat_route, "detect_language", lambda _: "en")
    monkeypatch.setattr(chat_route, "get_embedder", lambda: object())
    monkeypatch.setattr(chat_route, "get_vector_store", lambda: object())
    monkeypatch.setattr(
        chat_route,
        "retrieve",
        lambda *args, **kwargs: SimpleNamespace(results=[object()]),
    )
    monkeypatch.setattr(
        chat_route,
        "build_grounded_prompt",
        lambda *args, **kwargs: SimpleNamespace(
            messages=[{"role": "user", "content": "question"}],
            included_results=[],
        ),
    )
    if completion is not None:
        monkeypatch.setattr(chat_route, "create_chat_completion", completion)


def test_successful_chat_log_matches_response_usage_and_hides_auth_token(
    logged_client,
    monkeypatch: pytest.MonkeyPatch,
):
    client, entries = logged_client

    def complete(*args, **kwargs):
        return SimpleNamespace(
            content="Grounded answer.",
            llm_calls=2,
            prompt_tokens=31,
            completion_tokens=12,
        )

    _patch_chat(monkeypatch, completion=complete)
    response = client.post(
        "/api/v1/chat?debug=not-logged",
        json={"message": "question"},
        headers={"Authorization": "Bearer test-member-secret"},
    )

    assert response.status_code == 200
    entry = _log_entry(entries, response)
    usage = response.json()["usage"]
    assert entry["path"] == "/api/v1/chat"
    assert entry["llm_calls"] == usage["llm_calls"] == 2
    assert entry["prompt_tokens"] == usage["prompt_tokens"] == 31
    assert entry["completion_tokens"] == usage["completion_tokens"] == 12
    assert entry["access_level"] == "members"
    assert entry["grounded"] == response.json()["grounded"] is True
    assert "test-member-secret" not in entries[0]
    assert "debug=not-logged" not in entries[0]


def test_refusal_log_matches_zero_usage(
    logged_client,
    monkeypatch: pytest.MonkeyPatch,
):
    client, entries = logged_client
    _patch_chat(monkeypatch)

    def no_context(*args, **kwargs):
        raise AppError(404, "no_relevant_context", "No context.")

    monkeypatch.setattr(chat_route, "retrieve", no_context)
    response = client.post("/api/v1/chat", json={"message": "question"})

    assert response.status_code == 200
    entry = _log_entry(entries, response)
    assert entry["llm_calls"] == response.json()["usage"]["llm_calls"] == 0
    assert entry["prompt_tokens"] == response.json()["usage"]["prompt_tokens"] == 0
    assert (
        entry["completion_tokens"]
        == response.json()["usage"]["completion_tokens"]
        == 0
    )
    assert entry["access_level"] == "public"
    assert entry["grounded"] is response.json()["grounded"] is False


def test_llm_failure_logs_unknown_usage_without_credentials(
    logged_client,
    monkeypatch: pytest.MonkeyPatch,
):
    client, entries = logged_client

    def fail(*args, **kwargs):
        raise AppError(503, "llm_unavailable", "Unavailable.")

    _patch_chat(monkeypatch, completion=fail)
    response = client.post(
        "/api/v1/chat",
        json={"message": "question"},
        headers={"Authorization": "Bearer test-member-secret"},
    )

    assert response.status_code == 503
    entry = _log_entry(entries, response)
    assert entry["llm_calls"] is None
    assert entry["prompt_tokens"] is None
    assert entry["completion_tokens"] is None
    assert entry["access_level"] == "members"
    assert entry["grounded"] is None
    assert "test-member-secret" not in entries[0]


def test_non_chat_error_logs_defaults_and_one_json_line(logged_client):
    client, entries = logged_client

    response = client.get("/missing?secret=query-value")

    assert response.status_code == 404
    entry = _log_entry(entries, response)
    assert entry["path"] == "/missing"
    assert entry["llm_calls"] == 0
    assert entry["prompt_tokens"] == 0
    assert entry["completion_tokens"] == 0
    assert entry["access_level"] is None
    assert entry["grounded"] is None
    assert "query-value" not in entries[0]
