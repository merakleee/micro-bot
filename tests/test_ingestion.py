from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import registry
from app.config import get_settings
from app.ingestion import pipeline
from app.ingestion.chunking import DocumentChunk
from app.ingestion.parsers import ParsedDocument


@dataclass
class FakeEmbedder:
    received_texts: list[str]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.received_texts.extend(texts)

        return [
            [float(len(text)), 1.0]
            for text in texts
        ]


class FakeVectorStore:
    def __init__(self) -> None:
        self.chunks: dict[str, DocumentChunk] = {}
        self.add_calls = 0
        self.delete_calls: list[str] = []
        self.fail_after_add = False

    def add_chunks(
        self,
        chunks: list[DocumentChunk],
        embeddings: list[list[float]],
    ) -> int:
        assert len(chunks) == len(embeddings)

        self.add_calls += 1

        for chunk in chunks:
            key = f"{chunk.doc_id}:{chunk.chunk_index}"
            self.chunks[key] = chunk

        if self.fail_after_add:
            raise RuntimeError("vector store failed after adding chunks")

        return len(chunks)

    def delete_by_doc_id(self, doc_id: str) -> None:
        self.delete_calls.append(doc_id)

        self.chunks = {
            key: chunk
            for key, chunk in self.chunks.items()
            if chunk.doc_id != doc_id
        }

    def chunk_count(self) -> int:
        return len(self.chunks)


@pytest.fixture
def isolated_registry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    database_path = tmp_path / "registry.sqlite3"

    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("CHUNK_SIZE", "800")
    monkeypatch.setenv("CHUNK_OVERLAP", "120")

    get_settings.cache_clear()

    yield database_path

    get_settings.cache_clear()


