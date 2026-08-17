import os
from pathlib import Path

os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

import chromadb

from backend.schemas.workflow import EvidenceChunk
from backend.services.documents import DocumentChunk
from backend.vector.embedding import embedding_service


DOCUMENT_COLLECTION = "document_chunks"
DOCUMENT_TYPES = {"jd", "resume"}


def _int_id(value: int | str, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if result < 0:
        raise ValueError(f"{name} must be non-negative")
    return result


class ChromaRagStore:
    def __init__(self, *, path=None, embedding_client=None, client=None):
        self.path = Path(path or os.getenv("CHROMA_PATH") or "data/chroma")
        self.embedding_client = embedding_client or embedding_service
        self.client = client or chromadb.PersistentClient(path=str(self.path))
        self._collection = None

    @property
    def collection(self):
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                name=DOCUMENT_COLLECTION,
                embedding_function=None,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    @staticmethod
    def document_filter(user_id: int, document_id: int, document_type: str) -> dict:
        if document_type not in DOCUMENT_TYPES:
            raise ValueError(f"document_type must be one of {sorted(DOCUMENT_TYPES)}")
        return {
            "$and": [
                {"user_id": _int_id(user_id, "user_id")},
                {"document_id": _int_id(document_id, "document_id")},
                {"document_type": document_type},
            ]
        }

    def _collection_for_dimension(self, dimension: int):
        contract = self.embedding_client.contract
        expected = {
            "hnsw:space": "cosine",
            "embedding_provider": contract["provider"],
            "embedding_model": contract["model"],
            "embedding_dimension": dimension,
        }
        collection = self.client.get_or_create_collection(
            name=DOCUMENT_COLLECTION,
            embedding_function=None,
            metadata=expected,
        )
        actual = collection.metadata or {}
        mismatches = {
            key: (actual.get(key), value)
            for key, value in expected.items()
            if key in actual and actual.get(key) != value
        }
        missing = expected.keys() - actual.keys()
        if mismatches or (missing and collection.count()):
            raise RuntimeError(
                "Embedding configuration changed; remove data/chroma and reparse documents"
            )
        if missing:
            collection.modify(
                metadata={key: value for key, value in expected.items() if key != "hnsw:space"}
            )
        self._collection = collection
        return collection

    def replace_document_chunks(
        self, *, user_id: int, document_id: int, chunks: list[DocumentChunk]
    ) -> None:
        if not chunks:
            return
        document_types = {chunk.document_type for chunk in chunks}
        if len(document_types) != 1:
            raise ValueError("all chunks must have the same document_type")
        document_type = document_types.pop()
        where = self.document_filter(user_id, document_id, document_type)
        texts = [
            str(
                chunk.metadata.get("embedding_text")
                or chunk.metadata.get("normalized_text")
                or chunk.text
            )
            for chunk in chunks
        ]
        vectors = self.embedding_client.embed_many(texts)
        if len(vectors) != len(chunks) or not vectors or not vectors[0]:
            raise RuntimeError("Embedding service returned invalid vectors")
        collection = self._collection_for_dimension(len(vectors[0]))
        existing_ids = set(collection.get(where=where, include=[])["ids"])
        new_ids = [chunk.id for chunk in chunks]
        collection.upsert(
            ids=new_ids,
            embeddings=vectors,
            documents=[chunk.text for chunk in chunks],
            metadatas=[
                {
                    "user_id": _int_id(user_id, "user_id"),
                    "document_id": _int_id(document_id, "document_id"),
                    "document_type": document_type,
                    "filename": chunk.filename,
                    "page_number": int(chunk.page_number),
                    "section": chunk.section,
                    "chunk_index": int(chunk.chunk_index),
                }
                for chunk in chunks
            ],
        )
        stale_ids = sorted(existing_ids - set(new_ids))
        if stale_ids:
            collection.delete(ids=stale_ids)

    def search_resume_evidence(
        self, *, user_id: int, document_id: int, query: str, top_k: int = 4
    ) -> list[EvidenceChunk]:
        vector = self.embedding_client.embed(query)
        collection = self._collection_for_dimension(len(vector))
        result = collection.query(
            query_embeddings=[vector],
            where=self.document_filter(user_id, document_id, "resume"),
            n_results=int(top_k),
            include=["documents", "metadatas", "distances"],
        )
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        return [
            EvidenceChunk(
                chunk_id=str(chunk_id),
                filename=str((metadata or {}).get("filename") or ""),
                page_number=int((metadata or {}).get("page_number") or 0),
                section=str((metadata or {}).get("section") or ""),
                text=str(document or ""),
                score=max(-1.0, min(1.0, 1.0 - float(distance))),
            )
            for chunk_id, document, metadata, distance in zip(
                ids, documents, metadatas, distances, strict=True
            )
        ]

    def delete_document(
        self, *, user_id: int, document_type: str, document_id: int
    ) -> None:
        self.collection.delete(
            where=self.document_filter(user_id, document_id, document_type)
        )
