import json
import logging
import re
import sqlglot
from dataclasses import dataclass
from app.config import settings
from app.utils.llm_client import get_llm_client
from app.observability.logger import AgentLogger
from app.constants.app_constants import (
    AgentName,
    EventName,
    ValidationResult,
    HardRuleCode,
    DisallowedKeyword,
    DangerousSystemCall,
    AppConfig,
)
from app.constants.prompts import (
    LLM_GUARDRAIL_SYSTEM_PROMPT,
    LLM_GUARDRAIL_USER_PROMPT,
)
from app.constants.messages import (
    VALIDATION_STARTED,
    HARD_RULE_PASSED,
    HARD_RULE_FAILED,
    LLM_GUARDRAIL_PASSED,
    LLM_GUARDRAIL_FAILED,
    VALIDATION_APPROVED,
    VALIDATION_REJECTED,
)
from app.utils.execution_plan import check_query_plan


logger = logging.getLogger(__name__)


@dataclass
class ValidationOutcome:
    verdict: str
    rule_code: str = None
    reason: str = None
    warn: bool = False
    warn_message: str = None

    @property
    def approved(self) -> bool:
        return self.verdict in (ValidationResult.APPROVED, ValidationResult.WARN)


# ---------------------------------------------------------------------------
# Layer 1 — Hard Rules (pure Python, no LLM)
# ---------------------------------------------------------------------------

def _check_syntax(sql: str) -> ValidationOutcome:
    try:
        statements = sqlglot.parse(sql, dialect="tsql")
        if not statements:
            return ValidationOutcome(
                verdict=ValidationResult.REJECTED,
                rule_code=HardRuleCode.SYNTAX_ERROR,
                reason="Query could not be parsed — no valid statements found.",
            )
        return ValidationOutcome(verdict=ValidationResult.APPROVED)
    except sqlglot.errors.ParseError as e:
        return ValidationOutcome(
            verdict=ValidationResult.REJECTED,
            rule_code=HardRuleCode.SYNTAX_ERROR,
            reason=f"SQL syntax error: {str(e)}",
        )


def _check_select_only(sql: str) -> ValidationOutcome:
    try:
        statements = sqlglot.parse(sql, dialect="tsql")
        for statement in statements:
            if not isinstance(statement, sqlglot.expressions.Select):
                return ValidationOutcome(
                    verdict=ValidationResult.REJECTED,
                    rule_code=HardRuleCode.NOT_SELECT,
                    reason=(
                        f"Only SELECT statements are allowed. "
                        f"Found: {type(statement).__name__}."
                    ),
                )
        return ValidationOutcome(verdict=ValidationResult.APPROVED)
    except Exception:
        return ValidationOutcome(
            verdict=ValidationResult.REJECTED,
            rule_code=HardRuleCode.SYNTAX_ERROR,
            reason="Could not determine statement type.",
        )


def _check_disallowed_keywords(sql: str) -> ValidationOutcome:
    sql_upper = sql.upper()
    for keyword in DisallowedKeyword.LIST:
        pattern = r'\b' + re.escape(keyword) + r'\b'
        if re.search(pattern, sql_upper):
            return ValidationOutcome(
                verdict=ValidationResult.REJECTED,
                rule_code=HardRuleCode.DISALLOWED_KEYWORD,
                reason=f"Disallowed keyword detected: {keyword}.",
            )
    return ValidationOutcome(verdict=ValidationResult.APPROVED)


def _check_dangerous_system_calls(sql: str) -> ValidationOutcome:
    sql_upper = sql.upper()
    for call in DangerousSystemCall.LIST:
        if call.upper() in sql_upper:
            return ValidationOutcome(
                verdict=ValidationResult.REJECTED,
                rule_code=HardRuleCode.DANGEROUS_SYSTEM_CALL,
                reason=f"Dangerous system call detected: {call}.",
            )
    return ValidationOutcome(verdict=ValidationResult.APPROVED)


def _check_comment_injection(sql: str) -> ValidationOutcome:
    if "--" in sql or "/*" in sql:
        return ValidationOutcome(
            verdict=ValidationResult.REJECTED,
            rule_code=HardRuleCode.COMMENT_INJECTION,
            reason="SQL comments are not allowed in queries.",
        )
    return ValidationOutcome(verdict=ValidationResult.APPROVED)


def _check_semicolon_stacking(sql: str) -> ValidationOutcome:
    # Allow trailing semicolon but block multiple statements
    stripped = sql.rstrip().rstrip(";").strip()
    if ";" in stripped:
        return ValidationOutcome(
            verdict=ValidationResult.REJECTED,
            rule_code=HardRuleCode.SEMICOLON_STACKING,
            reason="Multiple statements detected. Only a single SELECT is allowed.",
        )
    return ValidationOutcome(verdict=ValidationResult.APPROVED)


