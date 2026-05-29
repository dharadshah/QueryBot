import logging
from app.database import SessionLocal
from app.models.conversation import ConversationHistory
from app.config import settings

logger = logging.getLogger(__name__)

MAX_HISTORY_TURNS = 5


def load_history(session_id: str) -> list[dict]:
    db = SessionLocal()
    try:
        records = (
            db.query(ConversationHistory)
            .filter(ConversationHistory.session_id == session_id)
            .order_by(ConversationHistory.turn_number.desc())
            .limit(MAX_HISTORY_TURNS)
            .all()
        )
        # Return in chronological order
        records = list(reversed(records))
        return [
            {
                "turn_number": r.turn_number,
                "user_question": r.user_question,
                "generated_sql": r.generated_sql,
                "answer": r.answer,
            }
            for r in records
        ]
    except Exception as e:
        logger.error("Failed to load conversation history: %s", str(e))
        return []
    finally:
        db.close()


def save_turn(
    session_id: str,
    user_question: str,
    generated_sql: str,
    answer: str,
) -> None:
    db = SessionLocal()
    try:
        # Get current turn count
        count = (
            db.query(ConversationHistory)
            .filter(ConversationHistory.session_id == session_id)
            .count()
        )
        record = ConversationHistory(
            session_id=session_id,
            turn_number=count + 1,
            user_question=user_question,
            generated_sql=generated_sql,
            answer=answer,
        )
        db.add(record)
        db.commit()
    except Exception as e:
        logger.error("Failed to save conversation turn: %s", str(e))
    finally:
        db.close()


def format_history_for_prompt(history: list[dict]) -> str:
    if not history:
        return ""

    lines = [f"Conversation history (last {len(history)} exchanges):"]
    for turn in history:
        lines.append(f"\n  [{turn['turn_number']}] User: {turn['user_question']}")
        if turn["generated_sql"]:
            # Truncate long SQL to keep prompt lean
            sql_preview = turn["generated_sql"][:200]
            if len(turn["generated_sql"]) > 200:
                sql_preview += "..."
            lines.append(f"      SQL: {sql_preview}")
        # Truncate long answers too
        answer_preview = turn["answer"][:150]
        if len(turn["answer"]) > 150:
            answer_preview += "..."
        lines.append(f"      Answer: {answer_preview}")

    return "\n".join(lines)