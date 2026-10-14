from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from app.config import get_settings
from app.errors import AppError
from app.retrieval import retrieve
from app.vector_store import SearchResult


@dataclass
class FakeEmbedder:
    calls: list[str]

    def embed_query(self, text: str) -> list[float]:
        self.calls.append(text)
        return [1.0, 0.0]


class FakeStore:
    def __init__(self, results: list[SearchResult]):
        self.results = results
        self.calls: list[tuple[list[float], str, int]] = []

    def search(
        self,
        query_embedding,
        *,
        access_level: str,
        limit: int = 5,
    ) -> list[SearchResult]:
        self.calls.append(
            (list(query_embedding), access_level, limit)
        )
        return self.results[:limit]


def result(
    *,
    score: float,
    visibility: str = "public",
    doc_id: str = "doc-1",
) -> SearchResult:
    return SearchResult(
        text="Example retrieved text.",
        doc_id=doc_id,
        title="Example document",
        visibility=visibility,
        chunk_index=0,
        score=score,
    )


@pytest.fixture
def retrieval_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RETRIEVAL_THRESHOLD", "0.79")
    get_settings.cache_clear()

    yield

    get_settings.cache_clear()


def test_retrieve_returns_chunks_with_scores(retrieval_settings):
    embedder = FakeEmbedder([])
    store = FakeStore(
        [
            result(score=0.92),
            result(score=0.84, doc_id="doc-2"),
        ]
    )

    response = retrieve(
        "What is the club?",
        "public",
        5,
        embedder=embedder,
        store=store,
    )

    assert response.best_score == pytest.approx(0.92)
    assert response.threshold == pytest.approx(0.79)
    assert len(response.results) == 2
    assert response.results[0].score == pytest.approx(0.92)
    assert embedder.calls == ["What is the club?"]
    assert store.calls == [([1.0, 0.0], "public", 5)]


def test_retrieve_passes_access_level_to_store(retrieval_settings):
    embedder = FakeEmbedder([])
    store = FakeStore([result(score=0.90, visibility="members")])

    response = retrieve(
        "Members question",
        "members",
        3,
        embedder=embedder,
        store=store,
    )

    assert response.results[0].visibility == "members"
    assert store.calls == [([1.0, 0.0], "members", 3)]


def test_retrieve_refuses_when_best_score_is_below_threshold(
    retrieval_settings,
):
    embedder = FakeEmbedder([])
    store = FakeStore([result(score=0.78)])

    with pytest.raises(
        AppError,
        match="No sufficiently relevant information",
    ) as exc_info:
        retrieve(
            "Unrelated question",
            "public",
            5,
            embedder=embedder,
            store=store,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "no_relevant_context"


def test_retrieve_accepts_score_equal_to_threshold(
    retrieval_settings,
):
    embedder = FakeEmbedder([])
    store = FakeStore([result(score=0.79)])

    response = retrieve(
        "Boundary question",
        "public",
        5,
        embedder=embedder,
        store=store,
    )

    assert response.best_score == pytest.approx(0.79)


def test_retrieve_refuses_empty_store(retrieval_settings):
    embedder = FakeEmbedder([])
    store = FakeStore([])

    with pytest.raises(
        AppError,
        match="No relevant information",
    ):
        retrieve(
            "Question",
            "public",
            5,
            embedder=embedder,
            store=store,
        )


@pytest.mark.parametrize(
    "query",
    ["", "   ", None],
)
def test_retrieve_rejects_empty_query(
    retrieval_settings,
    query,
):
    embedder = FakeEmbedder([])
    store = FakeStore([])

    with pytest.raises(AppError, match="non-empty"):
        retrieve(
            query,
            "public",
            5,
            embedder=embedder,
            store=store,
        )


@pytest.mark.parametrize("k", [0, -1])
def test_retrieve_rejects_invalid_k(
    retrieval_settings,
    k,
):
    embedder = FakeEmbedder([])
    store = FakeStore([])

    with pytest.raises(AppError, match="k must be positive"):
        retrieve(
            "Question",
            "public",
            k,
            embedder=embedder,
            store=store,
        )