@pytest.fixture
def source_file(tmp_path: Path) -> Path:
    path = tmp_path / "members.md"
    path.write_text(
        "# Members\n\n"
        "This document contains information about members.",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def fake_parser(monkeypatch: pytest.MonkeyPatch):
    def parse_document(path: Path) -> ParsedDocument:
        return ParsedDocument(
            title=path.stem,
            text=path.read_text(encoding="utf-8"),
        )

    monkeypatch.setattr(
        pipeline,
        "parse_document",
        parse_document,
    )


def test_ingest_file_creates_ready_document(
    isolated_registry,
    source_file: Path,
    fake_parser,
):
    embedder = FakeEmbedder([])
    store = FakeVectorStore()

    doc_id, skipped = pipeline.ingest_file(
        source_file,
        title="Members",
        visibility="members",
        embedder=embedder,
        store=store,
    )

    document = registry.get_document(doc_id)

    assert skipped is False
    assert document is not None
    assert document["doc_id"] == doc_id
    assert document["title"] == "Members"
    assert document["visibility"] == "members"
    assert document["status"] == "ready"
    assert document["error"] is None
    assert store.chunk_count() > 0


def test_ingesting_same_file_twice_skips_without_adding_duplicates(
    isolated_registry,
    source_file: Path,
    fake_parser,
):
    embedder = FakeEmbedder([])
    store = FakeVectorStore()

    first_id, first_skipped = pipeline.ingest_file(
        source_file,
        title="Members",
        visibility="members",
        embedder=embedder,
        store=store,
    )
    first_chunk_count = store.chunk_count()
    first_add_calls = store.add_calls

    second_id, second_skipped = pipeline.ingest_file(
        source_file,
        title="Members",
        visibility="members",
        embedder=embedder,
        store=store,
    )

    assert first_skipped is False
    assert second_skipped is True
    assert second_id == first_id
    assert store.chunk_count() == first_chunk_count
    assert store.add_calls == first_add_calls


def test_embedder_receives_original_text_without_passage_prefix(
    isolated_registry,
    source_file: Path,
    fake_parser,
):
    embedder = FakeEmbedder([])
    store = FakeVectorStore()

    pipeline.ingest_file(
        source_file,
        title="Members",
        visibility="members",
        embedder=embedder,
        store=store,
    )

    assert embedder.received_texts
    assert all(
        not text.startswith("passage: ")
        for text in embedder.received_texts
    )

    stored_texts = [chunk.text for chunk in store.chunks.values()]
    assert stored_texts == embedder.received_texts


def test_failed_ingestion_marks_document_failed_and_removes_chunks(
    isolated_registry,
    source_file: Path,
    fake_parser,
):
    embedder = FakeEmbedder([])
    store = FakeVectorStore()
    store.fail_after_add = True

    with pytest.raises(RuntimeError, match="vector store failed"):
        pipeline.ingest_file(
            source_file,
            title="Members",
            visibility="members",
            embedder=embedder,
            store=store,
        )

    documents = registry.list_documents()

    assert len(documents) == 1
    assert documents[0]["status"] == "failed"
    assert "vector store failed" in (documents[0]["error"] or "")
    assert store.chunk_count() == 0
    assert store.delete_calls == [documents[0]["doc_id"]]


def test_empty_document_is_marked_failed(
    isolated_registry,
    source_file: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    def parse_empty_document(path: Path) -> ParsedDocument:
        return ParsedDocument(
            title=path.stem,
            text="",
        )

    monkeypatch.setattr(
        pipeline,
        "parse_document",
        parse_empty_document,
    )

    embedder = FakeEmbedder([])
    store = FakeVectorStore()

    with pytest.raises(ValueError, match="no usable chunks"):
        pipeline.ingest_file(
            source_file,
            title="Empty document",
            visibility="public",
            embedder=embedder,
            store=store,
        )

    documents = registry.list_documents()

    assert len(documents) == 1
    assert documents[0]["status"] == "failed"
    assert "no usable chunks" in (documents[0]["error"] or "")
    assert embedder.received_texts == []
    assert store.chunk_count() == 0


def test_same_hash_with_different_visibility_is_rejected(
    isolated_registry,
    source_file: Path,
    fake_parser,
):
    embedder = FakeEmbedder([])
    store = FakeVectorStore()

    first_id, first_skipped = pipeline.ingest_file(
        source_file,
        title="Members",
        visibility="public",
        embedder=embedder,
        store=store,
    )

    with pytest.raises(
        ValueError,
        match="different visibility",
    ):
        pipeline.ingest_file(
            source_file,
            title="Members",
            visibility="members",
            embedder=embedder,
            store=store,
        )

    document = registry.get_document(first_id)

    assert first_skipped is False
    assert document is not None
    assert document["visibility"] == "public"
    assert document["status"] == "ready"
    assert store.chunk_count() > 0


def test_failed_document_can_be_retried(
    isolated_registry,
    source_file: Path,
    fake_parser,
):
    embedder = FakeEmbedder([])
    store = FakeVectorStore()
    store.fail_after_add = True

    with pytest.raises(RuntimeError):
        pipeline.ingest_file(
            source_file,
            title="Members",
            visibility="members",
            embedder=embedder,
            store=store,
        )

    failed_document = registry.list_documents()[0]
    assert failed_document["status"] == "failed"

    store.fail_after_add = False

    retried_id, retried_skipped = pipeline.ingest_file(
        source_file,
        title="Members",
        visibility="members",
        embedder=embedder,
        store=store,
    )

    retried_document = registry.get_document(retried_id)

    assert retried_id == failed_document["doc_id"]
    assert retried_skipped is False
    assert retried_document is not None
    assert retried_document["status"] == "ready"
    assert retried_document["error"] is None
    assert store.chunk_count() > 0


def test_delete_document_removes_chunks_before_registry_row(
    isolated_registry,
    source_file: Path,
    fake_parser,
):
    embedder = FakeEmbedder([])
    store = FakeVectorStore()

    doc_id, _ = pipeline.ingest_file(
        source_file,
        title="Members",
        visibility="members",
        embedder=embedder,
        store=store,
    )

    assert store.chunk_count() > 0
    assert registry.get_document(doc_id) is not None

    deleted = pipeline.delete_document(
        doc_id,
        store=store,
    )

    assert deleted is True
    assert store.chunk_count() == 0
    assert registry.get_document(doc_id) is None
    assert store.delete_calls == [doc_id]


def test_delete_unknown_document_returns_false(
    isolated_registry,
):
    store = FakeVectorStore()

    deleted = pipeline.delete_document(
        "missing-document",
        store=store,
    )

    assert deleted is False
    assert store.delete_calls == []


def test_vector_store_failure_keeps_registry_row(
    isolated_registry,
    source_file: Path,
    fake_parser,
    monkeypatch: pytest.MonkeyPatch,
):
    embedder = FakeEmbedder([])
    store = FakeVectorStore()

    doc_id, _ = pipeline.ingest_file(
        source_file,
        title="Members",
        visibility="members",
        embedder=embedder,
        store=store,
    )

    def fail_delete(doc_id: str) -> None:
        raise RuntimeError("vector deletion failed")

    monkeypatch.setattr(store, "delete_by_doc_id", fail_delete)

    with pytest.raises(RuntimeError, match="vector deletion failed"):
        pipeline.delete_document(
            doc_id,
            store=store,
        )

    assert registry.get_document(doc_id) is not None
