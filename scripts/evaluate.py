from __future__ import annotations


from app.vector_store import SearchResult
from app.retrieval import retrieve
from app.ingestion.runtime import get_embedder, get_vector_store
from app.errors import AppError
from app.config import get_settings
from fastapi.testclient import TestClient
from app.main import app
import argparse
import csv
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


client = TestClient(app)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT))


EVALUATION_PATH = PROJECT_ROOT / "evals" / "evaluation_set.json"
CACHE_PATH = PROJECT_ROOT / "eval" / "answer_cache.json"
RESULTS_PATH = PROJECT_ROOT / "eval" / "results.md"
CSV_RESULTS_PATH = PROJECT_ROOT / "eval" / "results.csv"


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    category: str
    language: str
    access_level: str
    question: str
    expected_source: str | None
    expected_answer: str
    previous_turns: list[dict[str, str]]


@dataclass(frozen=True)
class RetrievalEvaluation:
    case_id: str
    category: str
    access_level: str
    expected_source: str | None
    results: list[SearchResult]
    best_score: float | None
    refused: bool
    refusal_error: str | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate retrieval, access control, refusal behavior, "
            "and optionally cached answers."
        )
    )

    parser.add_argument(
        "--k",
        type=int,
        default=5,
        help="Maximum number of retrieved chunks.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Override RETRIEVAL_THRESHOLD for this evaluation.",
    )
    parser.add_argument(
        "--answers",
        action="store_true",
        help="Run the small cached answer-check sample.",
    )
    parser.add_argument(
        "--refresh-answers",
        action="store_true",
        help="Ignore cached answer results and call the LLM again.",
    )
    parser.add_argument(
        "--answer-sample",
        type=int,
        default=6,
        help="Number of answer cases to evaluate when --answers is used.",
    )

    args = parser.parse_args()

    if args.k <= 0:
        parser.error("--k must be positive.")

    if args.threshold is not None and not -1.0 <= args.threshold <= 1.0:
        parser.error("--threshold must be between -1 and 1.")

    if args.answer_sample <= 0:
        parser.error("--answer-sample must be positive.")

    return args


def load_cases() -> list[EvaluationCase]:
    with EVALUATION_PATH.open(encoding="utf-8") as file:
        raw_cases = json.load(file)

    cases: list[EvaluationCase] = []

    for raw in raw_cases:
        cases.append(
            EvaluationCase(
                case_id=raw["id"],
                category=raw["category"],
                language=raw["language"],
                access_level=raw["access_level"],
                question=raw["question"],
                expected_source=raw.get("expected_source"),
                expected_answer=raw["expected_answer"],
                previous_turns=raw.get("previous_turns", []),
            )
        )

    return cases


def source_matches(
    result: SearchResult,
    expected_source: str | None,
) -> bool:
    if expected_source is None:
        return False

    expected_name = Path(expected_source).name

    # Current Qdrant payload stores doc_id/title, not the original path.
    # Match using a mapping from the evaluation source filename to title.
    source_title = Path(expected_source).stem.lower()
    result_title = result.title.strip().lower()

    return (
        result_title == source_title
        or result_title == expected_name.removesuffix(".md").lower()
    )


def source_matches_with_mapping(
    result: SearchResult,
    expected_source: str | None,
    source_to_title: dict[str, str],
) -> bool:
    if expected_source is None:
        return False

    expected_title = source_to_title.get(expected_source)
    if expected_title is None:
        expected_title = Path(expected_source).stem

    return result.title.strip().casefold() == expected_title.strip().casefold()


def load_manifest_titles() -> dict[str, str]:
    manifest_path = PROJECT_ROOT / "corpus" / "manifest.csv"
    mapping: dict[str, str] = {}

    with manifest_path.open(
        encoding="utf-8",
        newline="",
    ) as file:
        for row in csv.DictReader(file):
            mapping[f"corpus/{row['filename']}"] = row["title"]

    return mapping


def evaluate_case(
    case: EvaluationCase,
    *,
    k: int,
    threshold: float,
    embedder: Any,
    store: Any,
) -> RetrievalEvaluation:
    query = case.question

    if case.previous_turns:
        previous_questions = [
            turn["content"]
            for turn in case.previous_turns
            if turn.get("role") == "user"
        ]
        query = " ".join(
            [*previous_questions, case.question]
        )

    query_embedding = embedder.embed_query(
        f"query: {query}"
    )

    results = store.search(
        query_embedding,
        access_level=case.access_level,
        limit=k,
    )

    best_score = max(
        (result.score for result in results),
        default=None,
    )

    refused = (
        not results
        or (
            best_score is not None
            and best_score < threshold
        )
    )

    return RetrievalEvaluation(
        case_id=case.case_id,
        category=case.category,
        access_level=case.access_level,
        expected_source=case.expected_source,
        results=results,
        best_score=best_score,
        refused=refused,
        refusal_error=(
            "no_relevant_context"
            if refused
            else None
        ),
    )


