import logging
import chromadb
from chromadb.config import Settings as ChromaSettings
from openai import OpenAI
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


def get_openai_client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key)


def embed_schema() -> None:
    logger.info(SCHEMA_RETRIEVAL_STARTED.format(question="schema embedding on startup"))

    try:
        chunks = load_schema_chunks()
        chroma_client = get_chroma_client()
        openai_client = get_openai_client()

        collection = chroma_client.get_or_create_collection(
            name=settings.chroma_collection_name,
            metadata={"hnsw:space": "cosine"},
        )

        existing = collection.get()
        existing_ids = set(existing["ids"])

        new_chunks = [c for c in chunks if c["chunk_id"] not in existing_ids]

        if not new_chunks:
            logger.info("Schema already embedded. Skipping. Total chunks: %d", len(existing_ids))
            return

        texts = [c["text"] for c in new_chunks]
        ids = [c["chunk_id"] for c in new_chunks]

        response = openai_client.embeddings.create(
            model=settings.openai_embedding_model,
            input=texts,
        )

        embeddings = [item.embedding for item in response.data]

        collection.add(
            ids=ids,
            embeddings=embeddings,
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
        openai_client = get_openai_client()

        collection = chroma_client.get_collection(
            name=settings.chroma_collection_name,
        )

        response = openai_client.embeddings.create(
            model=settings.openai_embedding_model,
            input=[question],
        )

        query_embedding = response.data[0].embedding

        results = collection.query(
            query_embeddings=[query_embedding],
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