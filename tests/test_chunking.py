import pytest

from app.ingestion.chunking import chunk_text, normalize_text


def test_normalize_text():
    result = normalize_text(" A\t B\r\n\r\n\r\nC ")

    assert result == "A B\n\nC"


def test_empty_text_returns_no_chunks():
    chunks = chunk_text(
        " \n\n ",
        doc_id="d1",
        title="Test",
        visibility="public",
        chunk_size=100,
        overlap=10,
    )

    assert chunks == []


def test_every_chunk_has_metadata():
    chunks = chunk_text(
        "# Title\n\nThis is content.",
        doc_id="d42",
        title="Guide",
        visibility="members",
        chunk_size=100,
        overlap=10,
    )

    assert chunks

    for chunk in chunks:
        assert chunk.text
        assert chunk.doc_id == "d42"
        assert chunk.title == "Guide"
        assert chunk.visibility == "members"


def test_large_text_is_split():
    chunks = chunk_text(
        "A" * 250,
        doc_id="d1",
        title="Large",
        visibility="public",
        chunk_size=100,
        overlap=20,
    )

    assert len(chunks) > 1
    assert all(len(chunk.text) <= 100 for chunk in chunks)


def test_invalid_overlap_is_rejected():
    with pytest.raises(
        ValueError,
        match="overlap must be between 0 and chunk_size",
    ):
        chunk_text(
            "Some text",
            doc_id="d1",
            title="Test",
            visibility="public",
            chunk_size=100,
            overlap=100,
        )


def test_chunks_have_overlap():
    text = "0123456789" * 30

    chunks = chunk_text(
        text,
        doc_id="d1",
        title="Overlap",
        visibility="public",
        chunk_size=100,
        overlap=20,
    )

    assert len(chunks) >= 2
    assert chunks[0].text[-20:] == chunks[1].text[:20]
