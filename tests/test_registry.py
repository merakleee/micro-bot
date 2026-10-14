import sqlite3

import pytest

from app import registry
from app.config import get_settings
from app.errors import AppError


@pytest.fixture
def isolated_registry(monkeypatch, tmp_path):
    """Point the registry at a throwaway database and yield its path."""
    path = tmp_path / "registry.sqlite3"
    monkeypatch.setenv("DATABASE_PATH", str(path))
    get_settings.cache_clear()
    yield path
    get_settings.cache_clear()


def test_create_then_get_returns_same_data(isolated_registry):
    doc_id = registry.create_document("Alpha", "public", "hash-1")

    document = registry.get_document(doc_id)

    assert document is not None
    assert document["doc_id"] == doc_id
    assert document["title"] == "Alpha"
    assert document["visibility"] == "public"
    assert document["status"] == "processing"
    assert document["error"] is None
    assert document["content_hash"] == "hash-1"
    assert document["created_at"]
    # proves the test used its own temporary database, not data/
    assert isolated_registry.exists()


def test_get_unknown_id_returns_nothing(isolated_registry):
    assert registry.get_document("missing") is None


def test_list_returns_documents_in_insertion_order(isolated_registry):
    # created back to back, so most share the same created_at second:
    # the order must still be the creation order.
    ids = [
        registry.create_document(f"Doc {i}", "public", f"hash-{i}")
        for i in range(5)
    ]

    documents = registry.list_documents()

    assert [d["doc_id"] for d in documents] == ids
    assert [d["title"] for d in documents] == [f"Doc {i}" for i in range(5)]


def test_count_ready_documents_excludes_processing_and_failed(isolated_registry):
    registry.create_document("ready one", "public", "hash-1", status="ready")
    registry.create_document("processing", "public", "hash-2")
    registry.create_document("failed", "members", "hash-3", status="failed")
    registry.create_document("ready two", "members", "hash-4", status="ready")

    assert registry.count_ready_documents() == 2


def test_delete_removes_row_and_reports_existence(isolated_registry):
    doc_id = registry.create_document("Delete me", "public", "hash-delete")

    assert registry.delete_document(doc_id) is True
    assert registry.delete_document(doc_id) is False
    assert registry.get_document(doc_id) is None


def test_find_by_hash_returns_matching_document(isolated_registry):
    doc_id = registry.create_document("Hash hit", "members", "shared-hash")

    document = registry.find_document_by_hash("shared-hash")

    assert document is not None
    assert document["doc_id"] == doc_id
    assert registry.find_document_by_hash("unknown-hash") is None


def test_invalid_visibility_is_rejected(isolated_registry):
    with pytest.raises(AppError) as exc_info:
        registry.create_document("Bad", "secret", "hash-bad")

    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "validation_error"
    assert registry.list_documents() == []


def test_invalid_status_is_rejected_on_create(isolated_registry):
    with pytest.raises(AppError) as exc_info:
        registry.create_document("Bad", "public", "hash-bad", status="redy")

    assert exc_info.value.code == "validation_error"
    assert registry.list_documents() == []


def test_invalid_status_is_rejected_on_update(isolated_registry):
    doc_id = registry.create_document("Doc", "public", "hash-1")

    with pytest.raises(AppError) as exc_info:
        registry.update_document_status(doc_id, "redy")

    assert exc_info.value.code == "validation_error"
    assert registry.get_document(doc_id)["status"] == "processing"


def test_two_documents_get_different_ids(isolated_registry):
    first_id = registry.create_document("One", "public", "hash-1")
    second_id = registry.create_document("Two", "public", "hash-2")

    assert first_id != second_id


def test_status_update_changes_stored_status(isolated_registry):
    doc_id = registry.create_document("Status", "public", "hash-status")

    assert registry.update_document_status(doc_id, "ready") is True
    document = registry.get_document(doc_id)

    assert document is not None
    assert document["status"] == "ready"


def test_failed_status_stores_error_and_ready_clears_it(isolated_registry):
    doc_id = registry.create_document("Doc", "public", "hash-1")

    registry.update_document_status(doc_id, "failed", "corrupt PDF")
    failed = registry.get_document(doc_id)
    assert failed["status"] == "failed"
    assert failed["error"] == "corrupt PDF"

    registry.update_document_status(doc_id, "ready")
    ready = registry.get_document(doc_id)
    assert ready["status"] == "ready"
    assert ready["error"] is None


def test_update_unknown_id_returns_false(isolated_registry):
    assert registry.update_document_status("missing", "ready") is False


def test_hostile_title_is_stored_literally(isolated_registry):
    # proves queries are parameterized: the title is data, never SQL
    hostile = "x'); DROP TABLE documents; --"
    doc_id = registry.create_document(hostile, "public", "hash-1")

    assert registry.get_document(doc_id)["title"] == hostile
    assert len(registry.list_documents()) == 1


def test_arabic_title_round_trips(isolated_registry):
    title = "توظيف القسم"
    doc_id = registry.create_document(title, "members", "hash-ar")

    assert registry.get_document(doc_id)["title"] == title


def test_database_rejects_bad_values_even_without_python_checks(isolated_registry):
    registry.create_document(
        "Seed", "public", "hash-seed")  # creates the table
    connection = sqlite3.connect(isolated_registry)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO documents VALUES "
                "('x', 't', 'secret', 'ready', NULL, 'h', 'now')"
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO documents VALUES "
                "('y', 't', 'public', 'redy', NULL, 'h', 'now')"
            )
    finally:
        connection.close()
