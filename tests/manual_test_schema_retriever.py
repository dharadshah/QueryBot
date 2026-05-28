import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.observability.logger import setup_logging
from app.agents.schema_retriever import retrieve_schema_context

setup_logging("INFO")

TEST_SESSION_ID = "manual-test-002"

questions = [
    "Show me all products in the electronics category",
    "What are the total sales per customer",
    "List all pending orders",
]

for question in questions:
    print(f"\n--- Question: {question} ---")
    context = retrieve_schema_context(question, session_id=TEST_SESSION_ID)
    print(context[:500])
    print("...")