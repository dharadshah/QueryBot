class AppConfig:
    MAX_ROWS = 20
    MAX_RETRIES = 3
    TOP_K_CHUNKS = 5


class UserRole:
    GUEST = "guest"
    CUSTOMER = "customer"
    ADMIN = "admin"

    ALL = [GUEST, CUSTOMER, ADMIN]


class OrderStatus:
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

    ALL = [PENDING, CONFIRMED, SHIPPED, DELIVERED, CANCELLED]


class ValidationResult:
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    WARN = "WARN"


class AgentName:
    SCHEMA_RETRIEVER = "schema_retriever"
    QUERY_GENERATOR = "query_generator"
    QUERY_VALIDATOR = "query_validator"
    RESPONSE_SYNTHESISER = "response_synthesiser"
    ORCHESTRATOR = "orchestrator"
    DB_QUERY_TOOL = "db_query_tool"


class EventName:
    # Orchestrator events
    SESSION_STARTED = "session_started"
    SESSION_COMPLETED = "session_completed"
    SESSION_FAILED = "session_failed"

    # Schema retriever events
    SCHEMA_RETRIEVAL_STARTED = "schema_retrieval_started"
    SCHEMA_RETRIEVAL_COMPLETED = "schema_retrieval_completed"

    # Query generator events
    QUERY_GENERATION_STARTED = "query_generation_started"
    QUERY_GENERATION_COMPLETED = "query_generation_completed"
    QUERY_GENERATION_FAILED = "query_generation_failed"

    # Query validator events
    VALIDATION_STARTED = "validation_started"
    HARD_RULE_PASSED = "hard_rule_passed"
    HARD_RULE_FAILED = "hard_rule_failed"
    LLM_GUARDRAIL_PASSED = "llm_guardrail_passed"
    LLM_GUARDRAIL_FAILED = "llm_guardrail_failed"
    VALIDATION_APPROVED = "validation_approved"
    VALIDATION_REJECTED = "validation_rejected"
    RETRY_ATTEMPT = "retry_attempt"
    MAX_RETRIES_EXCEEDED = "max_retries_exceeded"

    # DB tool events
    QUERY_EXECUTION_STARTED = "query_execution_started"
    QUERY_EXECUTION_COMPLETED = "query_execution_completed"
    QUERY_EXECUTION_FAILED = "query_execution_failed"

    # Response synthesiser events
    RESPONSE_SYNTHESIS_STARTED = "response_synthesis_started"
    RESPONSE_SYNTHESIS_COMPLETED = "response_synthesis_completed"


class HardRuleCode:
    NOT_SELECT = "NOT_SELECT"
    DISALLOWED_KEYWORD = "DISALLOWED_KEYWORD"
    DANGEROUS_SYSTEM_CALL = "DANGEROUS_SYSTEM_CALL"
    COMMENT_INJECTION = "COMMENT_INJECTION"
    SEMICOLON_STACKING = "SEMICOLON_STACKING"
    MISSING_TOP_CLAUSE = "MISSING_TOP_CLAUSE"
    CARTESIAN_JOIN = "CARTESIAN_JOIN"
    SYNTAX_ERROR = "SYNTAX_ERROR"
    EXECUTION_PLAN = "EXECUTION_PLAN"        


class DisallowedKeyword:
    LIST = [
        "INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE",
        "ALTER", "CREATE", "EXEC", "EXECUTE", "MERGE",
        "BULK", "RESTORE", "BACKUP",
    ]


class DangerousSystemCall:
    LIST = [
        "xp_", "sp_", "OPENROWSET", "OPENDATASOURCE",
        "OPENQUERY", "BULK INSERT",
    ]


class LogField:
    TIMESTAMP = "timestamp"
    SESSION_ID = "session_id"
    AGENT = "agent"
    EVENT = "event"
    LEVEL = "level"
    PAYLOAD = "payload"
    LATENCY_MS = "latency_ms"