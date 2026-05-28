import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.observability.logger import setup_logging
from app.agents.schema_retriever import retrieve_schema_context
from app.agents.query_generator import generate_query
from app.agents.query_validator import validate_query
from app.constants.app_constants import ValidationResult

setup_logging("INFO")

TEST_SESSION_ID = "manual-test-003"

questions = [
    "Show me all products in the electronics category",
    "What are the total sales per customer",
    "List all pending orders with customer names",
]

for question in questions:
    print(f"\n{'='*60}")
    print(f"Question: {question}")
    print('='*60)

    # Step 1 - retrieve schema context
    schema_context = retrieve_schema_context(question, session_id=TEST_SESSION_ID)

    # Step 2 - generate SQL
    sql = generate_query(
        question=question,
        schema_context=schema_context,
        session_id=TEST_SESSION_ID,
    )
    print(f"\nGenerated SQL:\n{sql}")

    # Step 3 - validate SQL
    outcome = validate_query(
        sql=sql,
        question=question,
        schema_context=schema_context,
        session_id=TEST_SESSION_ID,
    )

    print(f"\nValidation verdict: {outcome.verdict}")
    if not outcome.approved:
        print(f"Rejection reason: {outcome.reason}")