from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateTable

from backend.db.database import Base
from backend.rag.mysql import DocumentEmbeddingChunk, EmbeddingContract, MySQLRagStore
from backend.services.documents import DocumentChunk


class FakeEmbedding:
    contract = {"provider": "fake", "model": "v1"}

    vectors = {
        "Python": [1.0, 0.0],
        "close": [2.0, 2.0],
        "far": [-1.0, 0.0],
        "other": [0.0, 1.0],
    }

    def embed_many(self, texts):
        return [self.vectors[text] for text in texts]

    def embed(self, text):
        return self.embed_many([text])[0]


def chunk(chunk_id, text, *, document_type="resume", embedding_text=None):
    return DocumentChunk(
        id=chunk_id, run_id=0, candidate_id=21, document_type=document_type,
        filename="resume.pdf", page_number=2, section="Projects", chunk_index=0,
        text=text, metadata={"embedding_text": embedding_text} if embedding_text else {},
    )


@pytest.fixture
def store():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[EmbeddingContract.__table__, DocumentEmbeddingChunk.__table__])
    factory = sessionmaker(engine, expire_on_commit=False)
    yield MySQLRagStore(session_factory=factory, embedding_client=FakeEmbedding())
    engine.dispose()


def test_replace_search_metadata_and_delete_preserve_other_scopes(store):
    store.replace_document_chunks(user_id=7, document_id=21, chunks=[chunk("same", "close"), chunk("stale", "far")])
    store.replace_document_chunks(user_id=8, document_id=21, chunks=[chunk("same", "Python")])
    store.replace_document_chunks(user_id=7, document_id=22, chunks=[chunk("same", "Python")])
    store.replace_document_chunks(user_id=7, document_id=21, chunks=[chunk("same", "Python", document_type="jd")])
    result = store.search_resume_evidence(user_id=7, document_id=21, query="Python", top_k=1)
    assert len(result) == 1
    assert result[0].model_dump() == {
        "chunk_id": "same", "filename": "resume.pdf", "page_number": 2,
        "section": "Projects", "text": "close", "score": pytest.approx(2 ** -0.5),
    }

    store.replace_document_chunks(user_id=7, document_id=21, chunks=[chunk("same", "updated raw text", embedding_text="Python")])
    assert [(item.chunk_id, item.text) for item in store.search_resume_evidence(user_id=7, document_id=21, query="Python")] == [("same", "updated raw text")]
    store.delete_document(user_id=7, document_id=21, document_type="resume")
    assert store.search_resume_evidence(user_id=7, document_id=21, query="Python") == []
    assert len(store.search_resume_evidence(user_id=8, document_id=21, query="Python")) == 1
    assert len(store.search_resume_evidence(user_id=7, document_id=22, query="Python")) == 1
    with store.session_factory() as session:
        assert session.scalar(select(DocumentEmbeddingChunk).where(DocumentEmbeddingChunk.document_type == "jd")) is not None


def test_search_uses_exact_cosine_order_and_top_k(store):
    store.replace_document_chunks(user_id=7, document_id=21, chunks=[chunk("far", "far"), chunk("close", "close"), chunk("best", "Python")])
    result = store.search_resume_evidence(user_id=7, document_id=21, query="Python", top_k=2)
    assert [item.chunk_id for item in result] == ["best", "close"]
    assert [item.score for item in result] == pytest.approx([1.0, 2 ** -0.5])


@pytest.mark.parametrize("changed", [{"provider": "other", "model": "v1"}, {"provider": "fake", "model": "v2"}, None])
def test_contract_mismatch_rejects_write_and_search_without_losing_chunks(store, changed):
    store.replace_document_chunks(user_id=7, document_id=21, chunks=[chunk("kept", "Python")])
    incompatible = FakeEmbedding()
    if changed is None:
        incompatible.vectors = {"Python": [1.0, 0.0, 0.0]}
    else:
        incompatible.contract = changed
    other = MySQLRagStore(session_factory=store.session_factory, embedding_client=incompatible)
    with pytest.raises(RuntimeError, match="reparse"):
        other.replace_document_chunks(user_id=7, document_id=21, chunks=[chunk("new", "Python")])
    with pytest.raises(RuntimeError, match="reparse"):
        other.search_resume_evidence(user_id=7, document_id=21, query="Python")
    assert [item.chunk_id for item in store.search_resume_evidence(user_id=7, document_id=21, query="Python")] == ["kept"]


def test_empty_replace_is_noop_and_failed_replace_is_atomic(store):
    store.replace_document_chunks(user_id=7, document_id=21, chunks=[chunk("kept", "Python")])
    store.replace_document_chunks(user_id=7, document_id=21, chunks=[])
    invalid = chunk("new", "Python")
    object.__setattr__(invalid, "page_number", "invalid")
    with pytest.raises(ValueError):
        store.replace_document_chunks(user_id=7, document_id=21, chunks=[chunk("kept", "far"), invalid])
    result = store.search_resume_evidence(user_id=7, document_id=21, query="Python")
    assert [(item.chunk_id, item.text) for item in result] == [("kept", "Python")]


def test_mysql_scoped_query_and_atomic_contract_compile():
    compiled = MySQLRagStore._search_statement(7, 21).compile(dialect=mysql.dialect())
    sql = str(compiled)
    assert "document_embedding_chunks.user_id =" in sql
    assert "document_embedding_chunks.document_id =" in sql
    assert "document_embedding_chunks.document_type =" in sql
    assert "LIMIT" not in sql
    assert set(compiled.params.values()) == {7, 21, "resume"}
    ddl = str(CreateTable(DocumentEmbeddingChunk.__table__).compile(dialect=mysql.dialect()))
    assert "embedding JSON NOT NULL" in ddl
    contract = MySQLRagStore._contract_statement({"provider": "fake", "model": "v1", "dimension": 2}, "mysql").compile(dialect=mysql.dialect())
    assert "ON DUPLICATE KEY UPDATE id = embedding_contracts.id" in str(contract)
    assert contract.params == {"id": 1, "provider": "fake", "model": "v1", "dimension": 2}


def test_concurrent_first_uploads_initialize_one_contract(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'concurrent.db'}")
    Base.metadata.create_all(engine, tables=[EmbeddingContract.__table__, DocumentEmbeddingChunk.__table__])
    factory = sessionmaker(engine, expire_on_commit=False, autoflush=False)
    start = Barrier(2)

    class SimultaneousEmbedding(FakeEmbedding):
        def embed_many(self, texts):
            start.wait(timeout=5)
            return super().embed_many(texts)

    def upload(user_id):
        store = MySQLRagStore(session_factory=factory, embedding_client=SimultaneousEmbedding())
        store.replace_document_chunks(user_id=user_id, document_id=21, chunks=[chunk("same", "Python")])

    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            list(workers.map(upload, [7, 8]))
        with factory() as session:
            assert len(session.scalars(select(EmbeddingContract)).all()) == 1
            assert len(session.scalars(select(DocumentEmbeddingChunk)).all()) == 2
    finally:
        engine.dispose()
