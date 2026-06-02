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
    EXECUTION_PLAN_TABLE_SCAN,
    EXECUTION_PLAN_MISSING_INDEX,
    EXECUTION_PLAN_CHECK_FAILED,
)

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

def _check_comment_injection(sql: str) -> ValidationOutcome:
    if "--" in sql or "/*" in sql:
        return ValidationOutcome(
            verdict=ValidationResult.REJECTED,
            rule_code=HardRuleCode.COMMENT_INJECTION,
            reason="SQL comments are not allowed in queries.",
        )
    return ValidationOutcome(verdict=ValidationResult.APPROVED)


def _check_semicolon_stacking(sql: str) -> ValidationOutcome:
    stripped = sql.rstrip().rstrip(";").strip()
    if ";" in stripped:
        return ValidationOutcome(
            verdict=ValidationResult.REJECTED,
            rule_code=HardRuleCode.SEMICOLON_STACKING,
            reason="Multiple statements detected. Only a single SELECT is allowed.",
        )
    return ValidationOutcome(verdict=ValidationResult.APPROVED)


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
    from app.utils.execution_plan import check_query_plan

    result = check_query_plan(sql)

    if result["success"]:
        try:
            import app.observability.demo_logger as demo_logger
            demo_logger.execution_plan_result(
                max_rows=result["max_estimated_rows"],
                statement_cost=result["statement_cost"],
                operations=result["operations"],
                table_scans=result["table_scans"],
                missing_indexes=result["missing_indexes"],
                score=result.get("score", 0),
                score_label=result.get("score_label", "UNKNOWN"),
                score_deductions=result.get("score_deductions", []),
            )
        except Exception:
            pass

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

    logger.info(
        "Execution plan check passed",
        extra={
            "agent": AgentName.QUERY_VALIDATOR,
            "event": EventName.HARD_RULE_PASSED,
            "session_id": None,
            "payload": {
                "max_estimated_rows": result["max_estimated_rows"],
                "score": result.get("score"),
                "score_label": result.get("score_label"),
                "table_scans": result["table_scans"],
                "missing_indexes": result["missing_indexes"],
            },
        },
    )
    return ValidationOutcome(verdict=ValidationResult.APPROVED)

def run_llm_plan_analyser(
    sql: str,
    plan_result: dict,
    schema_context: str,
    session_id: str,
) -> ValidationOutcome:
    import time
    import app.observability.demo_logger as demo_logger
    from app.constants.prompts import (
        LLM_PLAN_ANALYSER_SYSTEM_PROMPT,
        LLM_PLAN_ANALYSER_USER_PROMPT,
    )
    from app.constants.messages import (
        PLAN_ANALYSIS_STARTED,
        PLAN_ANALYSIS_APPROVED,
        PLAN_ANALYSIS_WARNED,
        PLAN_ANALYSIS_REJECTED,
    )

    agent_logger = AgentLogger(
        agent_name=AgentName.LLM_PLAN_ANALYSER,
        session_id=session_id,
    )

    agent_logger.info(
        PLAN_ANALYSIS_STARTED,
        event=EventName.PLAN_ANALYSIS_STARTED,
        payload={"score": plan_result.get("score")},
    )

    # Build a concise plan summary for the LLM — avoid sending raw XML
    ops_summary = []
    for op in plan_result.get("operations", []):
        entry = f"{op['physical_op']}"
        if op.get("table"):
            entry += f" on {op['table']}"
        entry += f" (est. {op['estimated_rows']:,} rows)"
        ops_summary.append(entry)

    plan_summary = (
        f"Statement cost    : {plan_result.get('statement_cost', 0)}\n"
        f"Max estimated rows: {plan_result.get('max_estimated_rows', 0):,}\n"
        f"Efficiency score  : {plan_result.get('score', 0)}/100 "
        f"({plan_result.get('score_label', 'UNKNOWN')})\n"
        f"Operations        :\n"
        + "\n".join(f"  - {op}" for op in ops_summary)
        + (
            f"\nTable scans       : {len(plan_result.get('table_scans', []))} detected"
            if plan_result.get("table_scans") else "\nTable scans       : None"
        )
        + (
            f"\nMissing indexes   : {len(plan_result.get('missing_indexes', []))} suggested"
            if plan_result.get("missing_indexes") else "\nMissing indexes   : None"
        )
    )

    start_time = time.monotonic()

    try:
        client = get_llm_client()

        response = client.chat.completions.create(
            model=settings.active_chat_model,
            messages=[
                {
                    "role": "system",
                    "content": LLM_PLAN_ANALYSER_SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": LLM_PLAN_ANALYSER_USER_PROMPT.format(
                        sql_query=sql,
                        plan_summary=plan_summary,
                        schema_context=schema_context[:1000],
                    ),
                },
            ],
            temperature=0.0,
            max_tokens=300,
        )

        latency_ms = int((time.monotonic() - start_time) * 1000)
        raw_response = response.choices[0].message.content.strip()

        if raw_response.startswith("```"):
            lines = raw_response.splitlines()
            lines = [l for l in lines if not l.strip().startswith("```")]
            raw_response = "\n".join(lines).strip()

        verdict_data = json.loads(raw_response)
        verdict = verdict_data.get("verdict", "APPROVED").upper()
        reason = verdict_data.get("reason", "No reason provided.")
        findings = verdict_data.get("findings", [])

        demo_logger.llm_plan_analyser(
            verdict=verdict,
            reason=reason,
            findings=findings,
            latency_ms=latency_ms,
        )

        if verdict == ValidationResult.APPROVED:
            agent_logger.info(
                PLAN_ANALYSIS_APPROVED.format(reason=reason),
                event=EventName.PLAN_ANALYSIS_APPROVED,
                payload={"reason": reason, "findings": findings},
            )
            return ValidationOutcome(verdict=ValidationResult.APPROVED, reason=reason)

        if verdict == ValidationResult.WARN:
            agent_logger.warning(
                PLAN_ANALYSIS_WARNED.format(reason=reason),
                event=EventName.PLAN_ANALYSIS_WARNED,
                payload={"reason": reason, "findings": findings},
            )
            return ValidationOutcome(
                verdict=ValidationResult.WARN,
                reason=reason,
                warn=True,
                warn_message=f"Performance note: {reason}",
            )

        agent_logger.warning(
            PLAN_ANALYSIS_REJECTED.format(reason=reason),
            event=EventName.PLAN_ANALYSIS_REJECTED,
            payload={"reason": reason, "findings": findings},
        )
        return ValidationOutcome(
            verdict=ValidationResult.REJECTED,
            rule_code=HardRuleCode.LLM_PLAN_ANALYSIS,
            reason=reason,
        )

    except json.JSONDecodeError as e:
        logger.warning("LLM plan analyser returned invalid JSON: %s", str(e))
        return ValidationOutcome(verdict=ValidationResult.APPROVED)

    except Exception as e:
        logger.warning("LLM plan analyser failed: %s", str(e))
        return ValidationOutcome(verdict=ValidationResult.APPROVED)