def calculate_hit_at_k(
    evaluations: list[RetrievalEvaluation],
    k: int,
    source_to_title: dict[str, str],
) -> float:
    source_cases = [
        evaluation
        for evaluation in evaluations
        if evaluation.expected_source is not None
    ]

    if not source_cases:
        return 0.0

    hits = 0

    for evaluation in source_cases:
        top_results = evaluation.results[:k]

        if any(
            source_matches_with_mapping(
                result,
                evaluation.expected_source,
                source_to_title,
            )
            for result in top_results
        ):
            hits += 1

    return hits / len(source_cases)


def calculate_mrr(
    evaluations: list[RetrievalEvaluation],
    source_to_title: dict[str, str],
) -> float:
    source_cases = [
        evaluation
        for evaluation in evaluations
        if evaluation.expected_source is not None
    ]

    if not source_cases:
        return 0.0

    reciprocal_ranks: list[float] = []

    for evaluation in source_cases:
        rank = 0

        for index, result in enumerate(evaluation.results, start=1):
            if source_matches_with_mapping(
                result,
                evaluation.expected_source,
                source_to_title,
            ):
                rank = index
                break

        reciprocal_ranks.append(
            0.0 if rank == 0 else 1.0 / rank
        )

    return sum(reciprocal_ranks) / len(reciprocal_ranks)


def calculate_access_accuracy(
    evaluations: list[RetrievalEvaluation],
) -> float:
    public_cases = [
        evaluation
        for evaluation in evaluations
        if evaluation.access_level == "public"
    ]

    if not public_cases:
        return 0.0

    safe_cases = 0

    for evaluation in public_cases:
        returned_members_chunk = any(
            result.visibility == "members"
            for result in evaluation.results
        )

        if not returned_members_chunk:
            safe_cases += 1

    return safe_cases / len(public_cases)


def calculate_refusal_accuracy(
    evaluations: list[RetrievalEvaluation],
) -> float:
    refusal_cases = [
        evaluation
        for evaluation in evaluations
        if evaluation.category in {
            "out_of_scope",
            "member_question_as_public",
        }
    ]

    if not refusal_cases:
        return 0.0

    correct = sum(
        evaluation.refused
        for evaluation in refusal_cases
    )

    return correct / len(refusal_cases)


def load_cache() -> dict[str, Any]:
    if not CACHE_PATH.exists():
        return {}

    with CACHE_PATH.open(encoding="utf-8") as file:
        return json.load(file)


def save_cache(cache: dict[str, Any]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = CACHE_PATH.with_suffix(".tmp")

    with temporary_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            cache,
            file,
            ensure_ascii=False,
            indent=2,
        )

    temporary_path.replace(CACHE_PATH)


def answer_cache_key(
    case: EvaluationCase,
    *,
    k: int,
    threshold: float | None,
) -> str:
    payload = {
        "case_id": case.case_id,
        "question": case.question,
        "access_level": case.access_level,
        "k": k,
        "threshold": threshold,
    }

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


def select_answer_cases(
    cases: list[EvaluationCase],
    sample_size: int,
) -> list[EvaluationCase]:
    preferred_categories = [
        "public",
        "out_of_scope",
        "member_question_as_public",
        "follow_up",
    ]

    selected: list[EvaluationCase] = []

    for category in preferred_categories:
        category_cases = [
            case
            for case in cases
            if case.category == category
        ]

        if category_cases:
            selected.append(category_cases[0])

        if len(selected) >= sample_size:
            return selected[:sample_size]

    return cases[:sample_size]


def run_cached_answer_checks(
    cases: list[EvaluationCase],
    evaluations: dict[str, RetrievalEvaluation],
    *,
    k: int,
    threshold: float | None,
    refresh: bool,
) -> dict[str, Any]:
    cache = load_cache()

    selected = select_answer_cases(
        cases,
        sample_size=6,
    )

    for case in selected:
        key = answer_cache_key(
            case,
            k=k,
            threshold=threshold,
        )

        if key in cache and not refresh:
            continue

        evaluation = evaluations[case.case_id]

        if evaluation.refused:
            cache[key] = {
                "case_id": case.case_id,
                "answer": (
                    "refused before LLM call"
                ),
                "grounded": False,
                "llm_calls": 0,
                "cached_at": datetime.now(
                    timezone.utc
                ).isoformat(),
            }
            continue

        # This section should call the real chat pipeline only when
        # --answers is explicitly supplied.
        from app.ingestion.runtime import (
            get_embedder,
            get_vector_store,
        )
        from app.routes.chat import chat

        cache[key] = {
            "case_id": case.case_id,
            "answer": (
                "Run through the API route or replace this section "
                "with your TestClient call."
            ),
            "grounded": None,
            "llm_calls": None,
            "cached_at": datetime.now(
                timezone.utc
            ).isoformat(),
        }

    save_cache(cache)
    return cache