def _check_top_clause(sql: str) -> ValidationOutcome:
    top_pattern = re.compile(
        r'\bSELECT\s+TOP\s*\(?\s*\d+\s*\)?',
        re.IGNORECASE,
    )
    if not top_pattern.search(sql):
        return ValidationOutcome(
            verdict=ValidationResult.REJECTED,
            rule_code=HardRuleCode.MISSING_TOP_CLAUSE,
            reason=(
                f"Query must include a TOP clause. "
                f"Add TOP {AppConfig.MAX_ROWS} after SELECT."
            ),
        )
    return ValidationOutcome(verdict=ValidationResult.APPROVED)


def _check_cartesian_join(sql: str) -> ValidationOutcome:
    # Detect comma-separated tables in FROM clause without JOIN keyword
    from_pattern = re.compile(
        r'\bFROM\b\s+\w+\s*,\s*\w+',
        re.IGNORECASE,
    )
    if from_pattern.search(sql):
        return ValidationOutcome(
            verdict=ValidationResult.REJECTED,
            rule_code=HardRuleCode.CARTESIAN_JOIN,
            reason=(
                "Implicit comma join detected in FROM clause. "
                "Use explicit JOIN ... ON syntax instead."
            ),
        )
    return ValidationOutcome(verdict=ValidationResult.APPROVED)


def _check_execution_plan(sql: str) -> ValidationOutcome:
    from app.constants.messages import (
        EXECUTION_PLAN_TABLE_SCAN,
        EXECUTION_PLAN_MISSING_INDEX,
        EXECUTION_PLAN_CHECK_FAILED,
    )

    result = check_query_plan(sql)

    if not result["success"]:
        logger.warning(
            EXECUTION_PLAN_CHECK_FAILED.format(error=result["error"])
        )
        return ValidationOutcome(verdict=ValidationResult.APPROVED)

    if result["table_scans"]:
        scan = result["table_scans"][0]
        return ValidationOutcome(
            verdict=ValidationResult.REJECTED,
            rule_code=HardRuleCode.EXECUTION_PLAN,
            reason=EXECUTION_PLAN_TABLE_SCAN.format(
                table=scan["table"],
                rows=scan["estimated_rows"],
            ),
        )

    if result["missing_indexes"]:
        missing = result["missing_indexes"][0]
        return ValidationOutcome(
            verdict=ValidationResult.REJECTED,
            rule_code=HardRuleCode.EXECUTION_PLAN,
            reason=EXECUTION_PLAN_MISSING_INDEX.format(
                table=missing["table"],
                columns=", ".join(missing["columns"]),
            ),
        )

    # Log the clean plan summary even when approved
    logger.info(
        "Execution plan check passed",
        extra={
            "agent": AgentName.QUERY_VALIDATOR,
            "event": EventName.HARD_RULE_PASSED,
            "session_id": None,
            "payload": {
                "max_estimated_rows": result["max_estimated_rows"],
                "table_scans": result["table_scans"],
                "missing_indexes": result["missing_indexes"],
            },
        },
    )
    return ValidationOutcome(verdict=ValidationResult.APPROVED)

def run_hard_rules(sql: str, agent_logger: AgentLogger) -> ValidationOutcome:
    rules = [
        _check_comment_injection,
        _check_semicolon_stacking,
        _check_syntax,
        _check_select_only,
        _check_disallowed_keywords,
        _check_dangerous_system_calls,
        _check_top_clause,
        _check_cartesian_join,
        _check_execution_plan,       # runs last — makes a DB call
    ]

    for rule_fn in rules:
        outcome = rule_fn(sql)
        if not outcome.approved:
            agent_logger.warning(
                HARD_RULE_FAILED.format(
                    rule_code=outcome.rule_code,
                    reason=outcome.reason,
                ),
                event=EventName.HARD_RULE_FAILED,
                payload={
                    "rule_code": outcome.rule_code,
                    "reason": outcome.reason,
                    "sql": sql,
                },
            )
            return outcome

    agent_logger.info(
        HARD_RULE_PASSED,
        event=EventName.HARD_RULE_PASSED,
        payload={"sql": sql},
    )
    return ValidationOutcome(verdict=ValidationResult.APPROVED)


# ---------------------------------------------------------------------------
# Layer 2 — LLM Guardrail
# ---------------------------------------------------------------------------