# ---------------------------------------------------------------------------
# run_hard_rules — must be defined AFTER all _check_* functions
# ---------------------------------------------------------------------------

def run_hard_rules(sql: str, agent_logger: AgentLogger) -> ValidationOutcome:
    import app.observability.demo_logger as demo_logger

    rules = [
        (_check_comment_injection,      "Comment injection"),
        (_check_semicolon_stacking,     "Semicolon stacking"),
        (_check_syntax,                 "T-SQL syntax"),
        (_check_select_only,            "SELECT only"),
        (_check_disallowed_keywords,    "Disallowed keywords"),
        (_check_dangerous_system_calls, "Dangerous system calls"),
        (_check_top_clause,             "TOP clause present"),
        (_check_cartesian_join,         "No cartesian joins"),
        (_check_execution_plan,         "Execution plan (MSSQL)"),
    ]

    demo_logger.hard_rules_header()

    for rule_fn, rule_name in rules:
        outcome = rule_fn(sql)
        # Skip demo check display for execution plan — it has its own display
        if rule_name != "Execution plan (MSSQL)":
            demo_logger.hard_rule_check(rule_name, outcome.approved, outcome.reason or "")
        else:
            demo_logger.hard_rule_check(rule_name, outcome.approved, outcome.reason or "")

        if not outcome.approved:
            demo_logger.hard_rules_result(passed=False)
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

    demo_logger.hard_rules_result(passed=True)
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
    import app.observability.demo_logger as demo_logger

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
            max_tokens=150,
        )

        raw_response = response.choices[0].message.content.strip()

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
            payload={"error": str(e)},
        )
        return ValidationOutcome(verdict=ValidationResult.APPROVED, reason=reason)

    except Exception as e:
        reason = f"LLM guardrail call failed: {str(e)}"
        agent_logger.error(
            reason,
            event=EventName.LLM_GUARDRAIL_FAILED,
            payload={"error": str(e)},
            exc_info=True,
        )
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
    import app.observability.demo_logger as demo_logger

    agent_logger = AgentLogger(
        agent_name=AgentName.QUERY_VALIDATOR,
        session_id=session_id,
    )

    agent_logger.info(
        VALIDATION_STARTED,
        event=EventName.VALIDATION_STARTED,
        payload={"sql": sql},
    )

    # Layer 1 — Hard rules first, always
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

    # Layer 1b — LLM Plan Analyser (optional)
    if settings.enable_llm_plan_analyser:
        from app.utils.execution_plan import check_query_plan
        plan_result = check_query_plan(sql)
        if plan_result["success"]:
            plan_outcome = run_llm_plan_analyser(
                sql=sql,
                plan_result=plan_result,
                schema_context=schema_context,
                session_id=session_id,
            )
            if not plan_outcome.approved:
                agent_logger.warning(
                    VALIDATION_REJECTED.format(reason=plan_outcome.reason),
                    event=EventName.VALIDATION_REJECTED,
                    payload={
                        "layer": "llm_plan_analyser",
                        "reason": plan_outcome.reason,
                    },
                )
                return plan_outcome

            if plan_outcome.warn:
                agent_logger.warning(
                    "LLM plan analyser warning",
                    event=EventName.PLAN_ANALYSIS_WARNED,
                    payload={"warn_message": plan_outcome.warn_message},
                )
                
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