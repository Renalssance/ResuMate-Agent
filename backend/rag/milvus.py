from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Protocol

from pymilvus import DataType, MilvusClient

from backend.schemas.workflow import EvidenceChunk
from backend.services.documents import DocumentChunk
from backend.vector.embedding import embedding_service


DOCUMENT_COLLECTION = "document_chunks"
ARTIFACT_COLLECTION = "analysis_artifacts"
PROFILE_COLLECTION = "document_profiles"
DOCUMENT_TYPES = {"jd", "resume"}

DOCUMENT_FIELD_TYPES = {
    "id": DataType.VARCHAR,
    "embedding": DataType.FLOAT_VECTOR,
    "user_id": DataType.INT64,
    "document_id": DataType.INT64,
    "run_id": DataType.INT64,
    "candidate_id": DataType.INT64,
    "document_type": DataType.VARCHAR,
    "filename": DataType.VARCHAR,
    "page_number": DataType.INT64,
    "section": DataType.VARCHAR,
    "chunk_index": DataType.INT64,
    "text": DataType.VARCHAR,
    "metadata": DataType.JSON,
}
ARTIFACT_FIELD_TYPES = {
    "id": DataType.VARCHAR,
    "embedding": DataType.FLOAT_VECTOR,
    "user_id": DataType.INT64,
    "run_id": DataType.INT64,
    "candidate_id": DataType.INT64,
    "artifact_type": DataType.VARCHAR,
    "summary": DataType.VARCHAR,
    "content": DataType.JSON,
    "created_at": DataType.VARCHAR,
}
PROFILE_FIELD_TYPES = {
    "id": DataType.VARCHAR,
    "embedding": DataType.FLOAT_VECTOR,
    "user_id": DataType.INT64,
    "document_id": DataType.INT64,
    "document_type": DataType.VARCHAR,
    "summary": DataType.VARCHAR,
    "content": DataType.JSON,
}


class EmbeddingClient(Protocol):
    def embed(self, text: str) -> list[float]: ...


class EmbeddingAdapter:
    def embed(self, text: str) -> list[float]:
        return embedding_service.embed(text)


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


def _document_type(value: str) -> str:
    if value not in DOCUMENT_TYPES:
        raise ValueError(f"document_type must be one of {sorted(DOCUMENT_TYPES)}")
    return value


def _vector_dimension(vector: list[float]) -> int:
    dimension = len(vector)
    if dimension <= 0:
        raise RuntimeError("Embedding service returned an empty vector")
    return dimension


def _described_fields(description: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(field.get("name")): field
        for field in description.get("fields", [])
        if isinstance(field, dict) and field.get("name")
    }


def _described_dimension(field: dict[str, Any]) -> int | None:
    candidates = [
        field.get("dim"),
        (field.get("params") or {}).get("dim"),
        (field.get("type_params") or {}).get("dim"),
    ]
    for candidate in candidates:
        if candidate is not None:
            try:
                return int(candidate)
            except (TypeError, ValueError):
                continue
    return None


def _type_matches(actual: Any, expected: DataType) -> bool:
    if actual == expected:
        return True
    try:
        if int(actual) == int(expected):
            return True
    except (TypeError, ValueError):
        pass
    return str(actual).upper().split(".")[-1] == expected.name


