import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.observability.logger import setup_logging
from app.schemas.chat import ChatRequest
from app.services.chat_service import process_chat

setup_logging("INFO")

questions = [
    # Original tests
    "Show me all products in the electronics category",
    "What are the total sales per customer",
    "List all pending orders with customer names",
    "Which products are out of stock",
    "List all orders",
    # Aggregation tests
    "How many products are in the electronics category?",
    "Which product has the maximum sale in the past month? How much?",
    "Give me top 5 customers based on their total purchases in the last month",
    "How many pending orders do we have?",
    "How many pending orders to Canada?",
]

for question in questions:
    print(f"\n{'='*60}")
    print(f"Question: {question}")
    print("="*60)

    request = ChatRequest(question=question)
    response = process_chat(request=request)

    print(f"\nAnswer:\n{response.answer}")
    print(f"\nSQL Used:\n{response.sql_generated}")
    print(f"\nRows returned: {response.rows_returned}")
    print(f"Success: {response.success}")
    if response.error:
        print(f"Error: {response.error}")