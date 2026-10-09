import secrets
from typing import Literal
from fastapi import Depends, Header
from app.config import Settings, get_settings
from app.errors import AppError


def _matches(given: str, expected: str) -> bool:
    # An unset secret must never match, even against an empty header.
    if not expected or not given:
        return False
    return secrets.compare_digest(given.encode(), expected.encode())


def get_access_level(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> Literal["public", "members"]:
    if authorization is None:
        return "public"
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not _matches(token.strip(), settings.member_token):
        raise AppError(401, "unauthorized",
                       "Invalid or malformed bearer token.")
    return "members"


def require_admin(
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
    settings: Settings = Depends(get_settings),
) -> None:
    if not _matches(x_admin_key or "", settings.admin_api_key):
        raise AppError(401, "unauthorized", "Missing or invalid admin key.")
