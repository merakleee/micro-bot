from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import get_settings
from app.errors import AppError
from app.llm.daily_counter import release_daily_request, reserve_daily_request

_MAX_ATTEMPTS = 2


@dataclass(frozen=True, slots=True)
class LLMCompletion:
    """Text and token accounting returned by a successful model call."""

    content: str
    prompt_tokens: int
    completion_tokens: int
    llm_calls: int


def _unavailable() -> AppError:
    return AppError(503, "llm_unavailable", "The language model is unavailable.")


def _validate_messages(
    messages: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    if (
        isinstance(messages, (str, bytes))
        or not isinstance(messages, Sequence)
        or not messages
    ):
        raise AppError(
            422,
            "validation_error",
            "At least one chat message is required.",
        )

    validated: list[dict[str, str]] = []

    for message in messages:
        if not isinstance(message, Mapping):
            raise AppError(
                422,
                "validation_error",
                "Each chat message must be an object.",
            )

        role = message.get("role")
        content = message.get("content")

        if (
            not isinstance(role, str)
            or not role.strip()
            or not isinstance(content, str)
        ):
            raise AppError(
                422,
                "validation_error",
                "Each chat message needs a role and text content.",
            )

        validated.append(
            {
                "role": role,
                "content": content,
            }
        )

    return validated


def _parse_completion(payload: Any, llm_calls: int) -> LLMCompletion:
    if not isinstance(payload, dict):
        raise _unavailable()

    choices = payload.get("choices")
    usage = payload.get("usage")
    if not isinstance(choices, list) or not choices or not isinstance(usage, dict):
        raise _unavailable()

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise _unavailable()
    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise _unavailable()
    content = message.get("content")
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    if not isinstance(content, str) or not content.strip():
        raise _unavailable()
    if not _is_token_count(prompt_tokens) or not _is_token_count(completion_tokens):
        raise _unavailable()

    return LLMCompletion(
        content=content,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        llm_calls=llm_calls,
    )


def _is_token_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def create_chat_completion(
    messages: Sequence[Mapping[str, str]],
    *,
    temperature: float = 0.1,
    max_tokens: int = 300,
    transport: httpx.BaseTransport | None = None,
) -> LLMCompletion:
    request_messages = _validate_messages(messages)
    settings = get_settings()
    api_key = settings.openrouter_api_key.strip()
    model = settings.openrouter_model.strip()
    base_url = settings.openrouter_base_url.rstrip("/")
    if not api_key or not model or not base_url:
        raise _unavailable()

    endpoint = f"{base_url}/chat/completions"
    request_body = {
        "model": model,
        "messages": request_messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(
            timeout=float(settings.llm_timeout_seconds),
            transport=transport,
        ) as client:
            for attempt in range(_MAX_ATTEMPTS):
                reservation = reserve_daily_request()
                try:
                    response = client.post(
                        endpoint, headers=headers, json=request_body)
                except (httpx.HTTPError, ValueError) as exc:
                    release_daily_request(reservation)
                    raise _unavailable() from exc

                if response.status_code == 429:
                    release_daily_request(reservation)
                    if attempt + 1 < _MAX_ATTEMPTS:
                        continue
                    raise AppError(429, "rate_limited",
                                   "The language model rate limit was reached.")

                if 500 <= response.status_code <= 599:
                    release_daily_request(reservation)
                    if attempt + 1 < _MAX_ATTEMPTS:
                        continue
                    raise _unavailable()

                if response.status_code >= 400:
                    release_daily_request(reservation)
                    raise _unavailable()

                try:
                    payload = response.json()
                    completion = _parse_completion(
                        payload, llm_calls=attempt + 1)
                except AppError:
                    release_daily_request(reservation)
                    raise
                except (ValueError, TypeError) as exc:
                    release_daily_request(reservation)
                    raise _unavailable() from exc
                return completion
    except AppError:
        raise
    except httpx.HTTPError as exc:
        raise _unavailable() from exc

    raise _unavailable()
