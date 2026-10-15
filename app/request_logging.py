from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any


_access_logger = logging.getLogger("app.access")
_access_logger.setLevel(logging.INFO)
_access_logger.propagate = False

if not any(getattr(handler, "_micro_bot_json_access", False)
           for handler in _access_logger.handlers):
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _handler._micro_bot_json_access = True  # type: ignore[attr-defined]
    _access_logger.addHandler(_handler)


class RequestLoggingMiddleware:
    
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started_at = time.perf_counter()
        request_id = uuid.uuid4().hex
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        state.setdefault("llm_calls", 0)
        state.setdefault("prompt_tokens", 0)
        state.setdefault("completion_tokens", 0)
        state.setdefault("access_level", None)
        state.setdefault("grounded", None)
        status = 500
        logged = False

        def write_log() -> None:
            nonlocal logged
            if logged:
                return
            logged = True
            record = {
                "request_id": request_id,
                "path": scope.get("path", ""),
                "status": status,
                "latency_ms": max(0, int((time.perf_counter() - started_at) * 1000)),
                "llm_calls": state.get("llm_calls", 0),
                "prompt_tokens": state.get("prompt_tokens", 0),
                "completion_tokens": state.get("completion_tokens", 0),
                "access_level": state.get("access_level"),
                "grounded": state.get("grounded"),
            }
            _access_logger.info(json.dumps(record, separators=(",", ":")))

        async def send_with_request_id(message: dict[str, Any]) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message["headers"] = headers
            await send(message)
            if (
                message["type"] == "http.response.body"
                and not message.get("more_body", False)
            ):
                write_log()

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            write_log()
