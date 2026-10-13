import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import get_settings
from app.errors import AppError, register_error_handlers
from app.llm.daily_counter import release_daily_request, reserve_daily_request


@pytest.fixture
def daily_counter_db(monkeypatch, tmp_path):
    database_path = tmp_path / "nested" / "registry.sqlite3"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("LLM_DAILY_REQUEST_LIMIT", "3")
    get_settings.cache_clear()
    yield database_path
    get_settings.cache_clear()


def _usage_rows(database_path):
    connection = sqlite3.connect(database_path)
    try:
        return connection.execute(
            "SELECT utc_date, request_count FROM llm_daily_usage ORDER BY utc_date"
        ).fetchall()
    finally:
        connection.close()


def test_creates_database_and_usage_table_automatically(daily_counter_db):
    assert not daily_counter_db.exists()

    reserve_daily_request(datetime(2026, 10, 13, 12, tzinfo=timezone.utc))

    assert daily_counter_db.exists()
    assert _usage_rows(daily_counter_db) == [("2026-10-13", 1)]


def test_allows_exact_limit_then_rejects_without_increasing_count(daily_counter_db):
    today = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)

    for _ in range(3):
        reserve_daily_request(today)

    with pytest.raises(AppError) as exc_info:
        reserve_daily_request(today)

    assert exc_info.value.status_code == 429
    assert exc_info.value.code == "rate_limited"
    assert exc_info.value.message
    assert _usage_rows(daily_counter_db) == [("2026-10-13", 3)]


def test_releasing_failed_reservation_returns_quota_slot_idempotently(daily_counter_db):
    today = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)
    reservation = reserve_daily_request(today)

    release_daily_request(reservation)
    release_daily_request(reservation)

    assert _usage_rows(daily_counter_db) == [("2026-10-13", 0)]
    reserve_daily_request(today)
    assert _usage_rows(daily_counter_db) == [("2026-10-13", 1)]


def test_rejected_reservation_uses_shared_json_error_handler(daily_counter_db):
    today = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)
    for _ in range(3):
        reserve_daily_request(today)

    app = FastAPI()
    register_error_handlers(app)

    @app.post("/reserve")
    def reserve():
        reserve_daily_request(today)
        return {"reserved": True}

    response = TestClient(app).post("/reserve")

    assert response.status_code == 429
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {
        "error": {
            "code": "rate_limited",
            "message": "The daily model request limit has been reached.",
        }
    }


def test_counter_persists_between_reservations_and_connections(daily_counter_db):
    today = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)

    reserve_daily_request(today)
    reserve_daily_request(today)
    reserve_daily_request(today)

    with pytest.raises(AppError):
        reserve_daily_request(today)

    assert _usage_rows(daily_counter_db) == [("2026-10-13", 3)]


def test_new_utc_day_gets_a_separate_quota(daily_counter_db):
    last_second = datetime(2026, 10, 13, 23, 59, 59, tzinfo=timezone.utc)
    next_day = datetime(2026, 10, 14, 0, 0, 0, tzinfo=timezone.utc)

    for _ in range(3):
        reserve_daily_request(last_second)
    with pytest.raises(AppError):
        reserve_daily_request(last_second)

    reserve_daily_request(next_day)

    assert _usage_rows(daily_counter_db) == [
        ("2026-10-13", 3),
        ("2026-10-14", 1),
    ]


def test_uses_utc_date_instead_of_local_calendar_date(daily_counter_db):
    utc_plus_two = timezone(timedelta(hours=2))
    just_after_local_midnight = datetime(2026, 10, 14, 0, 30, tzinfo=utc_plus_two)
    utc_next_day = datetime(2026, 10, 14, 0, 0, tzinfo=timezone.utc)

    for _ in range(3):
        reserve_daily_request(just_after_local_midnight)
    with pytest.raises(AppError):
        reserve_daily_request(just_after_local_midnight)

    reserve_daily_request(utc_next_day)

    assert _usage_rows(daily_counter_db) == [
        ("2026-10-13", 3),
        ("2026-10-14", 1),
    ]


def test_rejects_naive_datetime_without_creating_database(daily_counter_db):
    with pytest.raises(ValueError, match="timezone-aware"):
        reserve_daily_request(datetime(2026, 10, 13, 12))

    assert not daily_counter_db.exists()


def test_concurrent_reservations_never_exceed_limit(daily_counter_db):
    today = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)

    def try_reservation(_):
        try:
            reserve_daily_request(today)
            return "reserved"
        except AppError as exc:
            assert exc.status_code == 429
            assert exc.code == "rate_limited"
            return "limited"

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(try_reservation, range(12)))

    assert results.count("reserved") == 3
    assert results.count("limited") == 9
    assert _usage_rows(daily_counter_db) == [("2026-10-13", 3)]
