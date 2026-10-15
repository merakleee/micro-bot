from __future__ import annotations
import json
import sqlite3
from datetime import datetime, timezone

import httpx
import pytest

from app.config import get_settings
from app.errors import AppError
from app.llm.client import create_chat_completion
from app.llm.daily_counter import reserve_daily_request


@pytest.fixture
def llm_client_db(monkeypatch, tmp_path):
    database_path = tmp_path / "client" / "registry.sqlite3"

    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("LLM_DAILY_REQUEST_LIMIT", "3")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "test/model")
    monkeypatch.setenv(
        "OPENROUTER_BASE_URL",
        "https://openrouter.example/api/v1",
    )

    get_settings.cache_clear()

    yield database_path

    get_settings.cache_clear()


def _success_payload(
    content: str = "Hello from the mocked model",
) -> dict:
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": content,
                }
            }
        ],
        "usage": {
            "prompt_tokens": 12,
            "completion_tokens": 7,
            "total_tokens": 19,
        },
    }


def _stored_request_count(database_path) -> int:
    connection = sqlite3.connect(database_path)

    try:
        row = connection.execute(
            """
            SELECT request_count
            FROM llm_daily_usage
            WHERE utc_date = ?
            """,
            (
                datetime.now(timezone.utc)
                .date()
                .isoformat(),
            ),
        ).fetchone()

        return 0 if row is None else row[0]
    finally:
        connection.close()


def test_success_sends_openai_compatible_request_and_reads_usage(
    llm_client_db,
):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            200,
            json=_success_payload(),
            request=request,
        )

    result = create_chat_completion(
        [{"role": "user", "content": "Say hello"}],
        transport=httpx.MockTransport(handler),
    )

    assert result.content == "Hello from the mocked model"
    assert result.prompt_tokens == 12
    assert result.completion_tokens == 7
    assert result.llm_calls == 1

    assert len(seen) == 1
    assert (
        str(seen[0].url)
        == "https://openrouter.example/api/v1/chat/completions"
    )
    assert seen[0].headers["Authorization"] == "Bearer test-key"

    request_body = json.loads(seen[0].content)

    assert request_body == {
        "model": "test/model",
        "messages": [
            {
                "role": "user",
                "content": "Say hello",
            }
        ],
        "temperature": 0.1,
        "max_tokens": 300,
    }

    assert _stored_request_count(llm_client_db) == 1


def test_timeout_returns_llm_unavailable_without_retry(
    llm_client_db,
):
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout(
            "mock timeout",
            request=request,
        )

    with pytest.raises(AppError) as exc_info:
        create_chat_completion(
            [{"role": "user", "content": "Hello"}],
            transport=httpx.MockTransport(handler),
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "llm_unavailable"
    assert len(calls) == 1
    assert _stored_request_count(llm_client_db) == 0


def test_429_retries_once_and_returns_success(
    llm_client_db,
):
    statuses = iter([429, 200])
    calls = []

    def handler(request):
        calls.append(request)
        status = next(statuses)

        if status == 429:
            return httpx.Response(
                status,
                request=request,
            )

        return httpx.Response(
            status,
            json=_success_payload("Recovered"),
            request=request,
        )

    result = create_chat_completion(
        [{"role": "user", "content": "Hello"}],
        transport=httpx.MockTransport(handler),
    )

    assert result.content == "Recovered"
    assert result.llm_calls == 2
    assert len(calls) == 2
    assert _stored_request_count(llm_client_db) == 1


def test_repeated_429_returns_rate_limited_after_one_retry(
    llm_client_db,
):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            429,
            request=request,
        )

    with pytest.raises(AppError) as exc_info:
        create_chat_completion(
            [{"role": "user", "content": "Hello"}],
            transport=httpx.MockTransport(handler),
        )

    assert exc_info.value.status_code == 429
    assert exc_info.value.code == "rate_limited"
    assert len(calls) == 2
    assert _stored_request_count(llm_client_db) == 0


def test_500_retries_once_then_returns_llm_unavailable(
    llm_client_db,
):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            500,
            request=request,
        )

    with pytest.raises(AppError) as exc_info:
        create_chat_completion(
            [{"role": "user", "content": "Hello"}],
            transport=httpx.MockTransport(handler),
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "llm_unavailable"
    assert len(calls) == 2
    assert _stored_request_count(llm_client_db) == 0

    recovered = create_chat_completion(
        [{"role": "user", "content": "Try again"}],
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json=_success_payload(),
                request=request,
            )
        ),
    )

    assert recovered.llm_calls == 1
    assert _stored_request_count(llm_client_db) == 1


