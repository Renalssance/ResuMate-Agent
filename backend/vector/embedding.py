import os
from functools import lru_cache


DEFAULT_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class EmbeddingService:
    """Lazy sentence-transformer embedding service."""

    def __init__(self):
        self.model_name = os.getenv("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
        self.device = os.getenv("EMBEDDING_DEVICE", "cpu")

    @lru_cache(maxsize=1)
    def _model(self):
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(self.model_name, device=self.device)

    @property
    def dimension(self) -> int:
        dimension = self._model().get_sentence_embedding_dimension()
        if not dimension:
            raise RuntimeError(f"Cannot infer embedding dimension for {self.model_name}")
        return int(dimension)

    def embed(self, text: str) -> list[float]:
        vector = self._model().encode(
            [text],
            normalize_embeddings=True,
            show_progress_bar=False,
        )[0]
        return [float(v) for v in vector]


embedding_service = EmbeddingService()