class MilvusRagStore:
    def __init__(
        self,
        *,
        uri: str | None = None,
        token: str | None = None,
        embedding_client: EmbeddingClient | None = None,
        client: MilvusClient | None = None,
    ) -> None:
        self.uri = uri or os.getenv("MILVUS_URI", "http://localhost:19530")
        self.token = token if token is not None else os.getenv("MILVUS_TOKEN") or None
        self.embedding_client = embedding_client or EmbeddingAdapter()
        self.client = client or MilvusClient(uri=self.uri, token=self.token)
        self._validated_dimensions: dict[str, int] = {}

    def ensure_collections(self, dimension: int) -> None:
        self._ensure_document_chunks(dimension)
        self._ensure_analysis_artifacts(dimension)
        self._ensure_document_profiles(dimension)

    def _ensure_document_chunks(self, dimension: int) -> None:
        if self._validate_existing_collection(
            DOCUMENT_COLLECTION,
            DOCUMENT_FIELD_TYPES,
            dimension,
        ):
            return
        schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=256)
        schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=dimension)
        schema.add_field("user_id", DataType.INT64)
        schema.add_field("document_id", DataType.INT64)
        schema.add_field("run_id", DataType.INT64)
        schema.add_field("candidate_id", DataType.INT64)
        schema.add_field("document_type", DataType.VARCHAR, max_length=32)
        schema.add_field("filename", DataType.VARCHAR, max_length=512)
        schema.add_field("page_number", DataType.INT64)
        schema.add_field("section", DataType.VARCHAR, max_length=256)
        schema.add_field("chunk_index", DataType.INT64)
        schema.add_field("text", DataType.VARCHAR, max_length=8192)
        schema.add_field("metadata", DataType.JSON)
        self._create_collection(DOCUMENT_COLLECTION, schema)
        self._validated_dimensions[DOCUMENT_COLLECTION] = dimension

    def _ensure_analysis_artifacts(self, dimension: int) -> None:
        if self._validate_existing_collection(
            ARTIFACT_COLLECTION,
            ARTIFACT_FIELD_TYPES,
            dimension,
        ):
            return
        schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=256)
        schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=dimension)
        schema.add_field("user_id", DataType.INT64)
        schema.add_field("run_id", DataType.INT64)
        schema.add_field("candidate_id", DataType.INT64)
        schema.add_field("artifact_type", DataType.VARCHAR, max_length=64)
        schema.add_field("summary", DataType.VARCHAR, max_length=4096)
        schema.add_field("content", DataType.JSON)
        schema.add_field("created_at", DataType.VARCHAR, max_length=64)
        self._create_collection(ARTIFACT_COLLECTION, schema)
        self._validated_dimensions[ARTIFACT_COLLECTION] = dimension

    def _ensure_document_profiles(self, dimension: int) -> None:
        if self._validate_existing_collection(
            PROFILE_COLLECTION,
            PROFILE_FIELD_TYPES,
            dimension,
        ):
            return
        schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=256)
        schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=dimension)
        schema.add_field("user_id", DataType.INT64)
        schema.add_field("document_id", DataType.INT64)
        schema.add_field("document_type", DataType.VARCHAR, max_length=32)
        schema.add_field("summary", DataType.VARCHAR, max_length=4096)
        schema.add_field("content", DataType.JSON)
        self._create_collection(PROFILE_COLLECTION, schema)
        self._validated_dimensions[PROFILE_COLLECTION] = dimension

    def _create_collection(self, collection_name: str, schema: Any) -> None:
        index_params = self.client.prepare_index_params()
        index_params.add_index("embedding", index_type="AUTOINDEX", metric_type="COSINE")
        self.client.create_collection(
            collection_name=collection_name,
            schema=schema,
            index_params=index_params,
        )

    def _validate_existing_collection(
        self,
        collection_name: str,
        required_fields: dict[str, DataType],
        dimension: int | None = None,
    ) -> bool:
        if not self.client.has_collection(collection_name):
            return False
        if dimension is not None and self._validated_dimensions.get(collection_name) == dimension:
            return True

        description = self.client.describe_collection(collection_name=collection_name)
        fields = _described_fields(description)
        missing = sorted(required_fields.keys() - fields.keys())
        if missing:
            raise RuntimeError(
                f"Milvus collection {collection_name!r} is incompatible; "
                f"missing required fields: {', '.join(missing)}"
            )
        incompatible = [
            f"{name} must be {expected.name}"
            for name, expected in required_fields.items()
            if not _type_matches(fields[name].get("type"), expected)
        ]
        if incompatible:
            raise RuntimeError(
                f"Milvus collection {collection_name!r} is incompatible; "
                + ", ".join(incompatible)
            )
        actual_dimension = _described_dimension(fields["embedding"])
        if actual_dimension is None:
            raise RuntimeError(
                f"Milvus collection {collection_name!r} is incompatible; "
                "embedding dimension is unavailable"
            )
        if dimension is not None and actual_dimension != dimension:
            raise RuntimeError(
                f"Milvus collection {collection_name!r} embedding dimension "
                f"is {actual_dimension}, but the embedding service produced {dimension}"
            )
        if dimension is not None:
            self._validated_dimensions[collection_name] = dimension
        return True

    def index_chunks(
        self,
        *,
        user_id: int,
        document_id: int,
        chunks: list[DocumentChunk],
    ) -> None:
        if not chunks:
            return
        scoped_user_id = _int_id(user_id, "user_id")
        scoped_document_id = _int_id(document_id, "document_id")
        chunk_scope = [
            (
                _int_id(chunk.run_id, "run_id"),
                _int_id(chunk.candidate_id, "candidate_id"),
                _document_type(chunk.document_type),
            )
            for chunk in chunks
        ]
        vectors = [self.embedding_client.embed(chunk.text) for chunk in chunks]
        dimension = _vector_dimension(vectors[0])
        if any(len(vector) != dimension for vector in vectors):
            raise RuntimeError("Embedding service returned inconsistent vector dimensions")
        self.ensure_collections(dimension)
        rows = []
        for chunk, vector, (run_id, candidate_id, document_type) in zip(
            chunks,
            vectors,
            chunk_scope,
            strict=True,
        ):
            rows.append(
                {
                    "id": chunk.id,
                    "embedding": vector,
                    "user_id": scoped_user_id,
                    "document_id": scoped_document_id,
                    "run_id": run_id,
                    "candidate_id": candidate_id,
                    "document_type": document_type,
                    "filename": chunk.filename[:512],
                    "page_number": int(chunk.page_number),
                    "section": chunk.section[:256],
                    "chunk_index": int(chunk.chunk_index),
                    "text": chunk.text[:8192],
                    "metadata": chunk.metadata,
                }
            )
        self.client.upsert(collection_name=DOCUMENT_COLLECTION, data=rows)

    def search_resume_evidence(
        self,
        *,
        user_id: int,
        document_id: int | None = None,
        run_id: int | None = None,
        candidate_id: int | None = None,
        query: str,
        top_k: int = 4,
    ) -> list[EvidenceChunk]:
        scoped_user_id = _int_id(user_id, "user_id")
        vector = self.embedding_client.embed(query)
        self.ensure_collections(_vector_dimension(vector))
        if document_id is not None:
            scoped_document_id = _int_id(document_id, "document_id")
            expr = (
                f"user_id == {scoped_user_id} && document_id == {scoped_document_id} && "
                'document_type == "resume"'
            )
        else:
            scoped_run_id = _int_id(run_id, "run_id")
            scoped_candidate_id = _int_id(candidate_id, "candidate_id")
            expr = (
                f"user_id == {scoped_user_id} && run_id == {scoped_run_id} && "
                f'candidate_id == {scoped_candidate_id} && document_type == "resume"'
            )
        hits = self.client.search(
            collection_name=DOCUMENT_COLLECTION,
            data=[vector],
            limit=int(top_k),
            filter=expr,
            output_fields=["id", "filename", "page_number", "section", "text"],
        )
        return [self._hit_to_evidence(hit) for hit in (hits[0] if hits else [])]

    def persist_document_profile(
        self,
        *,
        user_id: int,
        document_type: str,
        document_id: int,
        summary: str,
        content: dict[str, Any],
    ) -> None:
        scoped_user_id = _int_id(user_id, "user_id")
        scoped_document_id = _int_id(document_id, "document_id")
        scoped_document_type = _document_type(document_type)
        vector = self.embedding_client.embed(
            summary or json.dumps(content, ensure_ascii=False)[:1000]
        )
        self.ensure_collections(_vector_dimension(vector))
        self.client.upsert(
            collection_name=PROFILE_COLLECTION,
            data=[
                {
                    "id": f"{scoped_user_id}:{scoped_document_type}:{scoped_document_id}",
                    "embedding": vector,
                    "user_id": scoped_user_id,
                    "document_id": scoped_document_id,
                    "document_type": scoped_document_type,
                    "summary": summary[:4096],
                    "content": content,
                }
            ],
        )

    def load_document_profile(
        self,
        *,
        user_id: int,
        document_type: str,
        document_id: int,
    ) -> dict[str, Any] | None:
        scoped_user_id = _int_id(user_id, "user_id")
        scoped_document_id = _int_id(document_id, "document_id")
        scoped_document_type = _document_type(document_type)
        if not self._validate_existing_collection(PROFILE_COLLECTION, PROFILE_FIELD_TYPES):
            return None
        rows = self.client.query(
            collection_name=PROFILE_COLLECTION,
            filter=(
                f"user_id == {scoped_user_id} && document_id == {scoped_document_id} && "
                f'document_type == "{scoped_document_type}"'
            ),
            output_fields=["content"],
            limit=1,
        )
        if not rows:
            return None
        content = rows[0].get("content")
        return content if isinstance(content, dict) else None

    def persist_artifact(
        self,
        *,
        user_id: int,
        run_id: int,
        candidate_id: int,
        artifact_type: str,
        summary: str,
        content: dict[str, Any],
    ) -> None:
        scoped_user_id = _int_id(user_id, "user_id")
        scoped_run_id = _int_id(run_id, "run_id")
        scoped_candidate_id = _int_id(candidate_id, "candidate_id")
        vector = self.embedding_client.embed(
            summary or json.dumps(content, ensure_ascii=False)[:1000]
        )
        self.ensure_collections(_vector_dimension(vector))
        artifact_id = (
            f"{scoped_user_id}:{scoped_run_id}:{scoped_candidate_id}:{artifact_type}"
        )
        self.client.upsert(
            collection_name=ARTIFACT_COLLECTION,
            data=[
                {
                    "id": artifact_id,
                    "embedding": vector,
                    "user_id": scoped_user_id,
                    "run_id": scoped_run_id,
                    "candidate_id": scoped_candidate_id,
                    "artifact_type": artifact_type,
                    "summary": summary[:4096],
                    "content": content,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            ],
        )

    def delete_document(
        self,
        *,
        user_id: int,
        document_type: str,
        document_id: int,
    ) -> None:
        scoped_user_id = _int_id(user_id, "user_id")
        scoped_document_id = _int_id(document_id, "document_id")
        scoped_document_type = _document_type(document_type)
        if not self._validate_existing_collection(DOCUMENT_COLLECTION, DOCUMENT_FIELD_TYPES):
            document_chunks_exist = False
        else:
            document_chunks_exist = True
        expr = (
            f"user_id == {scoped_user_id} && document_id == {scoped_document_id} && "
            f'document_type == "{scoped_document_type}"'
        )
        if document_chunks_exist:
            self.client.delete(collection_name=DOCUMENT_COLLECTION, filter=expr)
        if self._validate_existing_collection(PROFILE_COLLECTION, PROFILE_FIELD_TYPES):
            self.client.delete(collection_name=PROFILE_COLLECTION, filter=expr)

    def delete_candidate_artifacts(
        self,
        *,
        user_id: int,
        run_id: int,
        candidate_id: int,
    ) -> None:
        scoped_user_id = _int_id(user_id, "user_id")
        scoped_run_id = _int_id(run_id, "run_id")
        scoped_candidate_id = _int_id(candidate_id, "candidate_id")
        if not self._validate_existing_collection(ARTIFACT_COLLECTION, ARTIFACT_FIELD_TYPES):
            return
        self.client.delete(
            collection_name=ARTIFACT_COLLECTION,
            filter=(
                f"user_id == {scoped_user_id} && run_id == {scoped_run_id} && "
                f"candidate_id == {scoped_candidate_id}"
            ),
        )

    @staticmethod
    def _hit_to_evidence(hit: dict[str, Any]) -> EvidenceChunk:
        entity = hit.get("entity") or {}
        return EvidenceChunk(
            chunk_id=str(entity.get("id") or hit.get("id") or ""),
            filename=str(entity.get("filename") or ""),
            page_number=int(entity.get("page_number") or 0),
            section=str(entity.get("section") or ""),
            text=str(entity.get("text") or ""),
            score=float(hit.get("distance") or hit.get("score") or 0),
        )