def test_5xx_retry_can_recover(
    llm_client_db,
):
    calls = []

    def handler(request):
        calls.append(request)

        if len(calls) == 1:
            return httpx.Response(
                503,
                request=request,
            )

        return httpx.Response(
            200,
            json=_success_payload("Recovered"),
            request=request,
        )

    result = create_chat_completion(
        [{"role": "user", "content": "Hello"}],
        transport=httpx.MockTransport(handler),
    )

    assert result.content == "Recovered"
    assert result.llm_calls == 2
    assert len(calls) == 2
    assert _stored_request_count(llm_client_db) == 1


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {
            "choices": [],
            "usage": {
                "prompt_tokens": 1,
                "completion_tokens": 1,
            },
        },
        {
            "choices": [
                {
                    "message": {
                        "content": "ok",
                    }
                }
            ],
        },
        {
            "choices": [
                {
                    "message": {
                        "content": "   ",
                    }
                }
            ],
            "usage": {
                "prompt_tokens": 1,
                "completion_tokens": 1,
            },
        },
        {
            "choices": [
                {
                    "message": {
                        "content": "ok",
                    }
                }
            ],
            "usage": {
                "prompt_tokens": -1,
                "completion_tokens": 1,
            },
        },
        {
            "choices": [
                {
                    "message": {
                        "content": "ok",
                    }
                }
            ],
            "usage": {
                "prompt_tokens": True,
                "completion_tokens": 1,
            },
        },
    ],
    ids=[
        "not-an-object",
        "empty-object",
        "no-choices",
        "missing-usage",
        "empty-content",
        "negative-usage",
        "boolean-usage",
    ],
)
def test_malformed_success_payload_returns_llm_unavailable(
    llm_client_db,
    payload,
):
    def handler(request):
        return httpx.Response(
            200,
            json=payload,
            request=request,
        )

    with pytest.raises(AppError) as exc_info:
        create_chat_completion(
            [{"role": "user", "content": "Hello"}],
            transport=httpx.MockTransport(handler),
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "llm_unavailable"
    assert _stored_request_count(llm_client_db) == 0


def test_invalid_json_returns_llm_unavailable(
    llm_client_db,
):
    def handler(request):
        return httpx.Response(
            200,
            text="not-json",
            request=request,
        )

    with pytest.raises(AppError) as exc_info:
        create_chat_completion(
            [{"role": "user", "content": "Hello"}],
            transport=httpx.MockTransport(handler),
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "llm_unavailable"
    assert _stored_request_count(llm_client_db) == 0


def test_quota_reached_does_not_send_http_request(
    llm_client_db,
):
    today = datetime.now(timezone.utc)

    for _ in range(3):
        reserve_daily_request(today)

    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200,
            json=_success_payload(),
            request=request,
        )

    with pytest.raises(AppError) as exc_info:
        create_chat_completion(
            [{"role": "user", "content": "Hello"}],
            transport=httpx.MockTransport(handler),
        )

    assert exc_info.value.status_code == 429
    assert exc_info.value.code == "rate_limited"
    assert calls == []
    assert _stored_request_count(llm_client_db) == 3


def test_missing_api_key_returns_clean_error_without_http_request(
    llm_client_db,
    monkeypatch,
):
    monkeypatch.setenv(
        "OPENROUTER_API_KEY",
        " ",
    )
    get_settings.cache_clear()

    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200,
            json=_success_payload(),
            request=request,
        )

    with pytest.raises(AppError) as exc_info:
        create_chat_completion(
            [{"role": "user", "content": "Hello"}],
            transport=httpx.MockTransport(handler),
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "llm_unavailable"
    assert calls == []
    assert not llm_client_db.exists()


@pytest.mark.parametrize(
    "messages",
    [
        [],
        "hello",
        [{"role": "user"}],
    ],
)
def test_invalid_messages_are_rejected_before_network(
    llm_client_db,
    messages,
):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200,
            json=_success_payload(),
            request=request,
        )

    with pytest.raises(AppError) as exc_info:
        create_chat_completion(
            messages,
            transport=httpx.MockTransport(handler),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "validation_error"
    assert calls == []
    assert not llm_client_db.exists()


def test_other_client_error_maps_to_unavailable_without_retry(
    llm_client_db,
):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            401,
            request=request,
        )

    with pytest.raises(AppError) as exc_info:
        create_chat_completion(
            [{"role": "user", "content": "Hello"}],
            transport=httpx.MockTransport(handler),
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "llm_unavailable"
    assert len(calls) == 1
    assert _stored_request_count(llm_client_db) == 0
