"""
execution_plan.py
=================
Pre-execution SQL Performance Analysis using MSSQL Estimated Execution Plans.

Overview
--------
This module retrieves and analyses the estimated execution plan for a T-SQL
query BEFORE it is executed against the database. This means zero rows are
read and zero data is touched during the analysis — the database engine
simply computes what it WOULD do if the query ran.

How it works
------------
1. A fresh pyodbc connection is opened to the eCommerce database.
   This must be a dedicated connection — SET SHOWPLAN_XML ON changes
   the connection's behaviour so that every subsequent SQL statement
   returns an XML plan instead of executing. Reusing a shared connection
   would accidentally intercept live queries.

2. SET SHOWPLAN_XML ON is sent to the connection.
   This instructs MSSQL to return the estimated execution plan as XML
   for the next query, rather than running it.

3. The SQL query is sent on the same cursor.
   MSSQL does NOT execute it — it returns one row containing the full
   XML execution plan string.

4. SET SHOWPLAN_XML OFF is sent to restore the connection to normal mode.

5. The XML string is parsed using Python's built-in xml.etree.ElementTree.
   The MSSQL showplan namespace is:
   http://schemas.microsoft.com/sqlserver/2004/07/showplan

XML Structure parsed
--------------------
The plan XML contains a tree of RelOp (Relational Operation) nodes.
Each RelOp represents one physical operation the engine will perform.
Key attributes extracted per RelOp:
  - PhysicalOp     : the operation type (Index Seek, Table Scan, etc.)
  - LogicalOp      : the logical intent (Inner Join, Aggregate, etc.)
  - EstimateRows   : estimated number of rows this operation processes
  - EstimatedTotalSubtreeCost : estimated cost of this operation subtree

The StatementSubTreeCost attribute on StmtSimple gives the total
estimated cost of the entire query.

MissingIndexes nodes are emitted by MSSQL when its query optimiser
knows a better index would improve performance. These are extracted
and surfaced as warnings.

Scoring logic (score_query_plan)
---------------------------------
Each physical operation is assigned a base efficiency score (0-10):
  Index Seek / Clustered Index Seek  : 10  (best — direct index lookup)
  Nested Loops                       : 8   (good for small row sets)
  Index Scan / Hash Match / Merge    : 7   (acceptable)
  Clustered Index Scan / Key Lookup  : 6   (watch on large tables)
  Sort                               : 5   (expensive without index)
  Table Scan                         : 2   (worst — reads entire table)

Starting from a score of 100, deductions are applied:
  Table Scan on table > 1000 est. rows : -30
  Table Scan on small table            : -10
  Sort on > 100 rows                   : -10
  Key Lookup / RID Lookup              : -5 each
  Missing index suggestion from MSSQL  : -15 each

A bonus of +5 is applied if all operations are index-efficient
(no scans, no sorts, no lookups).

The final numeric score is clamped to 0-100 and mapped to a label:
  90-100 : EXCELLENT
  75-89  : GOOD
  60-74  : ACCEPTABLE
  40-59  : POOR
  0-39   : CRITICAL

Threshold for table scan rejection
------------------------------------
Table scans are only flagged as hard rule failures when estimated rows
exceed ESTIMATED_ROWS_THRESHOLD (default 1000). On small demo tables
with < 100 rows, a table scan is acceptable. On the client's production
database with millions of rows, it would be caught and the query
rejected with instructions to use indexed columns.

Fail-open policy
----------------
If the execution plan cannot be retrieved (connection issue, driver
version incompatibility, MSSQL timeout), the check fails open —
the query is approved and the failure is logged. This prevents plan
retrieval issues from blocking valid queries in production.
"""

import logging
import xml.etree.ElementTree as ET
import pyodbc
from app.config import settings
from app.utils.db_connection import get_mssql_connection
from app.rag.schema_validator import validate_plan_against_schema


logger = logging.getLogger(__name__)

SHOWPLAN_NAMESPACE = "http://schemas.microsoft.com/sqlserver/2004/07/showplan"
ESTIMATED_ROWS_THRESHOLD = 1000

