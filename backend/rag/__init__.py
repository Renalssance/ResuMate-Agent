import os


def get_rag_store():
    from backend.services.embedding_settings import saved_settings
    from backend.vector.embedding import EmbeddingService
    settings = saved_settings()
    options = {'embedding_client': EmbeddingService(settings=settings)} if settings is not None else {}
    if os.getenv("CLOUDBASE_ENV_ID"):
        from backend.rag.mysql import MySQLRagStore

        return MySQLRagStore(**options)
    from backend.rag.chroma import ChromaRagStore

    return ChromaRagStore(**options)
