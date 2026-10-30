import os


def get_rag_store():
    if os.getenv("CLOUDBASE_ENV_ID"):
        from backend.rag.mysql import MySQLRagStore

        return MySQLRagStore()
    from backend.rag.chroma import ChromaRagStore

    return ChromaRagStore()
