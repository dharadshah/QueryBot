import logging
import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
from app.config import settings
from app.rag.schema_loader import load_schema_chunks
from app.constants.messages import (
    SCHEMA_RETRIEVAL_STARTED,
    SCHEMA_RETRIEVAL_COMPLETED,
    SCHEMA_RETRIEVAL_FAILED,
)

logger = logging.getLogger(__name__)


def get_chroma_client() -> chromadb.PersistentClient:
    return chromadb.PersistentClient(
        path=settings.chroma_persist_path,
        settings=ChromaSettings(anonymized_telemetry=False),
    )


def get_embedding_function():
    if settings.llm_provider == "openai" and settings.use_openai_embeddings:
        from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
        return OpenAIEmbeddingFunction(
            api_key=settings.openai_api_key,
            model_name=settings.openai_embedding_model,
        )
    return DefaultEmbeddingFunction()


def embed_schema() -> None:
    logger.info(SCHEMA_RETRIEVAL_STARTED.format(question="schema embedding on startup"))

    try:
        chunks = load_schema_chunks()
        chroma_client = get_chroma_client()
        embedding_function = get_embedding_function()

        collection = chroma_client.get_or_create_collection(
            name=settings.chroma_collection_name,
            embedding_function=embedding_function,
            metadata={"hnsw:space": "cosine"},
        )

        existing = collection.get()
        existing_ids = set(existing["ids"])

        new_chunks = [c for c in chunks if c["chunk_id"] not in existing_ids]

        if not new_chunks:
            logger.info(
                "Schema already embedded. Skipping. Total chunks: %d",
                len(existing_ids),
            )
            return

        texts = [c["text"] for c in new_chunks]
        ids = [c["chunk_id"] for c in new_chunks]

        collection.add(
            ids=ids,
            documents=texts,
        )

        logger.info(
            SCHEMA_RETRIEVAL_COMPLETED.format(chunk_count=len(new_chunks))
        )

    except Exception as e:
        logger.error(SCHEMA_RETRIEVAL_FAILED.format(error=str(e)))
        raise


def retrieve_schema_chunks(question: str) -> list[str]:
    try:
        chroma_client = get_chroma_client()
        embedding_function = get_embedding_function()

        collection = chroma_client.get_collection(
            name=settings.chroma_collection_name,
            embedding_function=embedding_function,
        )

        results = collection.query(
            query_texts=[question],
            n_results=settings.top_k_chunks,
        )

        chunks = results["documents"][0] if results["documents"] else []
        logger.info(
            SCHEMA_RETRIEVAL_COMPLETED.format(chunk_count=len(chunks))
        )
        return chunks

    except Exception as e:
        logger.error(SCHEMA_RETRIEVAL_FAILED.format(error=str(e)))
        raise

def force_reembed():
    """
    Clears the existing ChromaDB collection and re-embeds
    from the current approved ecommerce_schema.md.
    Called manually after human approves a schema change.
    """
    import chromadb
    from app.config import settings

    logger.info("Force re-embed requested — clearing existing collection")

    client = chromadb.PersistentClient(path=settings.chroma_persist_path)

    # Delete existing collection if it exists
    try:
        client.delete_collection(settings.chroma_collection_name)
        logger.info(
            "Deleted existing collection: %s",
            settings.chroma_collection_name,
        )
        print(f"Deleted existing collection: {settings.chroma_collection_name}")
    except Exception:
        print("No existing collection found — creating fresh.")

    # Re-embed from current schema file
    print("Re-embedding schema from ecommerce_schema.md ...")
    embed_schema()
    print("Re-embedding complete.")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )))
    from app.observability.logger import setup_logging
    setup_logging("INFO")

    if "--force-reembed" in sys.argv:
        force_reembed()
    else:
        print("Running standard embed (skips existing chunks)...")
        embed_schema()
        print("Done.")