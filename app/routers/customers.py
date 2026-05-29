import pyodbc
from fastapi import APIRouter
from app.config import settings

router = APIRouter(prefix="/customers", tags=["customers"])


def get_connection():
    if settings.mssql_use_windows_auth:
        return pyodbc.connect(
            f"DRIVER={{{settings.mssql_driver}}};"
            f"SERVER={settings.mssql_server};"
            f"DATABASE={settings.mssql_database};"
            f"Trusted_Connection=yes;"
            f"TrustServerCertificate=yes;"
        )
    return pyodbc.connect(
        f"DRIVER={{{settings.mssql_driver}}};"
        f"SERVER={settings.mssql_server};"
        f"DATABASE={settings.mssql_database};"
        f"UID={settings.mssql_username};"
        f"PWD={settings.mssql_password};"
        f"TrustServerCertificate=yes;"
    )


@router.get("")
def list_customers():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT customer_id, first_name, last_name FROM customers ORDER BY first_name"
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [
        {
            "customer_id": row[0],
            "name": f"{row[1]} {row[2]}",
        }
        for row in rows
    ]