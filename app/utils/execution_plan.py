import logging
import xml.etree.ElementTree as ET
import pyodbc
from app.config import settings

logger = logging.getLogger(__name__)

SHOWPLAN_NAMESPACE = "http://schemas.microsoft.com/sqlserver/2004/07/showplan"
ESTIMATED_ROWS_THRESHOLD = 1000


def get_ecommerce_connection() -> pyodbc.Connection:
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


def get_execution_plan_xml(sql: str) -> str | None:
    try:
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

        with pyodbc.connect(conn_str) as conn:
            cursor = conn.cursor()
            cursor.execute("SET SHOWPLAN_XML ON;")
            cursor.execute(sql)
            row = cursor.fetchone()
            plan_xml = row[0] if row else None
            cursor.execute("SET SHOWPLAN_XML OFF;")
            return plan_xml

    except pyodbc.Error as e:
        logger.error("Failed to retrieve execution plan: %s", str(e))
        return None
    except Exception as e:
        logger.error("Unexpected error in execution plan: %s", str(e))
        return None


def analyse_execution_plan(xml_string: str) -> dict:
    """
    Parses execution plan XML and extracts:
    - table_scans  : list of table names with full scans
    - missing_indexes : list of missing index suggestions from MSSQL
    - max_estimated_rows : highest estimated row count across all operations
    - has_warnings : True if any actionable issue was found
    """
    result = {
        "table_scans": [],
        "missing_indexes": [],
        "max_estimated_rows": 0,
        "has_warnings": False,
    }

    try:
        ns = {"sp": SHOWPLAN_NAMESPACE}
        root = ET.fromstring(xml_string)

        # Detect Table Scans
        for rel_scan in root.iter(f"{{{SHOWPLAN_NAMESPACE}}}RelOp"):
            physical_op = rel_scan.attrib.get("PhysicalOp", "")
            estimated_rows = float(rel_scan.attrib.get("EstimateRows", 0))

            if estimated_rows > result["max_estimated_rows"]:
                result["max_estimated_rows"] = int(estimated_rows)

            if physical_op == "Table Scan":
                # Get the table name from the nested object node
                for obj in rel_scan.iter(f"{{{SHOWPLAN_NAMESPACE}}}Object"):
                    table = obj.attrib.get("Table", "unknown")
                    table = table.strip("[]")
                    if estimated_rows > ESTIMATED_ROWS_THRESHOLD:
                        result["table_scans"].append({
                            "table": table,
                            "estimated_rows": int(estimated_rows),
                        })
                        result["has_warnings"] = True

        # Detect Missing Index warnings from MSSQL
        for missing in root.iter(f"{{{SHOWPLAN_NAMESPACE}}}MissingIndex"):
            database = missing.attrib.get("Database", "").strip("[]")
            schema = missing.attrib.get("Schema", "").strip("[]")
            table = missing.attrib.get("Table", "").strip("[]")

            columns = []
            for col_group in missing.iter(f"{{{SHOWPLAN_NAMESPACE}}}ColumnGroup"):
                usage = col_group.attrib.get("Usage", "")
                for col in col_group.iter(f"{{{SHOWPLAN_NAMESPACE}}}Column"):
                    col_name = col.attrib.get("Name", "").strip("[]")
                    columns.append(f"{col_name} ({usage})")

            result["missing_indexes"].append({
                "table": f"{schema}.{table}",
                "columns": columns,
            })
            result["has_warnings"] = True

    except ET.ParseError as e:
        logger.error("Failed to parse execution plan XML: %s", str(e))

    return result


def check_query_plan(sql: str) -> dict:
    """
    Main entry point. Returns a dict with:
    - success      : whether the plan was retrieved and parsed
    - has_warnings : whether any issues were found
    - table_scans  : list of problematic table scans
    - missing_indexes : list of missing index suggestions
    - max_estimated_rows : highest row estimate in the plan
    - error        : error message if success is False
    """
    xml_string = get_execution_plan_xml(sql)

    if xml_string is None:
        return {
            "success": False,
            "has_warnings": False,
            "table_scans": [],
            "missing_indexes": [],
            "max_estimated_rows": 0,
            "error": "Could not retrieve execution plan.",
        }

    analysis = analyse_execution_plan(xml_string)
    analysis["success"] = True
    analysis["error"] = None
    return analysis