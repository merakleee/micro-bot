from fastapi import APIRouter
from app import registry
from app.ingestion.runtime import get_vector_store
from app.schemas import HealthResponse

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
    # Local Qdrant only allows one open client per storage path in a process.
    # Reuse the application client shared by ingestion and retrieval.
    get_vector_store().check_connection()
