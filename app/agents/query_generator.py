import logging
from app.config import settings
from app.utils.llm_client import get_llm_client
from app.observability.logger import AgentLogger
from app.constants.app_constants import AgentName, EventName, AppConfig
from app.constants.prompts import (
    QUERY_GENERATOR_SYSTEM_PROMPT,
    QUERY_GENERATOR_USER_PROMPT,
    QUERY_GENERATOR_RETRY_PROMPT,
)
from app.constants.messages import (
    QUERY_GENERATION_STARTED,
    QUERY_GENERATION_COMPLETED,
    QUERY_GENERATION_FAILED,
)

logger = logging.getLogger(__name__)


def _clean_sql(raw: str) -> str:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()
    return cleaned


def generate_query(
    question: str,
    schema_context: str,
    session_id: str,
    rejection_reason: str = None,
    conversation_history: str = "",
) -> str:
    agent_logger = AgentLogger(
        agent_name=AgentName.QUERY_GENERATOR,
        session_id=session_id,
    )

    agent_logger.info(
        QUERY_GENERATION_STARTED.format(question=question),
        event=EventName.QUERY_GENERATION_STARTED,
        payload={
            "question": question,
            "is_retry": rejection_reason is not None,
            "rejection_reason": rejection_reason,
            "has_history": bool(conversation_history),
        },
    )

    try:
        client = get_llm_client()

        system_prompt = QUERY_GENERATOR_SYSTEM_PROMPT.format(
            max_rows=AppConfig.MAX_ROWS,
        )

        conversation_separator = "\n\n" if conversation_history else ""

        if rejection_reason:
            user_prompt = QUERY_GENERATOR_RETRY_PROMPT.format(
                conversation_history=conversation_history,
                conversation_separator=conversation_separator,
                rejection_reason=rejection_reason,
                schema_context=schema_context,
                user_question=question,
                max_rows=AppConfig.MAX_ROWS,
            )
        else:
            user_prompt = QUERY_GENERATOR_USER_PROMPT.format(
                conversation_history=conversation_history,
                conversation_separator=conversation_separator,
                schema_context=schema_context,
                user_question=question,
                max_rows=AppConfig.MAX_ROWS,
            )

        response = client.chat.completions.create(
            model=settings.active_chat_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=300,
        )

        raw_sql = response.choices[0].message.content
        cleaned_sql = _clean_sql(raw_sql)

        agent_logger.info(
            QUERY_GENERATION_COMPLETED,
            event=EventName.QUERY_GENERATION_COMPLETED,
            payload={"generated_sql": cleaned_sql},
        )

        return cleaned_sql

    except Exception as e:
        agent_logger.error(
            QUERY_GENERATION_FAILED.format(error=str(e)),
            event=EventName.QUERY_GENERATION_FAILED,
            payload={"error": str(e)},
            exc_info=True,
        )
        raise