import time
from app.config import settings
from app.utils.execution_plan import OPERATION_SCORES

# ANSI colours
RESET   = "\033[0m"
BOLD    = "\033[1m"
CYAN    = "\033[96m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
RED     = "\033[91m"
BLUE    = "\033[94m"
MAGENTA = "\033[95m"
DIM     = "\033[2m"
WHITE   = "\033[97m"


def _enabled() -> bool:
    return settings.demo_mode


def _box(lines: list[str], colour: str = CYAN) -> None:
    width = max(len(l) for l in lines) + 4
    print(f"{colour}{BOLD}╔{'═' * width}╗{RESET}")
    for line in lines:
        padding = width - len(line)
        print(f"{colour}{BOLD}║  {RESET}{line}{' ' * padding}{colour}{BOLD}  ║{RESET}")
    print(f"{colour}{BOLD}╚{'═' * width}╝{RESET}")


def _header(agent: str, colour: str = BLUE) -> None:
    print(f"\n{colour}{BOLD}[{agent}]{RESET}")


def _row(label: str, value: str, colour: str = WHITE) -> None:
    print(f"  {DIM}{label:<10}{RESET} {colour}{value}{RESET}")


def _check(label: str, passed: bool) -> None:
    icon = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
    print(f"  {DIM}Checking :{RESET} {label:<35} {icon}")


def session_start(
    session_id: str,
    question: str,
    role: str,
    customer_id: int = None,
) -> None:
    if not _enabled():
        return
    customer_line = f"Customer : {customer_id}" if customer_id else None
    lines = [
        "QueryBot  —  New Session",
        f"Session  : {session_id[:8]}...",
        f"Role     : {role.capitalize()}",
    ]
    if customer_line:
        lines.append(customer_line)
    lines.append(f"Question : {question}")
    _box(lines, CYAN)


def session_end(
    total_ms: int,
    retry_count: int,
    rows_returned: int,
    success: bool,
) -> None:
    if not _enabled():
        return
    colour = GREEN if success else RED
    status = "Session Complete" if success else "Session Failed"
    _box(
        [
            status,
            f"Total time : {total_ms:,}ms   "
            f"Retries: {retry_count}   "
            f"Rows: {rows_returned}",
        ],
        colour,
    )


def schema_retrieval(chunk_count: int, latency_ms: int) -> None:
    if not _enabled():
        return
    _header("Agent 0 — Schema Retriever", BLUE)
    _row("Action :", "Querying ChromaDB for relevant schema chunks")
    _row("Output :", f"{chunk_count} chunks retrieved")
    _row("Time   :", f"{latency_ms:,}ms")


def query_generation(sql: str, latency_ms: int, is_retry: bool = False) -> None:
    if not _enabled():
        return
    label = "Agent 1 — Query Generator"
    if is_retry:
        label += " (RETRY)"
    _header(label, MAGENTA)
    _row("Action :", "Calling LLM to generate T-SQL")
    # Format SQL with indentation
    sql_lines = sql.strip().split("\n")
    _row("Output :", sql_lines[0])
    for line in sql_lines[1:]:
        print(f"             {DIM}{line}{RESET}")
    _row("Time   :", f"{latency_ms:,}ms")


def hard_rule_check(rule_name: str, passed: bool, detail: str = "") -> None:
    if not _enabled():
        return
    _check(rule_name, passed)
    if not passed and detail:
        print(f"           {RED}  Reason: {detail}{RESET}")


def hard_rules_header() -> None:
    if not _enabled():
        return
    _header("Agent 2 — Query Validator — Layer 1: Hard Rules", YELLOW)


def hard_rules_result(passed: bool) -> None:
    if not _enabled():
        return
    if passed:
        print(f"  {GREEN}{BOLD}Result   : ALL HARD RULES PASSED{RESET}")
    else:
        print(f"  {RED}{BOLD}Result   : HARD RULE FAILED — query rejected{RESET}")


def llm_guardrail(
    verdict: str,
    reason: str,
    latency_ms: int,
) -> None:
    if not _enabled():
        return
    _header("Agent 2 — Query Validator — Layer 2: LLM Guardrail", YELLOW)
    _row("Action :", "Calling LLM to evaluate query semantics")
    colour = GREEN if verdict == "APPROVED" else (YELLOW if verdict == "WARN" else RED)
    _row("Verdict:", f"{colour}{BOLD}{verdict}{RESET}")
    _row("Reason :", reason)
    _row("Time   :", f"{latency_ms:,}ms")


def db_tool(sql: str, row_count: int, latency_ms: int) -> None:
    if not _enabled():
        return
    _header("Tool — DB Query Tool", CYAN)
    sql_lines = sql.strip().split("\n")
    _row("SQL    :", sql_lines[0])
    for line in sql_lines[1:]:
        print(f"             {DIM}{line}{RESET}")
    _row("Action :", "Executing against QueryBotDB")
    _row("Output :", f"{row_count} row(s) returned  [execution: {latency_ms}ms]")


