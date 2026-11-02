import os
from functools import cached_property, lru_cache

from openai import OpenAI
from backend.model_transport import DefaultHttpxClient


DEFAULT_REMOTE_MODEL = "text-embedding-3-small"
DEFAULT_LOCAL_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
REMOTE_PROVIDERS = {"openai", "qwen"}


@lru_cache(maxsize=1)
def _local_model_for(model_name: str, device: str):
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model_name, device=device)


class EmbeddingService:
    def __init__(self, *, client=None, settings=None):
        self.provider = (os.getenv("EMBEDDING_PROVIDER") or "openai").lower()
        default_model = DEFAULT_LOCAL_MODEL if self.provider == "local" else DEFAULT_REMOTE_MODEL
        self.model_name = os.getenv("EMBEDDING_MODEL") or default_model
        self.device = os.getenv("EMBEDDING_DEVICE") or "cpu"
        self._settings = settings
        if settings is not None:
            self.provider = settings['provider']
            self.model_name = settings['model']
        self._client = client

    @property
    def contract(self) -> dict[str, str]:
        return {"provider": self.provider, "model": self.model_name}

    def _remote_client(self):
        if self._client is not None:
            return self._client
        api_key = (self._settings["api_key"] if self._settings is not None else
                   os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY"))
        if not api_key:
            raise RuntimeError("EMBEDDING_API_KEY or OPENAI_API_KEY is required")
        base_url = (self._settings["base_url"] if self._settings is not None else
                    os.getenv("EMBEDDING_BASE_URL") or os.getenv("OPENAI_BASE_URL")) or None
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=30.0, max_retries=0,
                              http_client=DefaultHttpxClient(follow_redirects=False))
        return self._client

    @cached_property
    def _local_model(self):
        try:
            return self._load_local_model()
        except ImportError as exc:
            raise RuntimeError(
                "Local embeddings require: uv sync --extra local-embeddings"
            ) from exc

    def _load_local_model(self):
        return _local_model_for(self.model_name, self.device)

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self.provider == "local":
            vectors = self._local_model.encode(
                texts, normalize_embeddings=True, show_progress_bar=False
            )
            return [[float(value) for value in vector] for vector in vectors]
        if self.provider not in REMOTE_PROVIDERS:
            raise RuntimeError(f"Unsupported EMBEDDING_PROVIDER: {self.provider}")
        response = self._remote_client().embeddings.create(
            model=self.model_name,
            input=texts,
        )
        rows = sorted(response.data, key=lambda row: row.index)
        if len(rows) != len(texts):
            raise RuntimeError("Embedding API returned an unexpected vector count")
        vectors = [[float(value) for value in row.embedding] for row in rows]
        if not vectors[0] or any(len(vector) != len(vectors[0]) for vector in vectors):
            raise RuntimeError("Embedding API returned inconsistent vector dimensions")
        return vectors

    def embed(self, text: str) -> list[float]:
        return self.embed_many([text])[0]


embedding_service = EmbeddingService()
