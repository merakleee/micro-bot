from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.config import get_settings


class TextEmbedder:
    def __init__(
        self,
        model_name: str | None = None,
        *,
        model: Any | None = None,
    ) -> None:
        self._model_name = model_name or get_settings().embedding_model
        self._model = model

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("Document texts must be non-empty strings.")
        prefixed_texts = [f"passage: {text.strip()}" for text in texts]
        return self._encode(prefixed_texts)

    def embed_query(self, text: str) -> list[float]:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Query text must be a non-empty string.")
        return self._encode([f"query: {text.strip()}"])[0]

    def _encode(self, texts: list[str]) -> list[list[float]]:
        model = self._get_model()
        vectors = model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        if len(vectors) != len(texts):
            raise ValueError("The embedding model returned an unexpected number of vectors.")

        result = [[float(value) for value in vector] for vector in vectors]
        if not result or not result[0] or any(
            len(vector) != len(result[0]) for vector in result
        ):
            raise ValueError("The embedding model returned invalid vector dimensions.")
        return result

    def _get_model(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        return self._model
