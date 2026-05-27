import logging
import os
from app.constants.messages import SCHEMA_RETRIEVAL_FAILED

logger = logging.getLogger(__name__)

SCHEMA_FILE_PATH = os.path.join(
    os.path.dirname(__file__),
    "schema_definitions",
    "ecommerce_schema.md",
)

CHUNK_SEPARATOR = "---"


def load_schema_chunks() -> list[dict]:
    try:
        with open(SCHEMA_FILE_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        raw_chunks = content.split(CHUNK_SEPARATOR)

        chunks = []
        for i, chunk in enumerate(raw_chunks):
            cleaned = chunk.strip()
            if len(cleaned) < 50:
                continue
            chunks.append({
                "chunk_id": f"schema_chunk_{i}",
                "text": cleaned,
            })

        logger.info("Schema loaded and split into %d chunks", len(chunks))
        return chunks

    except Exception as e:
        logger.error(SCHEMA_RETRIEVAL_FAILED.format(error=str(e)))
        raise