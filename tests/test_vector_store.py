import pytest
import numpy as np
from qdrant_client import QdrantClient, models
from uuid import uuid4

from app.ingestion.chunking import DocumentChunk
from app.vector_store import QdrantVectorStore


@pytest.fixture
def store():
    client = QdrantClient(":memory:")
    yield QdrantVectorStore(client=client, collection_name="test_chunks")
    client.close()


def chunk(doc_id: str, visibility: str, index: int = 0) -> DocumentChunk:
    return DocumentChunk(
        text=f"text from {doc_id} chunk {index}",
        doc_id=doc_id,
        title=f"Title {doc_id}",
        visibility=visibility,
        chunk_index=index,
    )


def test_public_search_filters_member_perfect_match_before_top_k(store):
    store.add_chunks(
        [
            chunk("private-doc", "members"),
            chunk("public-doc", "public"),
        ],
        [
            [1.0, 0.0],  # exact query match, but members-only
            [0.8, 0.6],
        ],
    )

    results = store.search([1.0, 0.0], access_level="public", limit=1)

    assert len(results) == 1
    assert results[0].doc_id == "public-doc"
    assert results[0].visibility == "public"
    assert all(result.doc_id != "private-doc" for result in results)


def test_member_search_can_return_public_and_members_chunks(store):
    store.add_chunks(
        [chunk("public-doc", "public"), chunk("private-doc", "members")],
        [[1.0, 0.0], [0.9, 0.1]],
    )

    results = store.search([1.0, 0.0], access_level="members", limit=2)

    assert {result.doc_id for result in results} == {"public-doc", "private-doc"}


def test_delete_by_doc_id_removes_only_that_documents_chunks(store):
    store.add_chunks(
        [
            chunk("delete-me", "public", 0),
            chunk("delete-me", "public", 1),
            chunk("keep-me", "public"),
        ],
        [[1.0, 0.0], [0.9, 0.1], [0.8, 0.2]],
    )

    store.delete_by_doc_id("delete-me")
    results = store.search([1.0, 0.0], access_level="public", limit=5)

    assert [result.doc_id for result in results] == ["keep-me"]


def test_add_chunks_returns_count_and_readding_same_chunks_upserts(store):
    document_chunk = chunk("doc", "public")

    assert store.add_chunks([document_chunk], [[1.0, 0.0]]) == 1
    assert store.add_chunks([document_chunk], [[0.0, 1.0]]) == 1
    results = store.search([0.0, 1.0], access_level="public")

    assert len(results) == 1
    assert results[0].doc_id == "doc"
    assert results[0].score == pytest.approx(1.0)


def test_replace_document_chunks_removes_chunks_from_previous_version(store):
    store.add_chunks(
        [
            chunk("doc", "public", 0),
            chunk("doc", "public", 1),
        ],
        [[1.0, 0.0], [0.9, 0.1]],
    )

    assert store.replace_document_chunks(
        "doc",
        [chunk("doc", "public", 0)],
        [[0.0, 1.0]],
    ) == 1

    results = store.search([0.0, 1.0], access_level="public", limit=5)
    assert [(result.doc_id, result.chunk_index) for result in results] == [("doc", 0)]


def test_replace_document_chunks_validates_before_deleting_existing_data(store):
    store.add_chunks([chunk("doc", "public")], [[1.0, 0.0]])

    with pytest.raises(ValueError, match="exactly one embedding"):
        store.replace_document_chunks("doc", [chunk("doc", "public")], [])

    results = store.search([1.0, 0.0], access_level="public")
    assert [result.doc_id for result in results] == ["doc"]


def test_add_chunks_rejects_dimension_mismatch_with_existing_collection(store):
    store.add_chunks([chunk("doc", "public")], [[1.0, 0.0]])

    with pytest.raises(ValueError, match="does not match the existing collection"):
        store.add_chunks([chunk("other", "public")], [[1.0, 0.0, 0.0]])


def test_search_rejects_incomplete_qdrant_payload(store):
    store.add_chunks([chunk("valid", "public")], [[0.0, 1.0]])
    store._client.upsert(
        collection_name="test_chunks",
        points=[
            models.PointStruct(
                id=str(uuid4()),
                vector=[1.0, 0.0],
                payload={"doc_id": "broken", "visibility": "public"},
            )
        ],
        wait=True,
    )

    with pytest.raises(ValueError, match="incomplete payload"):
        store.search([1.0, 0.0], access_level="public")


def test_empty_store_search_returns_no_results(store):
    assert store.search([1.0, 0.0], access_level="public") == []


def test_search_accepts_numpy_query_vectors(store):
    store.add_chunks([chunk("doc", "public")], [np.array([1.0, 0.0])])

    results = store.search(np.array([1.0, 0.0]), access_level="public")

    assert len(results) == 1
    assert results[0].doc_id == "doc"


def test_local_store_persists_data_between_clients(tmp_path):
    storage_path = tmp_path / "qdrant"
    first_client = QdrantClient(path=str(storage_path))
    first_store = QdrantVectorStore(
        client=first_client,
        collection_name="persistent_chunks",
    )
    first_store.add_chunks([chunk("saved-doc", "public")], [[1.0, 0.0]])
    first_client.close()

    second_client = QdrantClient(path=str(storage_path))
    second_store = QdrantVectorStore(
        client=second_client,
        collection_name="persistent_chunks",
    )
    results = second_store.search([1.0, 0.0], access_level="public")
    second_client.close()

    assert [result.doc_id for result in results] == ["saved-doc"]


def test_add_rejects_a_chunk_without_a_matching_embedding(store):
    with pytest.raises(ValueError, match="exactly one embedding"):
        store.add_chunks([chunk("doc", "public")], [])


def test_add_rejects_embeddings_with_different_dimensions(store):
    with pytest.raises(ValueError, match="equal dimensions"):
        store.add_chunks(
            [chunk("doc-a", "public"), chunk("doc-b", "public")],
            [[1.0, 0.0], [1.0]],
        )


def test_add_rejects_invalid_visibility(store):
    with pytest.raises(ValueError, match="visibility must be public or members"):
        store.add_chunks([chunk("doc", "private")], [[1.0, 0.0]])


@pytest.mark.parametrize("access_level", ["admin", "", None])
def test_search_rejects_unknown_access_level(store, access_level):
    with pytest.raises(ValueError, match="access_level must be public or members"):
        store.search([1.0, 0.0], access_level=access_level)


@pytest.mark.parametrize("limit", [0, -1])
def test_search_rejects_non_positive_limit(store, limit):
    with pytest.raises(ValueError, match="limit must be positive"):
        store.search([1.0, 0.0], access_level="public", limit=limit)


def test_search_rejects_empty_embedding(store):
    with pytest.raises(ValueError, match="query_embedding must not be empty"):
        store.search([], access_level="public")