def run_llm_guardrail(
    sql: str,
    question: str,
    schema_context: str,
    agent_logger: AgentLogger,
    conversation_history: str = "",
) -> ValidationOutcome:
    try:
        client = get_llm_client()

        conversation_separator = "\n\n" if conversation_history else ""

        response = client.chat.completions.create(
            model=settings.active_chat_model,
            messages=[
                {
                    "role": "system",
                    "content": LLM_GUARDRAIL_SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": LLM_GUARDRAIL_USER_PROMPT.format(
                        conversation_history=conversation_history,
                        conversation_separator=conversation_separator,
                        user_question=question,
                        schema_context=schema_context,
                        sql_query=sql,
                    ),
                },
            ],
            temperature=0.0,
            max_tokens=200,
        )

        raw_response = response.choices[0].message.content.strip()

        # Strip markdown fences if present
        if raw_response.startswith("```"):
            lines = raw_response.splitlines()
            lines = [l for l in lines if not l.strip().startswith("```")]
            raw_response = "\n".join(lines).strip()

        verdict_data = json.loads(raw_response)
        verdict = verdict_data.get("verdict", "").upper()
        reason = verdict_data.get("reason", "No reason provided.")

        if verdict == ValidationResult.APPROVED:
            agent_logger.info(
                LLM_GUARDRAIL_PASSED,
                event=EventName.LLM_GUARDRAIL_PASSED,
                payload={"reason": reason},
            )
            return ValidationOutcome(verdict=ValidationResult.APPROVED, reason=reason)

        if verdict == ValidationResult.WARN:
            agent_logger.warning(
                LLM_GUARDRAIL_FAILED.format(reason=reason),
                event=EventName.LLM_GUARDRAIL_PASSED,
                payload={"reason": reason, "verdict": "WARN"},
            )
            return ValidationOutcome(
                verdict=ValidationResult.WARN,
                reason=reason,
                warn=True,
                warn_message=reason,
            )

        agent_logger.warning(
            LLM_GUARDRAIL_FAILED.format(reason=reason),
            event=EventName.LLM_GUARDRAIL_FAILED,
            payload={"reason": reason, "sql": sql},
        )
        return ValidationOutcome(
            verdict=ValidationResult.REJECTED,
            rule_code="LLM_GUARDRAIL",
            reason=reason,
        )

    except json.JSONDecodeError as e:
        reason = f"LLM guardrail returned invalid JSON: {str(e)}"
        agent_logger.error(
            reason,
            event=EventName.LLM_GUARDRAIL_FAILED,
            payload={"raw_response": raw_response, "error": str(e)},
        )
        # Fail open on JSON parse error — do not block a potentially valid query
        # due to an LLM formatting issue. Log it and approve.
        return ValidationOutcome(verdict=ValidationResult.APPROVED, reason=reason)

    except Exception as e:
        reason = f"LLM guardrail call failed: {str(e)}"
        agent_logger.error(
            reason,
            event=EventName.LLM_GUARDRAIL_FAILED,
            payload={"error": str(e)},
            exc_info=True,
        )
        # Fail open on unexpected errors — hard rules already passed
        return ValidationOutcome(verdict=ValidationResult.APPROVED, reason=reason)


# ---------------------------------------------------------------------------
# Main validator entry point
# ---------------------------------------------------------------------------

def validate_query(
    sql: str,
    question: str,
    schema_context: str,
    session_id: str,
    conversation_history: str = "",
) -> ValidationOutcome:
    agent_logger = AgentLogger(
        agent_name=AgentName.QUERY_VALIDATOR,
        session_id=session_id,
    )

    agent_logger.info(
        VALIDATION_STARTED,
        event=EventName.VALIDATION_STARTED,
        payload={"sql": sql},
    )

    hard_rule_outcome = run_hard_rules(sql, agent_logger)
    if not hard_rule_outcome.approved:
        agent_logger.warning(
            VALIDATION_REJECTED.format(reason=hard_rule_outcome.reason),
            event=EventName.VALIDATION_REJECTED,
            payload={
                "layer": "hard_rules",
                "rule_code": hard_rule_outcome.rule_code,
                "reason": hard_rule_outcome.reason,
            },
        )
        return hard_rule_outcome

    # Layer 2 — LLM guardrail, only if hard rules pass and guardrail is enabled
    if not settings.enable_llm_guardrail:
        agent_logger.info(
            "LLM guardrail disabled — skipping",
            event=EventName.VALIDATION_APPROVED,
            payload={"sql": sql},
        )
        return ValidationOutcome(verdict=ValidationResult.APPROVED)

    llm_outcome = run_llm_guardrail(
        sql, question, schema_context, agent_logger, conversation_history
    )
    
    if not llm_outcome.approved:
        agent_logger.warning(
            VALIDATION_REJECTED.format(reason=llm_outcome.reason),
            event=EventName.VALIDATION_REJECTED,
            payload={
                "layer": "llm_guardrail",
                "reason": llm_outcome.reason,
            },
        )
        return llm_outcome

    if llm_outcome.warn:
        agent_logger.warning(
            "Query approved with warning: {warn}".format(warn=llm_outcome.warn_message),
            event=EventName.LLM_GUARDRAIL_PASSED,
            payload={"warn_message": llm_outcome.warn_message},
        )
        return llm_outcome

    agent_logger.info(
        VALIDATION_APPROVED.format(retry_count=0),
        event=EventName.VALIDATION_APPROVED,
        payload={"sql": sql},
    )
    return ValidationOutcome(verdict=ValidationResult.APPROVED)