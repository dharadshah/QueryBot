import logging
import uuid
from datetime import datetime
from app.config import settings
from app.agents.schema_retriever import retrieve_schema_context
from app.agents.query_generator import generate_query
from app.agents.query_validator import validate_query
from app.agents.response_synthesiser import synthesise_response
from app.tools.db_query_tool import execute_query, enforce_top_clause
from app.database import SessionLocal
from app.models.audit import QueryAudit
from app.observability.logger import AgentLogger
from app.observability.tracer import SessionTrace
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.user_context import UserContext
from app.constants.app_constants import (
    AgentName,
    EventName,
    AppConfig,
    ValidationResult,
)
from app.constants.messages import (
    SESSION_STARTED,
    SESSION_COMPLETED,
    SESSION_FAILED,
    RETRY_ATTEMPT,
    MAX_RETRIES_EXCEEDED,
    QUERY_FAILED_USER,
    MAX_RETRIES_USER,
)

logger = logging.getLogger(__name__)


def _write_audit_record(
    session_id: str,
    question: str,
    sql: str,
    was_approved: bool,
    rejection_reason: str,
    retry_count: int,
    rows_returned: int,
    execution_time_ms: int,
    plan_analysis: dict = None,
) -> None:
    import json
    db = SessionLocal()
    try:
        record = QueryAudit(
            session_id=session_id,
            user_question=question,
            generated_sql=sql,
            was_approved=was_approved,
            rejection_reason=rejection_reason,
            retry_count=retry_count,
            rows_returned=rows_returned,
            execution_time_ms=execution_time_ms,
            plan_analysis=json.dumps(plan_analysis) if plan_analysis else None,
            created_at=datetime.utcnow(),
        )
        db.add(record)
        db.commit()
    except Exception as e:
        logger.error("Failed to write audit record: %s", str(e))
    finally:
        db.close()


