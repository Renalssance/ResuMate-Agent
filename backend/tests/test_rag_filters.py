from backend.rag.milvus import DOCUMENT_COLLECTION, MilvusRagStore


class FakeEmbedding:
    dimension = 3

    def embed(self, text: str):
        return [1.0, 0.0, 0.0]


class FakeMilvusClient:
    def __init__(self):
        self.search_calls = []

    def has_collection(self, name):
        return True

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


def test_search_resume_evidence_filters_by_run_candidate_and_type():
    client = FakeMilvusClient()
    store = MilvusRagStore(client=client, embedding_client=FakeEmbedding())

    results = store.search_resume_evidence(
        run_id="run-1",
        candidate_id="candidate-1",
        query="Milvus RAG",
        top_k=4,
    )

    call = client.search_calls[0]
    assert call["collection_name"] == DOCUMENT_COLLECTION
    assert call["limit"] == 4
    assert 'run_id == "run-1"' in call["filter"]
    assert 'candidate_id == "candidate-1"' in call["filter"]
    assert 'document_type == "resume"' in call["filter"]
    assert results[0].chunk_id == "chunk-1"
    assert results[0].score == 0.91
