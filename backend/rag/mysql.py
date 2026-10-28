"""Document evidence in MySQL, with exact cosine ranking per document."""

import math

from sqlalchemy import JSON, Integer, String, Text, delete, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.database import Base, SessionLocal
from backend.schemas.workflow import EvidenceChunk
from backend.services.documents import DocumentChunk
from backend.vector.embedding import embedding_service


class EmbeddingContract(Base):
    __tablename__ = "embedding_contracts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(255), nullable=False)
    model: Mapped[str] = mapped_column(String(1024), nullable=False)
    dimension: Mapped[int] = mapped_column(Integer, nullable=False)


class DocumentEmbeddingChunk(Base):
    __tablename__ = "document_embedding_chunks"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_type: Mapped[str] = mapped_column(String(20), primary_key=True)
    chunk_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    section: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(JSON, nullable=False)


def _scope(user_id, document_id, document_type):
    if document_type not in {"jd", "resume"}:
        raise ValueError("document_type must be one of ['jd', 'resume']")
    ids = []
    for value, name in ((user_id, "user_id"), (document_id, "document_id")):
        if isinstance(value, bool):
            raise ValueError(f"{name} must be an integer")
        try:
            value = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be an integer") from exc
        if value < 0:
            raise ValueError(f"{name} must be non-negative")
        ids.append(value)
    return (
        DocumentEmbeddingChunk.user_id == ids[0],
        DocumentEmbeddingChunk.document_id == ids[1],
        DocumentEmbeddingChunk.document_type == document_type,
    )


class MySQLRagStore:
    def __init__(self, *, session_factory=None, embedding_client=None):
        self.session_factory = session_factory or SessionLocal
        self.embedding_client = embedding_client or embedding_service

    @staticmethod
    def _contract_statement(expected, dialect_name):
        if dialect_name == "sqlite":
            return (
                sqlite_insert(EmbeddingContract).values(id=1, **expected)
                .on_conflict_do_nothing(index_elements=["id"])
            )
        return (
            mysql_insert(EmbeddingContract).values(id=1, **expected)
            .on_duplicate_key_update(id=EmbeddingContract.id)
        )

    def _check_contract(self, session, dimension):
        expected = {**self.embedding_client.contract, "dimension": dimension}
        # Write first: MySQL's default repeatable-read then sees the winning row.
        session.execute(self._contract_statement(expected, session.get_bind().dialect.name))
        stored = session.get(EmbeddingContract, 1)
        if any(getattr(stored, key) != value for key, value in expected.items()):
            raise RuntimeError(
                "Embedding configuration changed; clear document embeddings and "
                "the embedding contract, then reparse documents"
            )

    def replace_document_chunks(
        self, *, user_id: int, document_id: int, chunks: list[DocumentChunk]
    ) -> None:
        if not chunks:
            return
        document_types = {chunk.document_type for chunk in chunks}
        if len(document_types) != 1:
            raise ValueError("all chunks must have the same document_type")
        document_type = document_types.pop()
        scope = _scope(user_id, document_id, document_type)
        texts = [
            str(chunk.metadata.get("embedding_text") or chunk.metadata.get("normalized_text") or chunk.text)
            for chunk in chunks
        ]
        vectors = self.embedding_client.embed_many(texts)
        if (
            len(vectors) != len(chunks)
            or not vectors
            or not vectors[0]
            or any(len(vector) != len(vectors[0]) for vector in vectors)
        ):
            raise RuntimeError("Embedding service returned invalid vectors")
        with self.session_factory() as session, session.begin():
            self._check_contract(session, len(vectors[0]))
            existing = {
                row.chunk_id: row
                for row in session.scalars(select(DocumentEmbeddingChunk).where(*scope))
            }
            for chunk, vector in zip(chunks, vectors, strict=True):
                row = existing.pop(chunk.id, None)
                if row is None:
                    row = DocumentEmbeddingChunk(
                        user_id=int(user_id), document_id=int(document_id),
                        document_type=document_type, chunk_id=chunk.id,
                    )
                    session.add(row)
                row.filename = chunk.filename
                row.page_number = int(chunk.page_number)
                row.section = chunk.section
                row.chunk_index = int(chunk.chunk_index)
                row.text = chunk.text
                row.embedding = vector
            for row in existing.values():
                session.delete(row)

    @staticmethod
    def _search_statement(user_id, document_id):
        return (
            select(DocumentEmbeddingChunk)
            .where(*_scope(user_id, document_id, "resume"))
        )

    def search_resume_evidence(
        self, *, user_id: int, document_id: int, query: str, top_k: int = 4
    ) -> list[EvidenceChunk]:
        top_k = int(top_k)
        if top_k <= 0:
            return []
        vector = self.embedding_client.embed(query)
        if not vector:
            raise RuntimeError("Embedding service returned invalid vectors")
        with self.session_factory() as session, session.begin():
            self._check_contract(session, len(vector))
            rows = session.scalars(self._search_statement(user_id, document_id))
            # Each query is scoped to one resume; its chunks fit in memory.
            query_norm = math.sqrt(sum(value * value for value in vector))
            ranked = []
            for row in rows:
                norm = query_norm * math.sqrt(
                    sum(value * value for value in row.embedding)
                )
                similarity = (
                    sum(a * b for a, b in zip(vector, row.embedding, strict=True)) / norm
                    if norm else 0.0
                )
                ranked.append((row, similarity))
            ranked.sort(key=lambda item: (-item[1], item[0].chunk_id))
            return [
                EvidenceChunk(
                    chunk_id=row.chunk_id, filename=row.filename,
                    page_number=row.page_number, section=row.section, text=row.text,
                    score=max(-1.0, min(1.0, similarity)),
                )
                for row, similarity in ranked[:top_k]
            ]

    def delete_document(
        self, *, user_id: int, document_type: str, document_id: int
    ) -> None:
        with self.session_factory() as session, session.begin():
            session.execute(
                delete(DocumentEmbeddingChunk).where(
                    *_scope(user_id, document_id, document_type)
                )
            )
