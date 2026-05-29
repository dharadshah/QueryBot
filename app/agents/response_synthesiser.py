import logging
from app.config import settings
from app.utils.llm_client import get_llm_client
from app.observability.logger import AgentLogger
from app.constants.app_constants import AgentName, EventName, AppConfig
from app.constants.prompts import (
    RESPONSE_SYNTHESISER_SYSTEM_PROMPT,
    RESPONSE_SYNTHESISER_USER_PROMPT,
)
from app.constants.messages import (
    RESPONSE_SYNTHESIS_STARTED,
    RESPONSE_SYNTHESIS_COMPLETED,
    RESPONSE_SYNTHESIS_FAILED,
    RESULTS_CAPPED_WARNING,
    UNBOUNDED_QUERY_WARNING,
    NO_RESULTS_FOUND,
)

logger = logging.getLogger(__name__)


def synthesise_response(
    question: str,
    rows: list[dict],
    session_id: str,
    warn: bool = False,
    warn_message: str = None,
    results_capped: bool = False,
) -> str:
    agent_logger = AgentLogger(
        agent_name=AgentName.RESPONSE_SYNTHESISER,
        session_id=session_id,
    )

    agent_logger.info(
        RESPONSE_SYNTHESIS_STARTED,
        event=EventName.RESPONSE_SYNTHESIS_STARTED,
        payload={
            "question": question,
            "row_count": len(rows),
            "warn": warn,
            "results_capped": results_capped,
        },
    )

    try:
       # Handle empty results without calling LLM
        if not rows:
            agent_logger.info(
                RESPONSE_SYNTHESIS_COMPLETED,
                event=EventName.RESPONSE_SYNTHESIS_COMPLETED,
                payload={"row_count": 0},
            )
            return NO_RESULTS_FOUND

        # Detect COUNT queries returning zero
        if len(rows) == 1:
            values = list(rows[0].values())
            if len(values) == 1 and isinstance(values[0], int) and values[0] == 0:
                agent_logger.info(
                    RESPONSE_SYNTHESIS_COMPLETED,
                    event=EventName.RESPONSE_SYNTHESIS_COMPLETED,
                    payload={"row_count": 0},
                )
                return f"There are no records matching your question: {question}"

        # Format rows as readable text for the LLM
        formatted_rows = _format_rows(rows)

        client = get_llm_client()

        response = client.chat.completions.create(
            model=settings.active_chat_model,
            messages=[
                {
                    "role": "system",
                    "content": RESPONSE_SYNTHESISER_SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": RESPONSE_SYNTHESISER_USER_PROMPT.format(
                        user_question=question,
                        query_results=formatted_rows,
                    ),
                },
            ],
            temperature=0.2,
            max_tokens=300,
        )

        answer = response.choices[0].message.content.strip()

        # Append warnings — merge into one message if both apply
        if results_capped and warn and warn_message:
            answer += (
                f"\n\nNote: your question asked for all results and the output is "
                f"limited to {AppConfig.MAX_ROWS} rows. The results shown may be incomplete."
            )
        elif results_capped:
            answer += "\n\n" + RESULTS_CAPPED_WARNING.format(
                max_rows=AppConfig.MAX_ROWS
            )
        elif warn and warn_message:
            answer += "\n\n" + UNBOUNDED_QUERY_WARNING.format(
                max_rows=AppConfig.MAX_ROWS
            )

        agent_logger.info(
            RESPONSE_SYNTHESIS_COMPLETED,
            event=EventName.RESPONSE_SYNTHESIS_COMPLETED,
            payload={"row_count": len(rows)},
        )

        return answer

    except Exception as e:
        agent_logger.error(
            RESPONSE_SYNTHESIS_FAILED.format(error=str(e)),
            event=EventName.RESPONSE_SYNTHESIS_FAILED,
            payload={"error": str(e)},
            exc_info=True,
        )
        raise


def _format_rows(rows: list[dict]) -> str:
    if not rows:
        return "No data returned."

    # Build a simple column-aligned text table
    headers = list(rows[0].keys())
    lines = []

    # Header row
    lines.append(" | ".join(str(h) for h in headers))
    lines.append("-" * len(lines[0]))

    # Data rows
    for row in rows:
        lines.append(" | ".join(str(row.get(h, "")) for h in headers))

    return "\n".join(lines)