def response_synthesis(answer: str, latency_ms: int) -> None:
    if not _enabled():
        return
    _header("Agent 3 — Response Synthesiser", GREEN)
    _row("Action :", "Calling LLM to generate natural language answer")
    _row("Output :", answer[:120] + ("..." if len(answer) > 120 else ""))
    _row("Time   :", f"{latency_ms:,}ms")


def cache_hit(question: str, ttl_remaining: int) -> None:
    if not _enabled():
        return
    _header("Cache — Query Cache", DIM)
    _row("Status :", f"{GREEN}HIT{RESET} — skipping Agent 1 and Agent 2")
    _row("TTL    :", f"{ttl_remaining}s remaining")


def permission_denied(role: str, reason: str) -> None:
    if not _enabled():
        return
    _header("Permission Check", RED)
    _row("Role   :", role)
    _row("Result :", f"{RED}DENIED{RESET} — {reason}")


def write_intent(question: str) -> None:
    if not _enabled():
        return
    _header("Pre-flight — Write Intent Detected", RED)
    _row("Question:", question)
    _row("Result :", f"{RED}BLOCKED{RESET} — only SELECT queries are permitted")


def retry_attempt(attempt: int, max_retries: int, reason: str) -> None:
    if not _enabled():
        return
    print(
        f"\n  {YELLOW}{BOLD}RETRY {attempt}/{max_retries}{RESET}"
        f"  {DIM}Reason: {reason[:80]}{RESET}"
    )

def execution_plan_result(
    max_rows: int,
    statement_cost: float,
    operations: list,
    table_scans: list,
    missing_indexes: list,
    score: int,
    score_label: str,
    score_deductions: list,
) -> None:
    if not _enabled():
        return

    # Score colour
    if score >= 90:
        score_colour = GREEN
    elif score >= 75:
        score_colour = YELLOW
    elif score >= 60:
        score_colour = YELLOW
    else:
        score_colour = RED

    print(f"\n  {DIM}{'─' * 55}{RESET}")
    print(f"  {BOLD}Execution Plan Analysis{RESET}")
    print(f"  {DIM}{'─' * 55}{RESET}")
    print(f"  {DIM}{'Statement cost':<22}{RESET} {statement_cost}")
    print(f"  {DIM}{'Max estimated rows':<22}{RESET} {max_rows:,}")

    if operations:
        print(f"  {DIM}{'Operations':<22}{RESET}")
        for op in operations:
            op_name = op["physical_op"]
            table = f" on {op['table']}" if op["table"] else ""
            rows = f"est. {op['estimated_rows']:,} rows"
            op_info = OPERATION_SCORES.get(op_name, {"score": 5, "label": "UNKNOWN"})
            op_colour = GREEN if op_info["score"] >= 8 else (
                YELLOW if op_info["score"] >= 5 else RED
            )
            print(
                f"    {op_colour}{op_name:<30}{RESET}"
                f"{table:<20} {DIM}{rows}{RESET}"
            )

    scan_text = f"{RED}WARNING — {len(table_scans)} table scan(s){RESET}" \
        if table_scans else f"{GREEN}None{RESET}"
    idx_text = f"{YELLOW}{len(missing_indexes)} suggestion(s){RESET}" \
        if missing_indexes else f"{GREEN}None{RESET}"

    print(f"  {DIM}{'Table scans':<22}{RESET} {scan_text}")
    print(f"  {DIM}{'Missing indexes':<22}{RESET} {idx_text}")

    if score_deductions:
        print(f"  {DIM}{'Deductions':<22}{RESET}")
        for d in score_deductions:
            print(f"    {RED}{d}{RESET}")

    print(
        f"  {DIM}{'Query score':<22}{RESET} "
        f"{score_colour}{BOLD}{score}/100  —  {score_label}{RESET}"
    )
    print(f"  {DIM}{'─' * 55}{RESET}\n")

def llm_plan_analyser(
    verdict: str,
    reason: str,
    findings: list,
    latency_ms: int,
) -> None:
    if not _enabled():
        return
    _header("Agent 2b — LLM Plan Analyser", YELLOW)
    _row("Action :", "Calling LLM to evaluate execution plan efficiency")
    colour = GREEN if verdict == "APPROVED" else (YELLOW if verdict == "WARN" else RED)
    _row("Verdict:", f"{colour}{BOLD}{verdict}{RESET}")
    _row("Reason :", reason)
    if findings:
        print(f"  {DIM}{'Findings':<10}{RESET}")
        for finding in findings:
            print(f"    {DIM}•{RESET} {finding}")
    _row("Time   :", f"{latency_ms:,}ms")