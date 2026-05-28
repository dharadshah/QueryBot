import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.observability.logger import setup_logging
from app.tools.db_query_tool import execute_query

setup_logging("INFO")

TEST_SESSION_ID = "manual-test-001"

# Test 1 - basic product query
print("\n--- Test 1: Products query ---")
rows = execute_query(
    "SELECT product_name, unit_price FROM products WHERE is_active = 1",
    session_id=TEST_SESSION_ID,
)
for row in rows:
    print(row)

# Test 2 - verify TOP clause is enforced
print("\n--- Test 2: TOP clause enforcement ---")
rows = execute_query(
    "SELECT order_id, total_amount FROM orders",
    session_id=TEST_SESSION_ID,
)
print(f"Rows returned: {len(rows)} (should be max 20)")

# Test 3 - join query
print("\n--- Test 3: Join query ---")
rows = execute_query(
    """
    SELECT TOP 5 c.first_name, c.last_name, COUNT(o.order_id) AS total_orders
    FROM customers c
    JOIN orders o ON c.customer_id = o.customer_id
    GROUP BY c.first_name, c.last_name
    """,
    session_id=TEST_SESSION_ID,
)
for row in rows:
    print(row)