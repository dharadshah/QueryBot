import sys
sys.path.append("D:\\QueryBot")

from app.tools.db_query_tool import execute_query

sql = "SELECT TOP 20 COUNT(order_id) FROM orders WHERE status = 'pending'"
rows = execute_query(sql, "debug-001")
print("rows:", rows)
print("type:", type(list(rows[0].values())[0]))
print("value:", list(rows[0].values())[0])