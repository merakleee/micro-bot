from fastapi import APIRouter
from app import registry
from app.schemas import HealthResponse
from app.vector_store import QdrantVectorStore

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health():
    status = "ok"
    try:
        documents = registry.count_ready_documents()
    except Exception:
        documents = 0
        status = "degraded"

    try:
        _check_vector_store()
    except Exception:
        status = "degraded"

    return HealthResponse(status=status, documents=documents)


def _check_vector_store() -> None:
    store = QdrantVectorStore()
    try:
        store.check_connection()
    finally:
        store.close()
