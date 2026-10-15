from __future__ import annotations

from types import SimpleNamespace

from app.vector_store import SearchResult
from scripts.evaluate import (
    calculate_access_accuracy,
    calculate_hit_at_k,
    calculate_mrr,
    calculate_refusal_accuracy,
)


def make_result(
    *,
    title: str,
    visibility: str = "public",
    score: float = 0.9,
) -> SearchResult:
    return SearchResult(
        text="Example",
        doc_id=f"doc-{title}",
        title=title,
        visibility=visibility,
        chunk_index=0,
        score=score,
    )


def make_evaluation(
    *,
    case_id: str,
    category: str = "public",
    access_level: str = "public",
    expected_source: str | None = "corpus/about.md",
    results: list[SearchResult] | None = None,
    refused: bool = False,
):
    return SimpleNamespace(
        case_id=case_id,
        category=category,
        access_level=access_level,
        expected_source=expected_source,
        results=results or [],
        refused=refused,
    )


def test_hit_at_one_is_one_when_source_is_first():
    evaluations = [
        make_evaluation(
            case_id="case-1",
            results=[
                make_result(title="About"),
            ],
        )
    ]

    assert calculate_hit_at_k(
        evaluations,
        1,
        {"corpus/about.md": "About"},
    ) == 1.0


def test_hit_at_one_is_zero_when_source_is_second():
    evaluations = [
        make_evaluation(
            case_id="case-1",
            results=[
                make_result(title="Sections"),
                make_result(title="About"),
            ],
        )
    ]

    assert calculate_hit_at_k(
        evaluations,
        1,
        {"corpus/about.md": "About"},
    ) == 0.0


def test_mrr_uses_reciprocal_rank():
    evaluations = [
        make_evaluation(
            case_id="case-1",
            results=[
                make_result(title="Sections"),
                make_result(title="About"),
            ],
        )
    ]

    assert calculate_mrr(
        evaluations,
        {"corpus/about.md": "About"},
    ) == 0.5


def test_public_access_accuracy_rejects_members_chunk():
    evaluations = [
        make_evaluation(
            case_id="public-case",
            access_level="public",
            results=[
                make_result(
                    title="Members List",
                    visibility="members",
                )
            ],
        )
    ]

    assert calculate_access_accuracy(evaluations) == 0.0


def test_public_access_accuracy_accepts_public_chunks():
    evaluations = [
        make_evaluation(
            case_id="public-case",
            access_level="public",
            results=[
                make_result(title="About"),
            ],
        )
    ]

    assert calculate_access_accuracy(evaluations) == 1.0


def test_refusal_accuracy_counts_expected_refusals():
    evaluations = [
        make_evaluation(
            case_id="out-of-scope",
            category="out_of_scope",
            expected_source=None,
            refused=True,
        ),
        make_evaluation(
            case_id="member-as-public",
            category="member_question_as_public",
            expected_source=None,
            refused=True,
        ),
    ]

    assert calculate_refusal_accuracy(evaluations) == 1.0
