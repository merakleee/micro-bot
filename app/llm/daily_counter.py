from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.config import get_settings
from app.errors import AppError


@dataclass(slots=True)
class DailyRequestReservation:
    
    utc_date: str
    released: bool = False


def reserve_daily_request(now: datetime | None = None) -> DailyRequestReservation:
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        raise ValueError("now must be a timezone-aware datetime")

    utc_date = current_time.astimezone(timezone.utc).date().isoformat()
    settings = get_settings()
    database_path = Path(settings.database_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(database_path, timeout=30)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_daily_usage (
                utc_date TEXT PRIMARY KEY,
                request_count INTEGER NOT NULL CHECK (request_count >= 0)
            )
            """
        )
        result = connection.execute(
            """
            INSERT INTO llm_daily_usage (utc_date, request_count)
            VALUES (?, 1)
            ON CONFLICT(utc_date) DO UPDATE
            SET request_count = request_count + 1
            WHERE request_count < ?
            """,
            (utc_date, settings.llm_daily_request_limit),
        )
        if result.rowcount == 0:
            connection.rollback()
            raise AppError(
                429,
                "rate_limited",
                "The daily model request limit has been reached.",
            )
        connection.commit()
        return DailyRequestReservation(utc_date=utc_date)
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.close()


def release_daily_request(reservation: DailyRequestReservation) -> None:
    if reservation.released:
        return

    database_path = Path(get_settings().database_path)
    connection = sqlite3.connect(database_path, timeout=30)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            UPDATE llm_daily_usage
            SET request_count = request_count - 1
            WHERE utc_date = ? AND request_count > 0
            """,
            (reservation.utc_date,),
        )
        connection.commit()
        reservation.released = True
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.close()
