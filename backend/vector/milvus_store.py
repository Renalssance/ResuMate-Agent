import json
import logging
import os
from typing import Any

from backend.vector.embedding import embedding_service

logger = logging.getLogger(__name__)

DEFAULT_COLLECTION = "candidate_profile_vectors"


def _join_values(values: list[Any], limit: int = 12) -> str:
    items = [str(item).strip() for item in values if str(item).strip()]
    return ", ".join(items[:limit])


def _compact_json(data: dict | None, max_chars: int = 4000) -> str:
    if not data:
        return "{}"
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return text[:max_chars]


def build_resume_profile_text(structured_data: dict | None, raw_text: str = "") -> str:
    data = structured_data or {}
    lines = [
        f"类型: 简历",
        f"姓名: {data.get('name', '')}",
        f"摘要: {data.get('summary', '')}",
        f"技能: {_join_values(data.get('skills') or [], 30)}",
    ]

    education = data.get("education") or []
    if education:
        lines.append(
            "教育经历: "
            + " | ".join(
                f"{item.get('school', '')} {item.get('degree', '')} {item.get('major', '')} {item.get('years', '')}".strip()
                for item in education[:5]
                if isinstance(item, dict)
            )
        )

    experience = data.get("experience") or []
    if experience:
        lines.append(
            "工作经历: "
            + " | ".join(
                f"{item.get('company', '')} {item.get('title', '')} {item.get('duration', '')} {item.get('description', '')}".strip()
                for item in experience[:8]
                if isinstance(item, dict)
            )
        )

    projects = data.get("projects") or []
    if projects:
        lines.append(
            "项目经历: "
            + " | ".join(
                f"{item.get('name', '')} {item.get('description', '')} {_join_values(item.get('tech_stack') or [], 10)}".strip()
                for item in projects[:8]
                if isinstance(item, dict)
            )
        )

    certifications = data.get("certifications") or []
    if certifications:
        lines.append(f"证书: {_join_values(certifications, 12)}")

    if raw_text:
        lines.append(f"原文摘要: {raw_text[:1600]}")

    return "\n".join(line for line in lines if line.strip())


def build_jd_profile_text(structured_data: dict | None, raw_text: str = "") -> str:
    data = structured_data or {}
    lines = [
        "类型: JD",
        f"职位: {data.get('title', '')}",
        f"公司: {data.get('company', '')}",
        f"必备要求: {_join_values(data.get('requirements') or [], 20)}",
        f"核心技能: {_join_values(data.get('skills') or [], 30)}",
        f"工作职责: {_join_values(data.get('responsibilities') or [], 20)}",
        f"加分项: {_join_values(data.get('nice_to_have') or [], 15)}",
        f"地点: {data.get('location', '')}",
    ]
    if raw_text:
        lines.append(f"JD原文摘要: {raw_text[:1600]}")
    return "\n".join(line for line in lines if line.strip())


class MilvusVectorStore:
    """Stores parsed resume/JD profiles in Milvus for candidate matching workflows."""

    def __init__(self):
        host = os.getenv("MILVUS_HOST", "127.0.0.1")
        port = os.getenv("MILVUS_PORT", "19530")
        self.uri = os.getenv("MILVUS_URI", f"http://{host}:{port}")
        self.collection_name = os.getenv("PROFILE_VECTOR_COLLECTION", DEFAULT_COLLECTION)
        self._client = None
        self._collection_ready_for_dim: int | None = None

    @property
    def enabled(self) -> bool:
        return os.getenv("VECTOR_STORE_ENABLED", "true").lower() != "false"

    def _get_client(self):
        if self._client is None:
            from pymilvus import MilvusClient

            self._client = MilvusClient(uri=self.uri)
        return self._client

    def _ensure_collection(self, vector_dim: int) -> None:
        if self._collection_ready_for_dim == vector_dim:
            return

        from pymilvus import DataType, MilvusClient

        client = self._get_client()
        if client.has_collection(self.collection_name):
            self._collection_ready_for_dim = vector_dim
            return

        schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("pk", DataType.VARCHAR, is_primary=True, max_length=128)
        schema.add_field("doc_type", DataType.VARCHAR, max_length=32)
        schema.add_field("user_id", DataType.INT64)
        schema.add_field("source_id", DataType.INT64)
        schema.add_field("title", DataType.VARCHAR, max_length=512)
        schema.add_field("content", DataType.VARCHAR, max_length=8192)
        schema.add_field("metadata_json", DataType.VARCHAR, max_length=8192)
        schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=vector_dim)

        index_params = client.prepare_index_params()
        index_params.add_index(
            field_name="embedding",
            index_type="AUTOINDEX",
            metric_type="COSINE",
        )
        client.create_collection(
            collection_name=self.collection_name,
            schema=schema,
            index_params=index_params,
        )
        self._collection_ready_for_dim = vector_dim

    @staticmethod
    def _pk(doc_type: str, user_id: int, source_id: int) -> str:
        return f"{doc_type}:{user_id}:{source_id}"

    def upsert_profile(
        self,
        *,
        doc_type: str,
        user_id: int,
        source_id: int,
        title: str,
        content: str,
        metadata: dict | None = None,
    ) -> None:
        if not self.enabled:
            return
        content = (content or "").strip()
        if not content:
            raise ValueError("Cannot write empty profile content to vector store")

        vector = embedding_service.embed(content)
        self._ensure_collection(len(vector))
        self._get_client().upsert(
            collection_name=self.collection_name,
            data=[
                {
                    "pk": self._pk(doc_type, user_id, source_id),
                    "doc_type": doc_type,
                    "user_id": int(user_id),
                    "source_id": int(source_id),
                    "title": (title or "")[:512],
                    "content": content[:8192],
                    "metadata_json": _compact_json(metadata, 8192),
                    "embedding": vector,
                }
            ],
        )

    def upsert_resume(
        self,
        *,
        user_id: int,
        resume_id: int,
        filename: str,
        structured_data: dict | None,
        raw_text: str,
    ) -> None:
        content = build_resume_profile_text(structured_data, raw_text)
        title = (structured_data or {}).get("name") or filename
        self.upsert_profile(
            doc_type="resume",
            user_id=user_id,
            source_id=resume_id,
            title=title,
            content=content,
            metadata={"filename": filename, "structured_data": structured_data or {}},
        )

    def upsert_jd(
        self,
        *,
        user_id: int,
        jd_id: int,
        title: str,
        company: str,
        structured_data: dict | None,
        raw_text: str,
    ) -> None:
        content = build_jd_profile_text(structured_data, raw_text)
        self.upsert_profile(
            doc_type="jd",
            user_id=user_id,
            source_id=jd_id,
            title=title,
            content=content,
            metadata={"title": title, "company": company, "structured_data": structured_data or {}},
        )

    def delete_profile(self, *, doc_type: str, user_id: int, source_id: int) -> None:
        if not self.enabled:
            return
        client = self._get_client()
        if not client.has_collection(self.collection_name):
            return
        client.delete(
            collection_name=self.collection_name,
            ids=[self._pk(doc_type, user_id, source_id)],
        )


vector_store = MilvusVectorStore()
