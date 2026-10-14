from fastapi.testclient import TestClient

from app.main import create_app
from app.routes import health


class HealthyVectorStore:
    def __init__(self):
        self.closed = False

    def check_connection(self):
        return None

    def close(self):
        self.closed = True


def test_health_is_ok_and_reports_ready_document_count(monkeypatch):
    store = HealthyVectorStore()
    monkeypatch.setattr(health.registry, "count_ready_documents", lambda: 3)
    monkeypatch.setattr(health, "QdrantVectorStore", lambda: store)

    response = TestClient(create_app()).get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "documents": 3}
    assert store.closed


def test_health_is_degraded_when_database_is_unreachable(monkeypatch):
    store = HealthyVectorStore()

    def unavailable_database():
        raise OSError("database unavailable")

    monkeypatch.setattr(health.registry, "count_ready_documents", unavailable_database)
    monkeypatch.setattr(health, "QdrantVectorStore", lambda: store)

    response = TestClient(create_app()).get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "degraded", "documents": 0}
    assert store.closed


def test_health_is_degraded_when_vector_store_is_unreachable(monkeypatch):
    class UnavailableVectorStore(HealthyVectorStore):
        def check_connection(self):
            raise OSError("vector store unavailable")

    store = UnavailableVectorStore()
    monkeypatch.setattr(health.registry, "count_ready_documents", lambda: 3)
    monkeypatch.setattr(health, "QdrantVectorStore", lambda: store)

    response = TestClient(create_app()).get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "degraded", "documents": 3}
    assert store.closed
