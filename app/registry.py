from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, TypedDict
from uuid import uuid4
from dataclasses import dataclass
from threading import RLock

from app.config import get_settings
from app.errors import AppError


_VISIBILITIES = {"public", "members"}
_STATUSES = {"processing", "ready", "failed"}
_claim_lock = RLock()


@dataclass(frozen=True)
class Claim:
    doc_id: str
    skipped: bool


class DocumentRecord(TypedDict):
    doc_id: str
    title: str
    visibility: str
    status: str
    error: str | None
    content_hash: str
    created_at: str


def _database_path() -> Path:
    return Path(get_settings().database_path)


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _validate_visibility(visibility: str) -> None:
    if visibility not in _VISIBILITIES:
        raise AppError(422, "validation_error",
                       "visibility must be public or members.")


def _validate_status(status: str) -> None:
    if status not in _STATUSES:
        raise AppError(422, "validation_error",
                       "status must be processing, ready or failed.")


@contextmanager
def _connection() -> Iterator[sqlite3.Connection]:
    database_path = _database_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        _ensure_schema(connection)
        yield connection
    finally:
        connection.close()


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            doc_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            visibility TEXT NOT NULL,
            status TEXT NOT NULL,
            error TEXT,
            content_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            CHECK (visibility IN ('public', 'members')),
            CHECK (status IN ('processing', 'ready', 'failed'))
        )
        """
    )

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_documents_content_hash
        ON documents (content_hash)
        """
    )

    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_documents_content_hash
        ON documents (content_hash)
        """
    )

    connection.commit()


def _row_to_document(row: sqlite3.Row) -> DocumentRecord:
    return {
        "doc_id": row["doc_id"],
        "title": row["title"],
        "visibility": row["visibility"],
        "status": row["status"],
        "error": row["error"],
        "content_hash": row["content_hash"],
        "created_at": row["created_at"],
    }


def create_document(
    title: str,
    visibility: str,
    content_hash: str,
    status: str = "processing",
    error: str | None = None,
) -> str:
    _validate_visibility(visibility)
    _validate_status(status)
    doc_id = uuid4().hex
    created_at = _utc_timestamp()

    with _connection() as connection:
        connection.execute(
            """
            INSERT INTO documents (
                doc_id, title, visibility, status, error, content_hash, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (doc_id, title, visibility, status, error, content_hash, created_at),
        )
        connection.commit()

    return doc_id


def get_document(doc_id: str) -> DocumentRecord | None:
    with _connection() as connection:
        row = connection.execute(
            "SELECT doc_id, title, visibility, status, error, content_hash, created_at "
            "FROM documents WHERE doc_id = ?",
            (doc_id,),
        ).fetchone()

    return None if row is None else _row_to_document(row)


def list_documents() -> list[DocumentRecord]:
    # rowid is SQLite's built-in insertion counter: true creation order,
    # even for documents created within the same second.
    with _connection() as connection:
        rows = connection.execute(
            "SELECT doc_id, title, visibility, status, error, content_hash, created_at "
            "FROM documents ORDER BY rowid"
        ).fetchall()

    return [_row_to_document(row) for row in rows]


def delete_document(doc_id: str) -> bool:
    with _connection() as connection:
        result = connection.execute(
            "DELETE FROM documents WHERE doc_id = ?", (doc_id,))
        connection.commit()

    return result.rowcount > 0


def find_document_by_hash(content_hash: str) -> DocumentRecord | None:
    with _connection() as connection:
        row = connection.execute(
            "SELECT doc_id, title, visibility, status, error, content_hash, created_at "
            "FROM documents WHERE content_hash = ? ORDER BY rowid LIMIT 1",
            (content_hash,),
        ).fetchone()

    return None if row is None else _row_to_document(row)


def update_document_status(doc_id: str, status: str, error: str | None = None) -> bool:
    _validate_status(status)
    with _connection() as connection:
        result = connection.execute(
            "UPDATE documents SET status = ?, error = ? WHERE doc_id = ?",
            (status, error, doc_id),
        )
        connection.commit()

    return result.rowcount > 0


def claim_document(
    *,
    title: str,
    visibility: str,
    content_hash: str,
) -> Claim:
    _validate_visibility(visibility)

    with _claim_lock, _connection() as connection:
        connection.execute("BEGIN IMMEDIATE")

        row = connection.execute(
            """
            SELECT doc_id, visibility, status
            FROM documents
            WHERE content_hash = ?
            """,
            (content_hash,),
        ).fetchone()

        if row is not None:
            if row["status"] == "ready":
                if row["visibility"] == visibility:
                    connection.commit()
                    return Claim(
                        doc_id=row["doc_id"],
                        skipped=True,
                    )

                connection.rollback()
                raise ValueError(
                    "The file already exists with a different visibility."
                )

            connection.execute(
                """
                UPDATE documents
                SET title = ?,
                    visibility = ?,
                    status = 'processing',
                    error = NULL
                WHERE doc_id = ?
                """,
                (title, visibility, row["doc_id"]),
            )
            connection.commit()

            return Claim(
                doc_id=row["doc_id"],
                skipped=False,
            )

        doc_id = uuid4().hex

        connection.execute(
            """
            INSERT INTO documents (
                doc_id,
                title,
                visibility,
                status,
                error,
                content_hash,
                created_at
            )
            VALUES (?, ?, ?, 'processing', NULL, ?, ?)
            """,
            (
                doc_id,
                title,
                visibility,
                content_hash,
                _utc_timestamp(),
            ),
        )
        connection.commit()

        return Claim(
            doc_id=doc_id,
            skipped=False,
        )
