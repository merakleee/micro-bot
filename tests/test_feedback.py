from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app


@pytest.fixture
def feedback_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    database_path = tmp_path / "feedback" / "registry.sqlite3"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        yield client, database_path
    get_settings.cache_clear()


def _feedback_rows(database_path: Path):
    with sqlite3.connect(database_path) as connection:
        return connection.execute(
            """
            SELECT feedback_id, conversation_id, rating, comment
            FROM feedback ORDER BY feedback_id
            """
        ).fetchall()


@pytest.mark.parametrize("rating", ["up", "down"])
def test_feedback_persists_rating_and_optional_comment(
    feedback_client,
    rating: str,
):
    client, database_path = feedback_client

    response = client.post(
        "/api/v1/feedback",
        json={
            "conversation_id": "c_123",
            "rating": rating,
            "comment": "Helpful response",
        },
    )

    assert response.status_code == 201
    assert response.json() == {"feedback_id": 1}
    assert _feedback_rows(database_path) == [
        (1, "c_123", rating, "Helpful response")
    ]


def test_feedback_allows_missing_comment(feedback_client):
    client, database_path = feedback_client

    response = client.post(
        "/api/v1/feedback",
        json={"conversation_id": "c_456", "rating": "up"},
    )

    assert response.status_code == 201
    assert response.json() == {"feedback_id": 1}
    assert _feedback_rows(database_path) == [(1, "c_456", "up", None)]


@pytest.mark.parametrize("rating", ["neutral", "UP", "", None])
def test_feedback_rejects_invalid_rating(feedback_client, rating):
    client, database_path = feedback_client

    response = client.post(
        "/api/v1/feedback",
        json={"conversation_id": "c_123", "rating": rating},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert not database_path.exists()


def test_feedback_rejects_empty_conversation_id(feedback_client):
    client, database_path = feedback_client

    response = client.post(
        "/api/v1/feedback",
        json={"conversation_id": "   ", "rating": "up"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert not database_path.exists()


def test_feedback_accepts_comment_at_limit(feedback_client):
    client, database_path = feedback_client
    comment = "x" * 1000

    response = client.post(
        "/api/v1/feedback",
        json={"conversation_id": "c_123", "rating": "down", "comment": comment},
    )

    assert response.status_code == 201
    assert _feedback_rows(database_path) == [(1, "c_123", "down", comment)]


def test_feedback_rejects_comment_over_limit(feedback_client):
    client, database_path = feedback_client

    response = client.post(
        "/api/v1/feedback",
        json={
            "conversation_id": "c_123",
            "rating": "down",
            "comment": "x" * 1001,
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert not database_path.exists()