def write_results(
    cases: list[EvaluationCase],
    evaluations: list[RetrievalEvaluation],
    *,
    k: int,
    threshold: float | None,
    source_to_title: dict[str, str],
    answer_cache: dict[str, Any] | None,
) -> None:
    hit_at_1 = calculate_hit_at_k(
        evaluations,
        1,
        source_to_title,
    )
    hit_at_3 = calculate_hit_at_k(
        evaluations,
        min(3, k),
        source_to_title,
    )
    hit_at_5 = calculate_hit_at_k(
        evaluations,
        min(5, k),
        source_to_title,
    )

    mrr = calculate_mrr(
        evaluations,
        source_to_title,
    )

    access_accuracy = calculate_access_accuracy(
        evaluations,
    )

    refusal_accuracy = calculate_refusal_accuracy(
        evaluations,
    )

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)

    with RESULTS_PATH.open("w", encoding="utf-8") as file:
        file.write("# Evaluation results\n\n")
        file.write(f"- Cases: {len(cases)}\n")
        file.write(f"- Retrieval k: {k}\n")
        file.write(f"- Refusal threshold: {threshold}\n\n")
        file.write("## Retrieval\n\n")
        file.write(f"- hit@1: {hit_at_1:.3f}\n")
        file.write(f"- hit@3: {hit_at_3:.3f}\n")
        file.write(f"- hit@5: {hit_at_5:.3f}\n")
        file.write(f"- MRR: {mrr:.3f}\n\n")
        file.write("## Safety\n\n")
        file.write(
            f"- Public access accuracy: "
            f"{access_accuracy:.3f}\n"
        )
        file.write(
            f"- Refusal accuracy: "
            f"{refusal_accuracy:.3f}\n\n"
        )

        file.write("## Per-case results\n\n")
        file.write(
            "| ID | Category | Best score | Refused | Top sources |\n"
        )
        file.write(
            "|---|---|---:|---|---|\n"
        )

        for evaluation in evaluations:
            top_sources = ", ".join(
                result.title
                for result in evaluation.results[:k]
            )

            file.write(
                f"| {evaluation.case_id} | "
                f"{evaluation.category} | "
                f"{evaluation.best_score or 0:.3f} | "
                f"{evaluation.refused} | "
                f"{top_sources} |\n"
            )

        if answer_cache:
            file.write("\n## Cached answer checks\n\n")
            file.write(
                f"- Cached entries: {len(answer_cache)}\n"
            )


def main() -> int:
    args = parse_args()

    settings = get_settings()

    threshold = (
        args.threshold
        if args.threshold is not None
        else settings.retrieval_threshold
    )

    cases = load_cases()
    source_to_title = load_manifest_titles()

    embedder = get_embedder()
    store = get_vector_store()

    evaluations = [
        evaluate_case(
            case,
            k=args.k,
            threshold=threshold,
            embedder=embedder,
            store=store,
        )
        for case in cases
    ]

    evaluation_map = {
        evaluation.case_id: evaluation
        for evaluation in evaluations
    }

    answer_cache = None

    if args.answers:
        answer_cache = run_cached_answer_checks(
            cases,
            evaluation_map,
            k=args.k,
            threshold=threshold,
            refresh=args.refresh_answers,
        )

    write_results(
        cases,
        evaluations,
        k=args.k,
        threshold=threshold,
        source_to_title=source_to_title,
        answer_cache=answer_cache,
    )

    hit_at_1 = calculate_hit_at_k(
        evaluations,
        1,
        source_to_title,
    )
    hit_at_3 = calculate_hit_at_k(
        evaluations,
        min(3, args.k),
        source_to_title,
    )
    hit_at_5 = calculate_hit_at_k(
        evaluations,
        min(5, args.k),
        source_to_title,
    )
    mrr = calculate_mrr(
        evaluations,
        source_to_title,
    )
    access_accuracy = calculate_access_accuracy(
        evaluations,
    )
    refusal_accuracy = calculate_refusal_accuracy(
        evaluations,
    )

    print("Evaluation complete")
    print(f"cases={len(cases)}")
    print(f"hit@1={hit_at_1:.3f}")
    print(f"hit@3={hit_at_3:.3f}")
    print(f"hit@5={hit_at_5:.3f}")
    print(f"mrr={mrr:.3f}")
    print(f"public_access_accuracy={access_accuracy:.3f}")
    print(f"refusal_accuracy={refusal_accuracy:.3f}")
    print(f"results={RESULTS_PATH}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
