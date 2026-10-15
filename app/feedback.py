from __future__ import annotations

import sqlite3
from pathlib import Path

from app.config import get_settings
from app.errors import AppError

_MAX_COMMENT_LENGTH = 1000
_RATINGS = {"up", "down"}


def create_feedback(
    *,
    conversation_id: str,
    rating: str,
    comment: str | None,
) -> int:
    if not isinstance(conversation_id, str) or not conversation_id.strip():
        raise AppError(
            422,
            "validation_error",
            "conversation_id must be a non-empty string.",
        )
    if not isinstance(rating, str) or rating not in _RATINGS:
        raise AppError(422, "validation_error", "rating must be 'up' or 'down'.")
    if comment is not None and (
        not isinstance(comment, str) or len(comment) > _MAX_COMMENT_LENGTH
    ):
        raise AppError(
            422,
            "validation_error",
            f"comment must be at most {_MAX_COMMENT_LENGTH} characters.",
        )

    database_path = Path(get_settings().database_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)

    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(database_path)
        with connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback (
                    feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    rating TEXT NOT NULL CHECK (rating IN ('up', 'down')),
                    comment TEXT CHECK (
                        comment IS NULL OR length(comment) <= 1000
                    )
                )
                """
            )
            cursor = connection.execute(
                """
                INSERT INTO feedback (conversation_id, rating, comment)
                VALUES (?, ?, ?)
                """,
                (conversation_id, rating, comment),
            )
            return int(cursor.lastrowid)
    except sqlite3.Error as exc:
        raise AppError(
            503,
            "feedback_unavailable",
            "Feedback could not be saved right now.",
        ) from exc
    finally:
        if connection is not None:
            connection.close()
