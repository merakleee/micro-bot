"""Benchmark candidate embedding models on the MC corpus (issue #5).

Run from the project root, with the benchmark venv active:

    python -m scripts.benchmark_embeddings                # all models
    python -m scripts.benchmark_embeddings --only e5      # models whose name contains "e5"

Rules (written in docs/decisions.md before any run):
  - same chunks and same questions for every model
  - prefixes exactly as each model card says
  - normalized vectors, cosine similarity (a dot product)
  - hit@3 and MRR at document level, out-of-scope questions not scored
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np

CORPUS_DIR = Path("corpus")
MANIFEST = CORPUS_DIR / "manifest.csv"
QUESTIONS = Path("eval/embedding_questions.csv")
RESULTS_DIR = Path("eval/results")

LANG_CODES = {"English": "en", "French": "fr", "Arabic": "ar"}
TOP_K = 3      # a question is a hit if the right document is in the top 3 chunks
MAX_RANK = 10  # beyond this rank a question counts 0 in MRR

# One entry per candidate. Everything model-specific lives here.
MODELS = [
    {
        "name": "intfloat/multilingual-e5-small",
        "query_prefix": "query: ",
        "passage_prefix": "passage: ",
    },
    {
        "name": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "query_prefix": "",
        "passage_prefix": "",
    },
    {
        "name": "BAAI/bge-m3",
        "query_prefix": "",
        "passage_prefix": "",
    },
]


# ---------------------------------------------------------------- loading

def load_manifest() -> list[dict]:
    with MANIFEST.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_chunks(manifest: list[dict], chunk_size: int, overlap: int) -> list:
    # Imported here so the scoring code below can be tested without the app.
    # Adjust these two imports if your files live elsewhere.
    from app.ingestion.chunking import chunk_text
    from app.ingestion.parsers import parse_document

    chunks = []
    for row in manifest:
        parsed = parse_document(CORPUS_DIR / row["filename"])
        chunks.extend(
            chunk_text(
                parsed.text,
                # the questions file refers to filenames
                doc_id=row["filename"],
                title=row["title"],
                visibility=row["visibility"],
                chunk_size=chunk_size,
                overlap=overlap,
            )
        )
    return chunks


def load_questions() -> tuple[list[dict], list[dict]]:
    with QUESTIONS.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    scored, out_of_scope = [], []
    for r in rows:
        if r["language"] not in LANG_CODES:
            raise ValueError(f"{r['id']}: unknown language {r['language']!r}")
        question = {
            "id": r["id"],
            "question": r["question"].strip(),
            "lang": LANG_CODES[r["language"]],
            "expected": {d for d in r["expected_doc"].split("|") if d},
        }
        if r["type"] == "out_of_scope":
            out_of_scope.append(question)
        elif not question["expected"]:
            raise ValueError(
                f"{r['id']}: scored question without expected_doc")
        else:
            scored.append(question)
    return scored, out_of_scope


def load_model(cfg: dict):
    from sentence_transformers import SentenceTransformer

    # CPU: what a free host gives
    return SentenceTransformer(cfg["name"], device="cpu")


# ---------------------------------------------------------------- scoring

def rank_of_expected(scores: np.ndarray, chunk_docs: list[str], expected: set):
    """1-based position of the first chunk that belongs to an expected document.

    Ties are broken by chunk order (stable sort), so runs are reproducible.
    Returns (rank or None, full ordering).
    """
    order = np.argsort(-scores, kind="stable")
    for position, idx in enumerate(order, start=1):
        if chunk_docs[idx] in expected:
            return position, order
    return None, order


def count_truncated(model, texts: list[str]) -> dict:
    limit = model.max_seq_length
    ids = model.tokenizer(texts, add_special_tokens=True,
                          truncation=False)["input_ids"]
    lengths = [len(x) for x in ids]
    return {
        "limit": limit,
        "truncated": sum(1 for n in lengths if n > limit),
        "max_tokens": max(lengths),
        "median_tokens": int(statistics.median(lengths)),
    }


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    if n == 0:
        return {"n": 0, "hits": 0, "hit_at_3": None, "mrr": None}
    hits = sum(r["hit"] for r in rows)
    return {
        "n": n,
        "hits": hits,
        "hit_at_3": hits / n,
        "mrr": sum(r["rr"] for r in rows) / n,
    }


def evaluate_model(model, cfg, chunks, scored, out_of_scope, doc_langs) -> dict:
    chunk_docs = [c.doc_id for c in chunks]
    passages = [cfg["passage_prefix"] + c.text for c in chunks]

    truncation = count_truncated(model, passages)

    start = time.perf_counter()
    chunk_vecs = model.encode(
        passages, normalize_embeddings=True, batch_size=16,
        show_progress_bar=False, convert_to_numpy=True,
    )
    embed_corpus_s = time.perf_counter() - start

    # the first call is slower than the rest: warm up before timing queries
    model.encode([cfg["query_prefix"] + "warm up"],
                 normalize_embeddings=True, convert_to_numpy=True)

    question_vecs, query_ms = [], []
    for q in scored + out_of_scope:
        start = time.perf_counter()
        vec = model.encode([cfg["query_prefix"] + q["question"]],
                           normalize_embeddings=True, convert_to_numpy=True)[0]
        query_ms.append((time.perf_counter() - start) * 1000)
        question_vecs.append(vec)

    # cosine, vectors are normalized
    sims = np.vstack(question_vecs) @ chunk_vecs.T

    rows, failures = [], []
    for i, q in enumerate(scored):
        rank, order = rank_of_expected(sims[i], chunk_docs, q["expected"])
        hit = rank is not None and rank <= TOP_K
        rr = 1 / rank if rank is not None and rank <= MAX_RANK else 0.0
        same_language = q["lang"] in {doc_langs[d] for d in q["expected"]}
        rows.append({"id": q["id"], "lang": q["lang"], "cross": not same_language,
                     "hit": hit, "rr": rr, "rank": rank,
                     "top1": float(sims[i].max())})
        if not hit:
            failures.append({
                "id": q["id"],
                "question": q["question"],
                "expected": sorted(q["expected"]),
                "rank_of_expected": rank,
                "top3": [(chunk_docs[j], round(float(sims[i][j]), 3)) for j in order[:3]],
            })

    out_of_scope_scores = {
        q["id"]: round(float(sims[len(scored) + k].max()), 3)
        for k, q in enumerate(out_of_scope)
    }

    return {
        "model": cfg["name"],
        "overall": summarize(rows),
        "by_language": {lang: summarize([r for r in rows if r["lang"] == lang])
                        for lang in ("en", "fr", "ar")},
        "same_language": summarize([r for r in rows if not r["cross"]]),
        "cross_language": summarize([r for r in rows if r["cross"]]),
        "truncation": truncation,
        "embed_corpus_s": round(embed_corpus_s, 2),
        "median_query_ms": round(statistics.median(query_ms), 1),
        "out_of_scope_top1": out_of_scope_scores,
        "in_scope_top1": {
            "min": round(min(r["top1"] for r in rows), 3),
            "median": round(statistics.median(r["top1"] for r in rows), 3),
        },
        "failures": failures,
    }


# ---------------------------------------------------------------- output

def pct(group: dict) -> str:
    if group["n"] == 0:
        return "n/a"
    return f"{group['hits']}/{group['n']} ({group['hit_at_3'] * 100:.0f}%)"


def print_result(result: dict, load_s: float) -> None:
    t = result["truncation"]
    print(f"\n=== {result['model']} ===")
    print(
        f"hit@3 overall   : {pct(result['overall'])}   MRR {result['overall']['mrr']:.3f}")
    for lang in ("en", "fr", "ar"):
        print(f"hit@3 {lang}        : {pct(result['by_language'][lang])}")
    print(f"hit@3 same-lang : {pct(result['same_language'])}")
    print(f"hit@3 cross-lang: {pct(result['cross_language'])}")
    print(f"tokens          : median {t['median_tokens']}, max {t['max_tokens']}, "
          f"model limit {t['limit']}, truncated chunks {t['truncated']}")
    print(f"timing          : load {load_s:.1f}s (includes download on first run), "
          f"embed corpus {result['embed_corpus_s']}s, "
          f"median per question {result['median_query_ms']} ms")
    print(f"out-of-scope top-1 similarity: {result['out_of_scope_top1']}")
    inside = result["in_scope_top1"]
    print(
        f"in-scope top-1 similarity    : min {inside['min']}, median {inside['median']}")
    if result["out_of_scope_top1"]:
        worst = max(result["out_of_scope_top1"].values())
        print(f"refusal margin (lowest in-scope top-1 minus highest out-of-scope top-1): "
              f"{inside['min'] - worst:+.3f}  (negative = the two ranges overlap)")
    if result["failures"]:
        print("failures:")
        for f in result["failures"]:
            print(
                f"  {f['id']} expected {f['expected']} (rank {f['rank_of_expected']})")
            print(f"     {f['question']}")
            print(f"     top 3 returned: {f['top3']}")
    else:
        print("failures: none")


def print_comparison(results: list[dict], chunk_count: int) -> None:
    print("\n=== COMPARISON (paste into docs/decisions.md) ===")
    header = ["model", "overall", "EN", "FR", "AR", "cross-lang", "MRR",
              "embed s", "ms/q", "truncated"]
    print(" | ".join(header))
    for r in results:
        print(" | ".join([
            r["model"].split("/")[-1],
            pct(r["overall"]),
            pct(r["by_language"]["en"]),
            pct(r["by_language"]["fr"]),
            pct(r["by_language"]["ar"]),
            pct(r["cross_language"]),
            f"{r['overall']['mrr']:.3f}",
            str(r["embed_corpus_s"]),
            str(r["median_query_ms"]),
            f"{r['truncation']['truncated']}/{chunk_count}",
        ]))


# ---------------------------------------------------------------- main

def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Arabic on a Windows console

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--only", help="run only models whose name contains this text")
    parser.add_argument("--chunk-size", type=int, default=800)
    parser.add_argument("--overlap", type=int, default=120)
    args = parser.parse_args()

    models = [m for m in MODELS if not args.only or args.only.lower()
              in m["name"].lower()]
    if not models:
        sys.exit(f"No model matches --only {args.only!r}")

    manifest = load_manifest()
    doc_langs = {row["filename"]: row["language"] for row in manifest}
    chunks = load_chunks(manifest, args.chunk_size, args.overlap)
    scored, out_of_scope = load_questions()

    print(f"chunk_size={args.chunk_size} overlap={args.overlap}")
    per_doc: dict[str, int] = {}
    for c in chunks:
        per_doc[c.doc_id] = per_doc.get(c.doc_id, 0) + 1
    print(f"chunks: {len(chunks)} in {len(per_doc)} documents")
    for doc, count in per_doc.items():
        print(f"  {doc}: {count}")
    sizes = [len(c.text) for c in chunks]
    print(
        f"chunk length (chars): min {min(sizes)}, median {int(statistics.median(sizes))}, max {max(sizes)}")
    missing = {d for q in scored for d in q["expected"]} - set(per_doc)
    if missing:
        print(f"WARNING: expected documents with no chunks: {sorted(missing)}")
    print(f"questions: {len(scored)} scored, {len(out_of_scope)} out-of-scope")

    first = models[0]
    print("\nprefix check (first model):")
    print(f"  question: {first['query_prefix'] + scored[0]['question']!r}")
    print(f"  chunk   : {(first['passage_prefix'] + chunks[0].text)[:70]!r}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for cfg in models:
        start = time.perf_counter()
        model = load_model(cfg)
        load_s = time.perf_counter() - start

        result = evaluate_model(
            model, cfg, chunks, scored, out_of_scope, doc_langs)
        result["load_s"] = round(load_s, 1)
        result["chunk_size"] = args.chunk_size
        result["overlap"] = args.overlap
        print_result(result, load_s)

        out = RESULTS_DIR / f"embedding_{cfg['name'].split('/')[-1]}.json"
        out.write_text(json.dumps(result, ensure_ascii=False,
                       indent=2), encoding="utf-8")
        results.append(result)
        del model

    print_comparison(results, len(chunks))


if __name__ == "__main__":
    main()
