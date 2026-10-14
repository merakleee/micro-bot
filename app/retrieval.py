from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from app.config import get_settings
from app.errors import AppError
from app.vector_store import SearchResult

AccessLevel = Literal["public", "members"]


class QueryEmbedder(Protocol):
    def embed_query(self, text: str) -> Sequence[float]:
        ...


class SearchStore(Protocol):
    def search(
        self,
        query_embedding: Sequence[float],
        *,
        access_level: AccessLevel,
        limit: int = 5,
    ) -> list[SearchResult]:
        ...


@dataclass(frozen=True)
class RetrievalResponse:
    query: str
    results: list[SearchResult]
    best_score: float
    threshold: float


def retrieve(
    query: str,
    access_level: AccessLevel,
    k: int,
    *,
    embedder: QueryEmbedder,
    store: SearchStore,
) -> RetrievalResponse:
    if not isinstance(query, str) or not query.strip():
        raise AppError(
            422,
            "validation_error",
            "query must be a non-empty string.",
        )

    if access_level not in {"public", "members"}:
        raise AppError(
            422,
            "validation_error",
            "access_level must be public or members.",
        )

    if k <= 0:
        raise AppError(
            422,
            "validation_error",
            "k must be positive.",
        )

    query_text = query.strip()
    query_embedding = embedder.embed_query(query_text)

    results = store.search(
        query_embedding,
        access_level=access_level,
        limit=k,
    )

    threshold = get_settings().retrieval_threshold

    if not results:
        raise AppError(
            404,
            "no_relevant_context",
            "No relevant information was found.",
        )

    best_score = max(result.score for result in results)

    if best_score < threshold:
        raise AppError(
            404,
            "no_relevant_context",
            "No sufficiently relevant information was found.",
        )

    return RetrievalResponse(
        query=query_text,
        results=results,
        best_score=best_score,
        threshold=threshold,
    )
