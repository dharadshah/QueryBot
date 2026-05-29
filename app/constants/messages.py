# Session messages
SESSION_STARTED = "Session started with id: {session_id}"
SESSION_COMPLETED = "Session completed with id: {session_id}"
SESSION_FAILED = "Session failed with id: {session_id} - {error}"

# Schema retriever messages
SCHEMA_RETRIEVAL_STARTED = "Retrieving relevant schema chunks for question: {question}"
SCHEMA_RETRIEVAL_COMPLETED = "Retrieved {chunk_count} schema chunks"
SCHEMA_RETRIEVAL_FAILED = "Schema retrieval failed: {error}"

# Query generator messages
QUERY_GENERATION_STARTED = "Generating SQL query for question: {question}"
QUERY_GENERATION_COMPLETED = "SQL query generated successfully"
QUERY_GENERATION_FAILED = "SQL query generation failed: {error}"

# Validator messages
VALIDATION_STARTED = "Starting validation for generated query"
HARD_RULE_PASSED = "All hard rules passed"
HARD_RULE_FAILED = "Hard rule failed - rule: {rule_code}, reason: {reason}"
LLM_GUARDRAIL_PASSED = "LLM guardrail passed"
LLM_GUARDRAIL_FAILED = "LLM guardrail failed - reason: {reason}"
VALIDATION_APPROVED = "Query approved after {retry_count} attempt(s)"
VALIDATION_REJECTED = "Query rejected - reason: {reason}"
RETRY_ATTEMPT = "Retry attempt {attempt} of {max_retries}"
MAX_RETRIES_EXCEEDED = "Maximum retries of {max_retries} exceeded. Aborting."

# DB tool messages
QUERY_EXECUTION_STARTED = "Executing approved SQL query"
QUERY_EXECUTION_COMPLETED = "Query executed successfully, {row_count} row(s) returned"
QUERY_EXECUTION_FAILED = "Query execution failed: {error}"
TOP_CLAUSE_ENFORCED = "TOP {max_rows} clause enforced on query"

# Response synthesiser messages
RESPONSE_SYNTHESIS_STARTED = "Synthesising natural language response"
RESPONSE_SYNTHESIS_COMPLETED = "Response synthesised successfully"
RESPONSE_SYNTHESIS_FAILED = "Response synthesis failed: {error}"

# User facing messages
NO_RESULTS_FOUND = "No results were found for your question."
QUERY_FAILED_USER = "I was unable to process your question at this time. Please try rephrasing it."
MAX_RETRIES_USER = "I was unable to generate a valid query for your question after several attempts. Please try rephrasing."
DB_UNAVAILABLE = "The database is currently unavailable. Please try again later."

# Results cap warning
RESULTS_CAPPED_WARNING = (
    "Note: this query returned the maximum of {max_rows} rows. "
    "There may be additional results beyond what is shown."
)
UNBOUNDED_QUERY_WARNING = (
    "Note: your question asked for all results but output is limited to {max_rows} rows. "
    "The results shown may be incomplete."
)

EXECUTION_PLAN_TABLE_SCAN = (
    "Query causes a full table scan on '{table}' "
    "with an estimated {rows} rows. "
    "Rewrite the query to use indexed columns in the WHERE or JOIN condition."
)
EXECUTION_PLAN_MISSING_INDEX = (
    "MSSQL recommends a missing index on '{table}' "
    "for columns: {columns}. "
    "Rewrite the query to use existing indexed columns where possible."
)
EXECUTION_PLAN_CHECK_FAILED = (
    "Execution plan could not be retrieved: {error}"
)

VAGUE_QUESTION_USER = (
    "Your question needs more context. "
    "Could you please be more specific about what you are looking for?"
)

WRITE_INTENT_DETECTED = (
    "I can only retrieve information from the database. "
    "Actions like adding, updating, or deleting records are not permitted."
)