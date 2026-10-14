import math
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.chdir(PROJECT_ROOT)
os.environ.setdefault(
    "HF_HOME",
    str(PROJECT_ROOT / "data" / "huggingface-cache"),
)
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings
from app.embeddings import TextEmbedder


def main() -> int:
    settings = get_settings()
    embedder = TextEmbedder()
    passage = "Micro Club organizes scientific and technology events."
    question = "What does Micro Club organize?"

    print(f"Loading model: {settings.embedding_model}")
    print(f"Hugging Face cache: {os.environ['HF_HOME']}")
    print("The first run may download the model weights.")

    try:
        document_vectors = embedder.embed_documents([passage])
        query_vector = embedder.embed_query(question)
    except Exception as exc:
        print(f"FAIL: model load or inference failed: {type(exc).__name__}: {exc}")
        return 1

    document_vector = document_vectors[0]
    dimensions_match = len(document_vector) == len(query_vector)
    all_values = document_vector + query_vector
    finite = all(math.isfinite(value) for value in all_values)
    document_norm = math.sqrt(sum(value * value for value in document_vector))
    query_norm = math.sqrt(sum(value * value for value in query_vector))
    normalized = math.isclose(document_norm, 1.0, abs_tol=1e-3) and math.isclose(
        query_norm, 1.0, abs_tol=1e-3
    )

    checks = {
        "one document vector returned": len(document_vectors) == 1,
        "document and query dimensions match": dimensions_match,
        "vectors contain finite values": finite,
        "vectors are normalized": normalized,
    }
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
    print(f"Vector dimensions: {len(document_vector)}")
    print(f"Document vector norm: {document_norm:.6f}")
    print(f"Query vector norm: {query_norm:.6f}")
    return int(not all(checks.values()))


if __name__ == "__main__":
    raise SystemExit(main())
