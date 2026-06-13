from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from openai import OpenAI
from pymilvus import DataType, MilvusClient

from backend.schemas.workflow import EvidenceChunk
from backend.services.documents import DocumentChunk


DOCUMENT_COLLECTION = "document_chunks"
ARTIFACT_COLLECTION = "analysis_artifacts"


class OpenAIEmbeddingClient:
    def __init__(self) -> None:
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("ARK_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("BASE_URL") or None
        self.model = os.getenv("EMBEDDING_MODEL")
        self.dimension_value = int(os.getenv("EMBEDDING_DIMENSION", "0") or "0")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for embeddings")
        if not self.model:
            raise RuntimeError("EMBEDDING_MODEL is required for embeddings")
        if self.dimension_value <= 0:
            raise RuntimeError("EMBEDDING_DIMENSION is required for Milvus schema")
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    @property
    def dimension(self) -> int:
        return self.dimension_value

    def embed(self, text: str) -> list[float]:
        response = self.client.embeddings.create(model=self.model, input=text)
        return [float(value) for value in response.data[0].embedding]


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


class MilvusRagStore:
    def __init__(
        self,
        *,
        uri: str | None = None,
        token: str | None = None,
        embedding_client: OpenAIEmbeddingClient | None = None,
        client: MilvusClient | None = None,
    ) -> None:
        self.uri = uri or os.getenv("MILVUS_URI", "http://localhost:19530")
        self.token = token if token is not None else os.getenv("MILVUS_TOKEN") or None
        self.embedding_client = embedding_client or OpenAIEmbeddingClient()
        self.client = client or MilvusClient(uri=self.uri, token=self.token)

    @property
    def dimension(self) -> int:
        return self.embedding_client.dimension

    def ensure_collections(self) -> None:
        self._ensure_document_chunks()
        self._ensure_analysis_artifacts()

    def _ensure_document_chunks(self) -> None:
        if self.client.has_collection(DOCUMENT_COLLECTION):
            return
        schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=256)
        schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=self.dimension)
        schema.add_field("run_id", DataType.VARCHAR, max_length=128)
        schema.add_field("candidate_id", DataType.VARCHAR, max_length=128)
        schema.add_field("document_type", DataType.VARCHAR, max_length=32)
        schema.add_field("filename", DataType.VARCHAR, max_length=512)
        schema.add_field("page_number", DataType.INT64)
        schema.add_field("section", DataType.VARCHAR, max_length=256)
        schema.add_field("chunk_index", DataType.INT64)
        schema.add_field("text", DataType.VARCHAR, max_length=8192)
        schema.add_field("metadata", DataType.JSON)
        index_params = self.client.prepare_index_params()
        index_params.add_index("embedding", index_type="AUTOINDEX", metric_type="COSINE")
        self.client.create_collection(DOCUMENT_COLLECTION, schema=schema, index_params=index_params)

    def _ensure_analysis_artifacts(self) -> None:
        if self.client.has_collection(ARTIFACT_COLLECTION):
            return
        schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=256)
        schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=self.dimension)
        schema.add_field("run_id", DataType.VARCHAR, max_length=128)
        schema.add_field("candidate_id", DataType.VARCHAR, max_length=128)
        schema.add_field("artifact_type", DataType.VARCHAR, max_length=64)
        schema.add_field("summary", DataType.VARCHAR, max_length=4096)
        schema.add_field("content", DataType.JSON)
        schema.add_field("created_at", DataType.VARCHAR, max_length=64)
        index_params = self.client.prepare_index_params()
        index_params.add_index("embedding", index_type="AUTOINDEX", metric_type="COSINE")
        self.client.create_collection(ARTIFACT_COLLECTION, schema=schema, index_params=index_params)

    def index_chunks(self, chunks: list[DocumentChunk]) -> None:
        if not chunks:
            return
        self.ensure_collections()
        rows = []
        for chunk in chunks:
            rows.append(
                {
                    "id": chunk.id,
                    "embedding": self.embedding_client.embed(chunk.text),
                    "run_id": chunk.run_id,
                    "candidate_id": chunk.candidate_id,
                    "document_type": chunk.document_type,
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
        run_id: str,
        candidate_id: str,
        query: str,
        top_k: int = 4,
    ) -> list[EvidenceChunk]:
        self.ensure_collections()
        vector = self.embedding_client.embed(query)
        expr = (
            f'run_id == "{_escape(run_id)}" && '
            f'candidate_id == "{_escape(candidate_id)}" && '
            'document_type == "resume"'
        )
        hits = self.client.search(
            collection_name=DOCUMENT_COLLECTION,
            data=[vector],
            limit=top_k,
            filter=expr,
            output_fields=["id", "filename", "page_number", "section", "text"],
        )
        return [self._hit_to_evidence(hit) for hit in (hits[0] if hits else [])]

    def persist_artifact(
        self,
        *,
        run_id: str,
        candidate_id: str,
        artifact_type: str,
        summary: str,
        content: dict[str, Any],
    ) -> None:
        self.ensure_collections()
        artifact_id = f"{run_id}:{candidate_id or 'jd'}:{artifact_type}"
        self.client.upsert(
            collection_name=ARTIFACT_COLLECTION,
            data=[
                {
                    "id": artifact_id,
                    "embedding": self.embedding_client.embed(summary or json.dumps(content, ensure_ascii=False)[:1000]),
                    "run_id": run_id,
                    "candidate_id": candidate_id,
                    "artifact_type": artifact_type,
                    "summary": summary[:4096],
                    "content": content,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            ],
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