# Operation display names and their base scores
OPERATION_SCORES = {
    "Index Seek":      {"score": 10, "label": "EXCELLENT"},
    "Index Scan":      {"score": 7,  "label": "GOOD"},
    "Key Lookup":      {"score": 6,  "label": "ACCEPTABLE"},
    "Nested Loops":    {"score": 8,  "label": "GOOD"},
    "Hash Match":      {"score": 7,  "label": "GOOD"},
    "Merge Join":      {"score": 8,  "label": "GOOD"},
    "Sort":            {"score": 5,  "label": "WATCH"},
    "Table Scan":      {"score": 2,  "label": "POOR"},
    "Compute Scalar":  {"score": 9,  "label": "NORMAL"},
    "Stream Aggregate":{"score": 9,  "label": "NORMAL"},
    "Filter":          {"score": 7,  "label": "NORMAL"},
    "Top":             {"score": 9,  "label": "NORMAL"},
    "Clustered Index Seek":  {"score": 10, "label": "EXCELLENT"},
    "Clustered Index Scan":  {"score": 6,  "label": "ACCEPTABLE"},
    "RID Lookup":      {"score": 5,  "label": "WATCH"},
}

def get_execution_plan_xml(sql: str) -> str | None:
    try:
        with get_mssql_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SET SHOWPLAN_XML ON;")
            cursor.execute(sql)
            row = cursor.fetchone()
            plan_xml = row[0] if row else None
            print("\n\n")
            print(plan_xml)
            print("\n\n")
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
    - operations     : list of all physical operations with details
    - table_scans    : list of table names with full scans above threshold
    - missing_indexes: list of missing index suggestions from MSSQL
    - max_estimated_rows: highest estimated row count across all operations
    - statement_cost : estimated total query cost
    - has_warnings   : True if any actionable issue was found
    """
    result = {
        "operations": [],
        "table_scans": [],
        "missing_indexes": [],
        "max_estimated_rows": 0,
        "statement_cost": 0.0,
        "has_warnings": False,
    }

    try:
        ns = SHOWPLAN_NAMESPACE
        root = ET.fromstring(xml_string)

        # Extract statement cost
        for stmt in root.iter(f"{{{ns}}}StmtSimple"):
            cost = stmt.attrib.get("StatementSubTreeCost", "0")
            try:
                result["statement_cost"] = round(float(cost), 6)
            except ValueError:
                pass

        # Extract all physical operations
        seen_ops = {}
        for rel_op in root.iter(f"{{{ns}}}RelOp"):
            physical_op = rel_op.attrib.get("PhysicalOp", "")
            logical_op = rel_op.attrib.get("LogicalOp", "")
            estimated_rows = float(rel_op.attrib.get("EstimateRows", 0))
            estimated_cost = float(rel_op.attrib.get("EstimatedTotalSubtreeCost", 0))

            if estimated_rows > result["max_estimated_rows"]:
                result["max_estimated_rows"] = int(estimated_rows)

            # Get table name if present
            table_name = ""
            for obj in rel_op.iter(f"{{{ns}}}Object"):
                table_name = obj.attrib.get("Table", "").strip("[]")
                break

            if physical_op:
                op_entry = {
                    "physical_op": physical_op,
                    "logical_op": logical_op,
                    "table": table_name,
                    "estimated_rows": int(estimated_rows),
                    "estimated_cost": round(estimated_cost, 6),
                }

                # Track table scans above threshold
                if physical_op == "Table Scan" and estimated_rows > ESTIMATED_ROWS_THRESHOLD:
                    result["table_scans"].append({
                        "table": table_name,
                        "estimated_rows": int(estimated_rows),
                    })
                    result["has_warnings"] = True

                # Deduplicate operations by type+table
                key = f"{physical_op}_{table_name}"
                if key not in seen_ops:
                    seen_ops[key] = op_entry
                    result["operations"].append(op_entry)

        # Extract missing index warnings
        for missing in root.iter(f"{{{ns}}}MissingIndex"):
            table = missing.attrib.get("Table", "").strip("[]")
            schema = missing.attrib.get("Schema", "").strip("[]")
            columns = []
            for col_group in missing.iter(f"{{{ns}}}ColumnGroup"):
                usage = col_group.attrib.get("Usage", "")
                for col in col_group.iter(f"{{{ns}}}Column"):
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


def score_query_plan(analysis: dict) -> dict:
    """
    Scores the query plan from 0-100 based on operations used.

    Scoring:
    - Start at 100
    - Each operation contributes based on its efficiency
    - Deductions for table scans, missing indexes, high row estimates
    - Returns numeric score and text label
    """
    if not analysis["operations"]:
        return {"score": 50, "label": "UNKNOWN", "detail": "Could not evaluate plan"}

    score = 100
    deductions = []

    # Score based on operations
    op_scores = []
    for op in analysis["operations"]:
        physical_op = op["physical_op"]
        op_info = OPERATION_SCORES.get(physical_op, {"score": 5, "label": "UNKNOWN"})
        op_scores.append(op_info["score"])

        # Extra deduction for table scans
        if physical_op == "Table Scan":
            deduction = 30 if op["estimated_rows"] > ESTIMATED_ROWS_THRESHOLD else 10
            score -= deduction
            deductions.append(
                f"Table Scan on {op['table']} (-{deduction})"
            )

        # Deduction for sort without index
        if physical_op == "Sort" and op["estimated_rows"] > 100:
            score -= 10
            deductions.append(f"Sort on {op['estimated_rows']} rows (-10)")

        # Deduction for key lookup — means index is incomplete
        if physical_op in ("Key Lookup", "RID Lookup"):
            score -= 5
            deductions.append(f"Key Lookup on {op['table']} (-5)")

    # Deduction for missing indexes
    for missing in analysis["missing_indexes"]:
        score -= 15
        deductions.append(
            f"Missing index on {missing['table']} (-15)"
        )

    # Bonus if all ops are seeks
    all_seeks = all(
        op["physical_op"] in ("Index Seek", "Clustered Index Seek", "Compute Scalar",
                               "Stream Aggregate", "Top", "Filter", "Nested Loops",
                               "Hash Match", "Merge Join")
        for op in analysis["operations"]
    )
    if all_seeks:
        score = min(score + 5, 100)

    # Clamp to 0-100
    score = max(0, min(100, score))

    # Text label based on score
    if score >= 90:
        label = "EXCELLENT"
    elif score >= 75:
        label = "GOOD"
    elif score >= 60:
        label = "ACCEPTABLE"
    elif score >= 40:
        label = "POOR"
    else:
        label = "CRITICAL"

    return {
        "score": score,
        "label": label,
        "deductions": deductions,
    }


def check_query_plan(sql: str) -> dict:
    xml_string = get_execution_plan_xml(sql)

    if xml_string is None:
        return {
            "success": False,
            "has_warnings": False,
            "operations": [],
            "table_scans": [],
            "missing_indexes": [],
            "max_estimated_rows": 0,
            "statement_cost": 0.0,
            "score": None,
            "schema_validation": None,
            "error": "Could not retrieve execution plan.",
        }

    analysis = analyse_execution_plan(xml_string)
    scoring = score_query_plan(analysis)

    # Extract all table names from operations for Check A
    table_names = list({
        op["table"]
        for op in analysis["operations"]
        if op.get("table")
    })

    # Run schema validation — Check A and Check B
    try:
        schema_validation = validate_plan_against_schema(
            operations=analysis["operations"],
            table_names=table_names,
        )
    except Exception as e:
        logger.warning("Schema validation failed: %s", str(e))
        schema_validation = None

    analysis["success"] = True
    analysis["error"] = None
    analysis["score"] = scoring["score"]
    analysis["score_label"] = scoring["label"]
    analysis["score_deductions"] = scoring["deductions"]
    analysis["schema_validation"] = schema_validation

    return analysis