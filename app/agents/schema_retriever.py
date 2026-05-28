import logging
from app.rag.embedder import retrieve_schema_chunks
from app.observability.logger import AgentLogger
from app.constants.app_constants import AgentName, EventName
from app.constants.messages import (
    SCHEMA_RETRIEVAL_STARTED,
    SCHEMA_RETRIEVAL_COMPLETED,
    SCHEMA_RETRIEVAL_FAILED,
)

logger = logging.getLogger(__name__)


def retrieve_schema_context(question: str, session_id: str) -> str:
    agent_logger = AgentLogger(
        agent_name=AgentName.SCHEMA_RETRIEVER,
        session_id=session_id,
    )

    agent_logger.info(
        SCHEMA_RETRIEVAL_STARTED.format(question=question),
        event=EventName.SCHEMA_RETRIEVAL_STARTED,
        payload={"question": question},
    )

    try:
        chunks = retrieve_schema_chunks(question)

        if not chunks:
            agent_logger.warning(
                "No schema chunks retrieved for question",
                event=EventName.SCHEMA_RETRIEVAL_COMPLETED,
                payload={"question": question, "chunk_count": 0},
            )
            return ""

        # Join chunks into a single formatted context string
        context = "\n\n---\n\n".join(chunks)

        agent_logger.info(
            SCHEMA_RETRIEVAL_COMPLETED.format(chunk_count=len(chunks)),
            event=EventName.SCHEMA_RETRIEVAL_COMPLETED,
            payload={"chunk_count": len(chunks)},
        )

        return context

    except Exception as e:
        agent_logger.error(
            SCHEMA_RETRIEVAL_FAILED.format(error=str(e)),
            event=EventName.SCHEMA_RETRIEVAL_COMPLETED,
            payload={"error": str(e)},
            exc_info=True,
        )
        raise