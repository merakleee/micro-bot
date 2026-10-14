import sys
from types import ModuleType

import numpy as np
import pytest

from app.embeddings import TextEmbedder


class FakeModel:
    def __init__(self):
        self.calls = []

    def encode(self, texts, **kwargs):
        self.calls.append((texts, kwargs))
        return np.array([[1.0, 0.0] for _ in texts])


def test_embed_documents_adds_e5_passage_prefix_and_normalizes():
    model = FakeModel()
    embedder = TextEmbedder(model=model)

    vectors = embedder.embed_documents(["  document one  ", "document two"])

    assert model.calls[0][0] == ["passage: document one", "passage: document two"]
    assert model.calls[0][1]["normalize_embeddings"] is True
    assert vectors == [[1.0, 0.0], [1.0, 0.0]]


def test_embed_query_adds_e5_query_prefix():
    model = FakeModel()

    vector = TextEmbedder(model=model).embed_query("  where is the club?  ")

    assert model.calls[0][0] == ["query: where is the club?"]
    assert vector == [1.0, 0.0]


def test_empty_document_list_returns_without_loading_or_calling_model():
    model = FakeModel()

    assert TextEmbedder(model=model).embed_documents([]) == []
    assert model.calls == []


@pytest.mark.parametrize("texts", [[""], ["valid", "   "]])
def test_embed_documents_rejects_empty_text(texts):
    model = FakeModel()

    with pytest.raises(ValueError, match="non-empty strings"):
        TextEmbedder(model=model).embed_documents(texts)

    assert model.calls == []


@pytest.mark.parametrize("text", ["", "   ", None])
def test_embed_query_rejects_empty_text(text):
    model = FakeModel()

    with pytest.raises(ValueError, match="non-empty string"):
        TextEmbedder(model=model).embed_query(text)

    assert model.calls == []


def test_model_is_loaded_lazily_and_reused(monkeypatch):
    model = FakeModel()
    loaded_names = []

    class FakeSentenceTransformer:
        def __init__(self, model_name):
            loaded_names.append(model_name)

        def encode(self, texts, **kwargs):
            return model.encode(texts, **kwargs)

    fake_module = ModuleType("sentence_transformers")
    fake_module.SentenceTransformer = FakeSentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    embedder = TextEmbedder("test-model")

    embedder.embed_query("first")
    embedder.embed_query("second")

    assert loaded_names == ["test-model"]
    assert len(model.calls) == 2
