import pyodbc
from app.config import settings


def get_mssql_connection() -> pyodbc.Connection:
    """
    Returns a fresh pyodbc connection to the eCommerce database.
    Always creates a new connection — never reuses an existing one.
    Each caller is responsible for closing it.
    """
    if settings.mssql_use_windows_auth:
        conn_str = (
            f"DRIVER={{{settings.mssql_driver}}};"
            f"SERVER={settings.mssql_server};"
            f"DATABASE={settings.mssql_database};"
            f"Trusted_Connection=yes;"
            f"TrustServerCertificate=yes;"
        )
    else:
        conn_str = (
            f"DRIVER={{{settings.mssql_driver}}};"
            f"SERVER={settings.mssql_server};"
            f"DATABASE={settings.mssql_database};"
            f"UID={settings.mssql_username};"
            f"PWD={settings.mssql_password};"
            f"TrustServerCertificate=yes;"
        )
    return pyodbc.connect(conn_str)