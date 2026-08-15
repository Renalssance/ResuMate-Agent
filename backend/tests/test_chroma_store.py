import pytest

from backend.rag.chroma import ChromaRagStore
from backend.services.documents import DocumentChunk


class FakeEmbedding:
    contract = {"provider": "fake", "model": "fake-v1"}

    def __init__(self):
        self.calls = []

    def embed_many(self, texts):
        self.calls.extend(texts)
        return [[1.0, 0.0] if "Python" in text else [0.0, 1.0] for text in texts]

    def embed(self, text):
        return [1.0, 0.0]


def chunk(chunk_id, text, *, user_document=21, index=0):
    return DocumentChunk(
        id=chunk_id,
        run_id=0,
        candidate_id=user_document,
        document_type="resume",
        filename="resume.pdf",
        page_number=1,
        section="Projects",
        chunk_index=index,
        text=text,
        metadata={},
    )


def test_replace_search_filter_and_delete(tmp_path):
    store = ChromaRagStore(path=tmp_path / "chroma", embedding_client=FakeEmbedding())
    store.replace_document_chunks(
        user_id=7,
        document_id=21,
        chunks=[chunk("python", "Python APIs"), chunk("java", "Java services", index=1)],
    )
    store.replace_document_chunks(
        user_id=8,
        document_id=22,
        chunks=[chunk("other", "Python for another user", user_document=22)],
    )

    results = store.search_resume_evidence(
        user_id=7, document_id=21, query="Python", top_k=4
    )
    assert [item.chunk_id for item in results] == ["python", "java"]
    assert results[0].score == pytest.approx(1.0)
    assert all(item.chunk_id != "other" for item in results)

    store.replace_document_chunks(
        user_id=7,
        document_id=21,
        chunks=[chunk("python", "Python APIs updated")],
    )
    assert store.collection.get(where=store.document_filter(7, 21, "resume"))["ids"] == ["python"]

    store.delete_document(user_id=7, document_type="resume", document_id=21)
    assert store.collection.get(where=store.document_filter(7, 21, "resume"))["ids"] == []


def test_embedding_contract_mismatch_requires_reindex(tmp_path):
    path = tmp_path / "chroma"
    ChromaRagStore(path=path, embedding_client=FakeEmbedding()).replace_document_chunks(
        user_id=7, document_id=21, chunks=[chunk("python", "Python APIs")]
    )
    incompatible = FakeEmbedding()
    incompatible.contract = {"provider": "fake", "model": "fake-v2"}
    with pytest.raises(RuntimeError, match="remove data/chroma.*reparse"):
        ChromaRagStore(path=path, embedding_client=incompatible).search_resume_evidence(
            user_id=7, document_id=21, query="Python"
        )


def test_chunk_embedding_prefers_embedding_text(tmp_path):
    embedding = FakeEmbedding()
    item = chunk("python", "raw display text")
    item.metadata["embedding_text"] = "Python normalized text"
    ChromaRagStore(
        path=tmp_path / "chroma", embedding_client=embedding
    ).replace_document_chunks(user_id=7, document_id=21, chunks=[item])
    assert embedding.calls == ["Python normalized text"]
