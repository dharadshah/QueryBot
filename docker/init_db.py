import time
import pyodbc
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def wait_for_db(max_attempts: int = 30) -> pyodbc.Connection:
    from app.config import settings
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={settings.mssql_server};"
        f"UID={settings.mssql_username};"
        f"PWD={settings.mssql_password};"
        f"TrustServerCertificate=yes;"
    )
    for attempt in range(max_attempts):
        try:
            conn = pyodbc.connect(conn_str, timeout=5)
            print(f"Connected to SQL Server on attempt {attempt + 1}")
            return conn
        except Exception as e:
            print(f"Attempt {attempt + 1}/{max_attempts} failed: {e}")
            time.sleep(2)
    raise RuntimeError("Could not connect to SQL Server after maximum attempts.")


def create_database(conn: pyodbc.Connection) -> None:
    conn.autocommit = True
    cursor = conn.cursor()
    cursor.execute("""
        IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'QueryBotDB')
        CREATE DATABASE QueryBotDB
    """)
    cursor.close()
    conn.autocommit = False
    print("Database QueryBotDB created or verified.")


if __name__ == "__main__":
    print("Waiting for SQL Server to be ready...")
    conn = wait_for_db()
    create_database(conn)
    conn.close()

    print("Running seed script...")
    from seed.seed_data import run
    run()
    print("Database initialisation complete.")