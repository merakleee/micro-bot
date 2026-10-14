from __future__ import annotations
from app.retrieval import retrieve
from app.ingestion.runtime import get_embedder, get_vector_store
from app.errors import AppError

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect vector retrieval without calling the LLM."
    )
    parser.add_argument(
        "query",
        help="Question or search text.",
    )
    parser.add_argument(
        "--access-level",
        choices=("public", "members"),
        default="public",
        help="Visibility level used during retrieval.",
    )
    parser.add_argument(
        "-k",
        type=int,
        default=5,
        help="Maximum number of chunks to display.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        response = retrieve(
            args.query,
            args.access_level,
            args.k,
            embedder=get_embedder(),
            store=get_vector_store(),
        )
    except AppError as exc:
        print(f"REFUSED [{exc.code}]: {exc.message}")
        return 1
    except Exception as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}")
        return 1

    print(f"Query: {response.query}")
    print(f"Access level: {args.access_level}")
    print(f"Threshold: {response.threshold:.4f}")
    print(f"Best score: {response.best_score:.4f}")
    print(f"Results: {len(response.results)}")

    for index, result in enumerate(response.results, start=1):
        print()
        print(f"[{index}] score={result.score:.4f}")
        print(f"doc_id={result.doc_id}")
        print(f"title={result.title}")
        print(f"visibility={result.visibility}")
        print(f"chunk_index={result.chunk_index}")
        print("text:")
        print(result.text)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
