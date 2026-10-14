from __future__ import annotations

import csv
from pathlib import Path

from app.ingestion.pipeline import ingest_file
from app.ingestion.runtime import get_embedder, get_vector_store


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    manifest_path = root / "corpus" / "manifest.csv"

    ingested = skipped = failed = 0
    embedder = get_embedder()
    store = get_vector_store()

    with manifest_path.open(newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            path = root / "corpus" / row["filename"]

            try:
                _, was_skipped = ingest_file(
                    path,
                    title=row["title"],
                    visibility=row["visibility"],
                    embedder=embedder,
                    store=store,
                )
                if was_skipped:
                    skipped += 1
                else:
                    ingested += 1
            except Exception as exc:
                failed += 1
                print(f"FAILED {path}: {exc}")

    print(
        f"ingested={ingested} skipped={skipped} failed={failed}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