def process_chat(
    request: ChatRequest,
    user_context: UserContext = None,
) -> ChatResponse:
    # Generate or use provided session ID
    session_id = request.session_id or str(uuid.uuid4())

    if user_context is None:
        user_context = UserContext()

    agent_logger = AgentLogger(
        agent_name=AgentName.ORCHESTRATOR,
        session_id=session_id,
    )

    trace = SessionTrace(
        session_id=session_id,
        user_question=request.question,
    )

    agent_logger.info(
        SESSION_STARTED.format(session_id=session_id),
        event=EventName.SESSION_STARTED,
        payload={
            "question": request.question,
            "user_role": user_context.role,
        },
    )

    final_sql = None
    last_rejection_reason = None
    retry_count = 0
    rows = []
    warn = False
    warn_message = None

    try:
        # --- Step 1: Schema Retrieval ---
        schema_span = trace.start_span(
            agent=AgentName.SCHEMA_RETRIEVER,
            input_summary=request.question,
        )
        schema_context = retrieve_schema_context(
            question=request.question,
            session_id=session_id,
        )
        schema_span.end(success=True, output_summary=f"{len(schema_context)} chars retrieved")

        # --- Step 2: Generation + Validation loop ---
        approved_sql = None

        while retry_count <= AppConfig.MAX_RETRIES:
            if retry_count > 0:
                agent_logger.info(
                    RETRY_ATTEMPT.format(
                        attempt=retry_count,
                        max_retries=AppConfig.MAX_RETRIES,
                    ),
                    event=EventName.RETRY_ATTEMPT,
                    payload={
                        "attempt": retry_count,
                        "rejection_reason": last_rejection_reason,
                    },
                )
                trace.retry_count = retry_count

            # Generate
            gen_span = trace.start_span(
                agent=AgentName.QUERY_GENERATOR,
                input_summary=request.question,
            )
            sql = generate_query(
                question=request.question,
                schema_context=schema_context,
                session_id=session_id,
                rejection_reason=last_rejection_reason,
            )
            gen_span.end(success=True, output_summary=sql)
            final_sql = sql

            # Validate
            val_span = trace.start_span(
                agent=AgentName.QUERY_VALIDATOR,
                input_summary=sql,
            )
            outcome = validate_query(
                sql=sql,
                question=request.question,
                schema_context=schema_context,
                session_id=session_id,
            )
            val_span.end(
                success=outcome.approved,
                output_summary=outcome.verdict,
                metadata={"rule_code": outcome.rule_code, "reason": outcome.reason},
            )

            if outcome.approved:
                approved_sql = sql
                warn = outcome.warn
                warn_message = outcome.warn_message
                break

            # Rejected — prepare for retry
            last_rejection_reason = outcome.reason
            retry_count += 1

            _write_audit_record(
                session_id=session_id,
                question=request.question,
                sql=sql,
                was_approved=False,
                rejection_reason=outcome.reason,
                retry_count=retry_count,
                rows_returned=None,
                execution_time_ms=None,
            )

        # --- Max retries exceeded ---
        if approved_sql is None:
            agent_logger.warning(
                MAX_RETRIES_EXCEEDED.format(max_retries=AppConfig.MAX_RETRIES),
                event=EventName.MAX_RETRIES_EXCEEDED,
                payload={"retry_count": retry_count},
            )
            trace.end_session(success=False, error=MAX_RETRIES_USER)
            agent_logger.info(
                str(trace.to_dict()),
                event=EventName.SESSION_FAILED,
                payload=trace.to_dict(),
            )
            return ChatResponse(
                session_id=session_id,
                question=request.question,
                answer=MAX_RETRIES_USER,
                sql_generated=final_sql,
                rows_returned=0,
                success=False,
                error=MAX_RETRIES_EXCEEDED.format(max_retries=AppConfig.MAX_RETRIES),
            )

        # --- Step 3: Execute Query ---
        exec_span = trace.start_span(
            agent=AgentName.DB_QUERY_TOOL,
            input_summary=approved_sql,
        )

        exec_start = datetime.utcnow()
        rows = execute_query(sql=approved_sql, session_id=session_id)
        exec_end = datetime.utcnow()
        execution_time_ms = int((exec_end - exec_start).total_seconds() * 1000)

        # Detect if results were capped at MAX_ROWS
        _, was_top_injected = enforce_top_clause(approved_sql)
        results_capped = len(rows) == AppConfig.MAX_ROWS

        exec_span.end(
            success=True,
            output_summary=f"{len(rows)} rows returned",
            metadata={"results_capped": results_capped},
        )

        # Write approved audit record
        _write_audit_record(
            session_id=session_id,
            question=request.question,
            sql=approved_sql,
            was_approved=True,
            rejection_reason=None,
            retry_count=retry_count,
            rows_returned=len(rows),
            execution_time_ms=execution_time_ms,
        )

        # --- Step 4: Synthesise Response ---
        synth_span = trace.start_span(
            agent=AgentName.RESPONSE_SYNTHESISER,
            input_summary=f"{len(rows)} rows",
        )
        answer = synthesise_response(
            question=request.question,
            rows=rows,
            session_id=session_id,
            warn=warn,
            warn_message=warn_message,
            results_capped=results_capped,
        )
        synth_span.end(success=True, output_summary="response generated")

        # --- Session Complete ---
        trace.end_session(
            success=True,
            final_sql=approved_sql,
            rows_returned=len(rows),
        )

        agent_logger.info(
            SESSION_COMPLETED.format(session_id=session_id),
            event=EventName.SESSION_COMPLETED,
            payload=trace.to_dict(),
        )

        return ChatResponse(
            session_id=session_id,
            question=request.question,
            answer=answer,
            sql_generated=approved_sql,
            rows_returned=len(rows),
            success=True,
        )

    except Exception as e:
        trace.end_session(success=False, error=str(e))
        agent_logger.error(
            SESSION_FAILED.format(session_id=session_id, error=str(e)),
            event=EventName.SESSION_FAILED,
            payload={"error": str(e), "trace": trace.to_dict()},
            exc_info=True,
        )
        _write_audit_record(
            session_id=session_id,
            question=request.question,
            sql=final_sql or "",
            was_approved=False,
            rejection_reason=str(e),
            retry_count=retry_count,
            rows_returned=None,
            execution_time_ms=None,
        )
        return ChatResponse(
            session_id=session_id,
            question=request.question,
            answer=QUERY_FAILED_USER,
            sql_generated=final_sql,
            rows_returned=0,
            success=False,
            error=str(e),
        )