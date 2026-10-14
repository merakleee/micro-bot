from functools import lru_cache

from app.embeddings import TextEmbedder
from app.vector_store import QdrantVectorStore


@lru_cache
def get_embedder() -> TextEmbedder:
    return TextEmbedder()


@lru_cache
def get_vector_store() -> QdrantVectorStore:
    return QdrantVectorStore()
