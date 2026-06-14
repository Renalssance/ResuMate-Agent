import pytest

from backend.rag import milvus
from backend.rag.milvus import ARTIFACT_COLLECTION, DOCUMENT_COLLECTION, MilvusRagStore
from backend.services.documents import DocumentChunk


DOCUMENT_FIELDS = {
    "id",
    "embedding",
    "user_id",
    "document_id",
    "run_id",
    "candidate_id",
    "document_type",
    "filename",
    "page_number",
    "section",
    "chunk_index",
    "text",
    "metadata",
}
ARTIFACT_FIELDS = {
    "id",
    "embedding",
    "user_id",
    "run_id",
    "candidate_id",
    "artifact_type",
    "summary",
    "content",
    "created_at",
}
INT_FIELDS = {
    "user_id",
    "document_id",
    "run_id",
    "candidate_id",
    "page_number",
    "chunk_index",
}
JSON_FIELDS = {"metadata", "content"}


class FakeEmbedding:
    def __init__(self, dimension=3):
        self.dimension = dimension
        self.calls = []

    def embed(self, text: str):
        self.calls.append(text)
        return [1.0] + [0.0] * (self.dimension - 1)


class FakeSchema:
    def __init__(self):
        self.fields = []

    def add_field(self, name, data_type, **kwargs):
        self.fields.append({"name": name, "type": data_type, **kwargs})


class FakeIndexParams:
    def add_index(self, *args, **kwargs):
        return None


class FakeMilvusClient:
    def __init__(self, collections=None):
        self.collections = collections or {}
        self.search_calls = []
        self.delete_calls = []
        self.upsert_calls = []
        self.create_calls = []

    def has_collection(self, name):
        return name in self.collections

    def describe_collection(self, collection_name):
        return self.collections[collection_name]

    def prepare_index_params(self):
        return FakeIndexParams()

    def create_collection(self, collection_name, schema, index_params):
        self.create_calls.append(
            {
                "collection_name": collection_name,
                "schema": schema,
                "index_params": index_params,
            }
        )
        self.collections[collection_name] = _collection_description(
            {field["name"] for field in schema.fields},
            next(field["dim"] for field in schema.fields if field["name"] == "embedding"),
        )

    def search(self, **kwargs):
        self.search_calls.append(kwargs)
        return [
            [
                {
                    "distance": 0.91,
                    "entity": {
                        "id": "chunk-1",
                        "filename": "resume.pdf",
                        "page_number": 2,
                        "section": "Projects",
                        "text": "Implemented Milvus retrieval.",
                    },
                }
            ]
        ]

    def delete(self, **kwargs):
        self.delete_calls.append(kwargs)

    def upsert(self, **kwargs):
        self.upsert_calls.append(kwargs)


def _collection_description(fields, dimension, type_overrides=None):
    type_overrides = type_overrides or {}
    return {
        "fields": [
            {
                "name": name,
                "type": type_overrides.get(
                    name,
                    "FLOAT_VECTOR"
                    if name == "embedding"
                    else "INT64"
                    if name in INT_FIELDS
                    else "JSON"
                    if name in JSON_FIELDS
                    else "VARCHAR",
                ),
                "params": {"dim": str(dimension)} if name == "embedding" else {},
            }
            for name in fields
        ]
    }


def _ready_client(dimension=3):
    return FakeMilvusClient(
        {
            DOCUMENT_COLLECTION: _collection_description(DOCUMENT_FIELDS, dimension),
            ARTIFACT_COLLECTION: _collection_description(ARTIFACT_FIELDS, dimension),
        }
    )


@pytest.fixture(autouse=True)
def fake_schema_factory(monkeypatch):
    monkeypatch.setattr(milvus.MilvusClient, "create_schema", lambda **kwargs: FakeSchema())


def test_search_resume_evidence_filters_by_user_run_candidate_and_type():
    client = _ready_client()
    store = MilvusRagStore(client=client, embedding_client=FakeEmbedding())

    results = store.search_resume_evidence(
        user_id="7",
        run_id="11",
        candidate_id="13",
        query="Milvus RAG",
        top_k=4,
    )

    call = client.search_calls[0]
    assert call["collection_name"] == DOCUMENT_COLLECTION
    assert call["limit"] == 4
    assert call["filter"] == (
        'user_id == 7 && run_id == 11 && candidate_id == 13 && document_type == "resume"'
    )
    assert results[0].chunk_id == "chunk-1"
    assert results[0].score == 0.91


def test_delete_document_filters_by_user_type_and_document():
    client = _ready_client()
    store = MilvusRagStore(client=client, embedding_client=FakeEmbedding())

    store.delete_document(user_id=7, document_type="resume", document_id=21)

    assert client.delete_calls == [
        {
            "collection_name": DOCUMENT_COLLECTION,
            "filter": 'user_id == 7 && document_id == 21 && document_type == "resume"',
        }
    ]


