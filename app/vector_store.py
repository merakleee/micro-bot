from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
from typing import Literal, Sequence
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient, models

from app.config import get_settings
from app.ingestion.chunking import DocumentChunk

AccessLevel = Literal["public", "members"]
COLLECTION_NAME = "micro_bot_chunks"


@dataclass(frozen=True)
class SearchResult:
    text: str
    doc_id: str
    title: str
    visibility: str
    chunk_index: int
    score: float


class QdrantVectorStore:
    def __init__(
        self,
        client: QdrantClient | None = None,
        *,
        collection_name: str = COLLECTION_NAME,
        create_payload_indexes: bool | None = None,
    ) -> None:
        if client is None:
            settings = get_settings()
            if settings.qdrant_url:
                client = QdrantClient(
                    url=settings.qdrant_url,
                    api_key=settings.qdrant_api_key or None,
                )
                should_create_indexes = True
            else:
                client = QdrantClient(path=settings.vector_store_path)
                should_create_indexes = False
        else:
            should_create_indexes = False

        self._client = client
        self._collection_name = collection_name
        self._create_payload_indexes = (
            should_create_indexes
            if create_payload_indexes is None
            else create_payload_indexes
        )

    def _ensure_collection(self, vector_size: int) -> None:
        if not self._client.collection_exists(self._collection_name):
            self._client.create_collection(
                collection_name=self._collection_name,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=models.Distance.COSINE,
                ),
            )
            if self._create_payload_indexes:
                self._client.create_payload_index(
                    collection_name=self._collection_name,
                    field_name="visibility",
                    field_schema=models.PayloadSchemaType.KEYWORD,
                    wait=True,
                )
                self._client.create_payload_index(
                    collection_name=self._collection_name,
                    field_name="doc_id",
                    field_schema=models.PayloadSchemaType.KEYWORD,
                    wait=True,
                )
            return

        collection = self._client.get_collection(self._collection_name)
        configured_size = collection.config.params.vectors.size
        if configured_size != vector_size:
            raise ValueError(
                "Embedding dimension does not match the existing collection "
                f"({vector_size} != {configured_size})."
            )
    def add_chunks(
        self,
        chunks: Sequence[DocumentChunk],
        embeddings: Sequence[Sequence[float]],
    ) -> int:
        if len(chunks) != len(embeddings):
            raise ValueError("Each chunk must have exactly one embedding.")
        if not chunks:
            return 0

        vector_size = self._validate_embeddings(embeddings)
        if any(chunk.visibility not in {"public", "members"} for chunk in chunks):
            raise ValueError("Chunk visibility must be public or members.")

        self._ensure_collection(vector_size)
        points = [
            models.PointStruct(
                id=str(uuid5(
                    NAMESPACE_URL,
                    f"micro-bot:{chunk.doc_id}:{chunk.chunk_index}",
                )),
                vector=[float(value) for value in embedding],
                payload={
                    "text": chunk.text,
                    "doc_id": chunk.doc_id,
                    "title": chunk.title,
                    "visibility": chunk.visibility,
                    "chunk_index": chunk.chunk_index,
                },
            )
            for chunk, embedding in zip(chunks, embeddings)
        ]
        self._client.upsert(
            collection_name=self._collection_name,
            points=points,
            wait=True,
        )
        return len(points)

    def replace_document_chunks(
        self,
        doc_id: str,
        chunks: Sequence[DocumentChunk],
        embeddings: Sequence[Sequence[float]],
    ) -> int:
        """Replace every stored chunk for one document with its new version."""
        if any(chunk.doc_id != doc_id for chunk in chunks):
            raise ValueError("All chunks must belong to doc_id.")
        if len(chunks) != len(embeddings):
            raise ValueError("Each chunk must have exactly one embedding.")
        if any(chunk.visibility not in {"public", "members"} for chunk in chunks):
            raise ValueError("Chunk visibility must be public or members.")

        if not chunks:
            self.delete_by_doc_id(doc_id)
            return 0

        # Validate the new collection dimension before deleting the old data.
        self._validate_embeddings(embeddings)
        self._ensure_collection(len(embeddings[0]))
        self.delete_by_doc_id(doc_id)
        return self.add_chunks(chunks, embeddings)

    @staticmethod
    def _validate_embeddings(embeddings: Sequence[Sequence[float]]) -> int:
        if not embeddings:
            raise ValueError("At least one embedding is required.")

        vector_size = len(embeddings[0])
        if vector_size == 0 or any(
            len(vector) != vector_size for vector in embeddings
        ):
            raise ValueError("Embeddings must be non-empty and have equal dimensions.")
        return vector_size

    def delete_by_doc_id(self, doc_id: str) -> None:
        if not self._client.collection_exists(self._collection_name):
            return

        self._client.delete(
            collection_name=self._collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="doc_id",
                            match=models.MatchValue(value=doc_id),
                        )
                    ]
                )
            ),
            wait=True,
        )

    def search(
        self,
        query_embedding: Sequence[float],
        *,
        access_level: AccessLevel,
        limit: int = 5,
    ) -> list[SearchResult]:
        if access_level not in {"public", "members"}:
            raise ValueError("access_level must be public or members.")
        if limit <= 0:
            raise ValueError("limit must be positive.")
        if len(query_embedding) == 0:
            raise ValueError("query_embedding must not be empty.")
        if not self._client.collection_exists(self._collection_name):
            return []

        visibility_match: models.MatchValue | models.MatchAny
        if access_level == "public":
            visibility_match = models.MatchValue(value="public")
        else:
            visibility_match = models.MatchAny(any=["public", "members"])

        response = self._client.query_points(
            collection_name=self._collection_name,
            query=[float(value) for value in query_embedding],
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="visibility",
                        match=visibility_match,
                    )
                ]
            ),
            limit=limit,
            with_payload=True,
        )

        results: list[SearchResult] = []
        for point in response.points:
            payload = point.payload
            if not isinstance(payload, Mapping):
                raise ValueError("Qdrant result is missing its payload.")
            required_fields = {
                "text", "doc_id", "title", "visibility", "chunk_index"
            }
            if not required_fields.issubset(payload):
                raise ValueError("Qdrant result has an incomplete payload.")
            results.append(
                SearchResult(
                    text=str(payload["text"]),
                    doc_id=str(payload["doc_id"]),
                    title=str(payload["title"]),
                    visibility=str(payload["visibility"]),
                    chunk_index=int(payload["chunk_index"]),
                    score=float(point.score),
                )
            )
        return results
