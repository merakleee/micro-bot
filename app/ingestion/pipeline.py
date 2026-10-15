from __future__ import annotations

import hashlib
from pathlib import Path
from threading import Lock
from typing import Protocol, Sequence

from app import registry
from app.config import get_settings
from app.ingestion.chunking import DocumentChunk, chunk_text
from app.ingestion.parsers import parse_document


class Embedder(Protocol):
    def embed_documents(
        self, texts: Sequence[str]
    ) -> list[list[float]]:
        ...


class VectorStore(Protocol):
    def add_chunks(
        self,
        chunks: Sequence[DocumentChunk],
        embeddings: Sequence[Sequence[float]],
    ) -> int:
        ...

    def delete_by_doc_id(self, doc_id: str) -> None:
        ...


_claim_lock = Lock()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)

    return digest.hexdigest()


def ingest_file(
    path: str | Path,
    *,
    title: str,
    visibility: str,
    embedder: Embedder,
    store: VectorStore,
) -> tuple[str, bool]:
    file_path = Path(path)
    content_hash = _sha256(file_path)

    with _claim_lock:
        claim = registry.claim_document(
            title=title,
            visibility=visibility,
            content_hash=content_hash,
        )

    if claim.skipped:
        return claim.doc_id, True

    doc_id = claim.doc_id

    try:
        parsed = parse_document(file_path)

        chunks = chunk_text(
            parsed.text,
            doc_id=doc_id,
            title=title,
            visibility=visibility,
            chunk_size=get_settings().chunk_size,
            overlap=get_settings().chunk_overlap,
        )

        if not chunks:
            raise ValueError("Document produced no usable chunks.")

        # TextEmbedder adds `passage: ` internally. The stored chunk text
        # remains unchanged and does not contain that prefix.
        embeddings = embedder.embed_documents(
            [chunk.text for chunk in chunks]
        )

        store.add_chunks(chunks, embeddings)
        registry.update_document_status(doc_id, "ready")
        return doc_id, False

    except Exception as exc:
        try:
            store.delete_by_doc_id(doc_id)
        finally:
            registry.update_document_status(
                doc_id,
                "failed",
                error=str(exc),
            )
        raise


def delete_document(doc_id: str, store: VectorStore) -> bool:
    document = registry.get_document(doc_id)

    if document is None:
        return False

    store.delete_by_doc_id(doc_id)
    return registry.delete_document(doc_id)