def test_delete_candidate_artifacts_filters_by_user_run_and_candidate():
    client = _ready_client()
    store = MilvusRagStore(client=client, embedding_client=FakeEmbedding())

    store.delete_candidate_artifacts(user_id=7, run_id=11, candidate_id=13)

    assert client.delete_calls == [
        {
            "collection_name": ARTIFACT_COLLECTION,
            "filter": "user_id == 7 && run_id == 11 && candidate_id == 13",
        }
    ]


def test_invalid_integer_and_document_type_filters_are_rejected():
    store = MilvusRagStore(client=_ready_client(), embedding_client=FakeEmbedding())

    with pytest.raises(ValueError, match="user_id"):
        store.delete_document(user_id='7 || user_id != 7', document_type="resume", document_id=21)
    with pytest.raises(ValueError, match="document_type"):
        store.delete_document(user_id=7, document_type='resume" || true', document_id=21)


def test_index_chunks_uses_first_real_vector_dimension_without_duplicate_embedding():
    client = FakeMilvusClient()
    embedding = FakeEmbedding(dimension=5)
    store = MilvusRagStore(client=client, embedding_client=embedding)
    chunks = [
        DocumentChunk(
            id=f"chunk-{index}",
            run_id=11,
            candidate_id=13,
            document_type="resume",
            filename="resume.pdf",
            page_number=1,
            section="Projects",
            chunk_index=index,
            text=f"chunk text {index}",
            metadata={},
        )
        for index in range(2)
    ]

    store.index_chunks(user_id=7, document_id=21, chunks=chunks)

    assert embedding.calls == ["chunk text 0", "chunk text 1"]
    assert {call["collection_name"] for call in client.create_calls} == {
        DOCUMENT_COLLECTION,
        ARTIFACT_COLLECTION,
    }
    for call in client.create_calls:
        embedding_field = next(
            field for field in call["schema"].fields if field["name"] == "embedding"
        )
        assert embedding_field["dim"] == 5
    rows = client.upsert_calls[0]["data"]
    assert rows[0]["user_id"] == 7
    assert rows[0]["document_id"] == 21
    assert rows[0]["run_id"] == 11
    assert rows[0]["candidate_id"] == 13


def test_persist_artifact_uses_user_run_candidate_fields():
    client = _ready_client()
    store = MilvusRagStore(client=client, embedding_client=FakeEmbedding())

    store.persist_artifact(
        user_id=7,
        run_id=11,
        candidate_id=13,
        artifact_type="report",
        summary="Candidate report",
        content={"score": 88},
    )

    row = client.upsert_calls[0]["data"][0]
    assert row["user_id"] == 7
    assert row["run_id"] == 11
    assert row["candidate_id"] == 13


def test_existing_collection_dimension_mismatch_is_rejected():
    client = _ready_client(dimension=4)
    store = MilvusRagStore(client=client, embedding_client=FakeEmbedding(dimension=3))

    with pytest.raises(RuntimeError, match="dimension.*4.*3"):
        store.search_resume_evidence(
            user_id=7,
            run_id=11,
            candidate_id=13,
            query="Milvus RAG",
        )


def test_existing_collection_missing_required_fields_is_rejected():
    client = _ready_client()
    client.collections[DOCUMENT_COLLECTION] = _collection_description(
        DOCUMENT_FIELDS - {"user_id"},
        3,
    )
    store = MilvusRagStore(client=client, embedding_client=FakeEmbedding())

    with pytest.raises(RuntimeError, match="user_id"):
        store.search_resume_evidence(
            user_id=7,
            run_id=11,
            candidate_id=13,
            query="Milvus RAG",
        )


def test_existing_collection_with_legacy_string_ids_is_rejected():
    client = _ready_client()
    client.collections[DOCUMENT_COLLECTION] = _collection_description(
        DOCUMENT_FIELDS,
        3,
        {"run_id": "VARCHAR"},
    )
    store = MilvusRagStore(client=client, embedding_client=FakeEmbedding())

    with pytest.raises(RuntimeError, match="run_id.*INT64"):
        store.search_resume_evidence(
            user_id=7,
            run_id=11,
            candidate_id=13,
            query="Milvus RAG",
        )


def test_default_embedding_adapter_has_no_embedding_dimension_env_dependency(monkeypatch):
    monkeypatch.delenv("EMBEDDING_DIMENSION", raising=False)
    monkeypatch.setattr(milvus.embedding_service, "embed", lambda text: [1.0, 0.0])
    client = FakeMilvusClient()

    store = MilvusRagStore(client=client)
    store.persist_artifact(
        user_id=7,
        run_id=11,
        candidate_id=13,
        artifact_type="report",
        summary="Candidate report",
        content={},
    )

    assert len(client.upsert_calls[0]["data"][0]["embedding"]) == 2
