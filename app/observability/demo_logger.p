import time
from app.config import settings

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