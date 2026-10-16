import secrets
from typing import Literal
from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.config import Settings, get_settings
from app.errors import AppError


_bearer_scheme = HTTPBearer(auto_error=False)


def _matches(given: str, expected: str) -> bool:
    # An unset secret must never match, even against an empty header.
    if not expected or not given:
        return False
    return secrets.compare_digest(given.encode(), expected.encode())


def get_access_level(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> Literal["public", "members"]:
    if credentials is None:
        return "public"
    if not _matches(credentials.credentials.strip(), settings.member_token):
        raise AppError(401, "unauthorized",
                       "Invalid or malformed bearer token.")
    return "members"


def require_admin(
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
    settings: Settings = Depends(get_settings),
) -> None:
    if not _matches(x_admin_key or "", settings.admin_api_key):
        raise AppError(401, "unauthorized", "Missing or invalid admin key.")
