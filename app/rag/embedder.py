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