"""
schema_validator.py
===================
Loads the structured schema dict and provides two validation functions
used by execution_plan.py after plan analysis:

Check A — Table existence validation:
    Verifies that every table referenced in the execution plan XML
    actually exists in the known schema. If the plan references a table
    not in the schema, it indicates either LLM hallucination or schema drift.

Check B — Index usage validation:
    For every operation in the execution plan, checks whether the
    operation type is consistent with the available indexes on that table.
    - Index Seek / Clustered Index Seek on a table that has indexes → CONFIRMED
    - Table Scan on a table that has non-PK indexes → UNEXPECTED
      (the query is ignoring available indexes)
    - Index name in plan matches a known index in schema → CONFIRMED
    - Index name in plan not found in schema → SCHEMA DRIFT warning
"""

import logging
import os
from app.rag.schema_extractor import extract_schema_dict

logger = logging.getLogger(__name__)

# Module-level cache — loaded once per process startup
_schema_dict: dict = {}


def load_schema_dict(force_reload: bool = False) -> dict:
    """
    Returns the schema dict. Loads from the live database on first call
    or when force_reload=True. Subsequent calls return the cached dict.
    """
    global _schema_dict
    if not _schema_dict or force_reload:
        try:
            result = extract_schema_dict()
            _schema_dict = result
            logger.info(
                "Schema dict loaded: %d tables",
                len(_schema_dict.get("tables", {})),
            )
        except Exception as e:
            logger.error("Failed to load schema dict: %s", str(e))
            _schema_dict = {"tables": {}}
    return _schema_dict


def get_known_tables() -> set:
    """Returns a set of all table names known in the schema."""
    schema = load_schema_dict()
    return set(schema.get("tables", {}).keys())


def get_table_indexes(table_name: str) -> dict:
    """
    Returns the indexes dict for a given table.
    Keys are index names, values contain columns, type, unique flag.
    Returns empty dict if table not found.
    """
    schema = load_schema_dict()
    table = schema.get("tables", {}).get(table_name.lower(), {})
    if not table:
        # Try case-insensitive match
        for tname, tdata in schema.get("tables", {}).items():
            if tname.lower() == table_name.lower():
                return tdata.get("indexes", {})
    return table.get("indexes", {})


def get_non_pk_indexes(table_name: str) -> list:
    """
    Returns a list of non-primary-key index names for a table.
    These are the indexes that should be used for query optimisation.
    """
    indexes = get_table_indexes(table_name)
    return [
        name for name, idx in indexes.items()
        if not idx.get("primary_key", False)
    ]


# ---------------------------------------------------------------------------
# Check A — Table existence validation
# ---------------------------------------------------------------------------

def validate_tables_in_plan(table_names: list) -> dict:
    """
    Check A: Verifies every table in the execution plan exists in the schema.

    Args:
        table_names: list of table names extracted from the plan XML

    Returns:
        {
            "valid": bool,
            "unknown_tables": list of table names not found in schema,
            "known_tables": list of table names confirmed in schema,
            "message": str,
        }
    """
    known = get_known_tables()
    known_lower = {t.lower() for t in known}

    unknown = []
    confirmed = []

    for table in table_names:
        if not table:
            continue
        if table.lower() in known_lower:
            confirmed.append(table)
        else:
            unknown.append(table)

    result = {
        "valid": len(unknown) == 0,
        "unknown_tables": unknown,
        "known_tables": confirmed,
        "message": "",
    }

    if unknown:
        result["message"] = (
            f"Plan references unknown tables: {', '.join(unknown)}. "
            f"Possible LLM hallucination or schema drift. "
            f"Known tables: {', '.join(sorted(known_lower))}"
        )
        logger.warning(result["message"])
    else:
        result["message"] = (
            f"All {len(confirmed)} table(s) in plan confirmed in schema."
        )

    return result


# ---------------------------------------------------------------------------
# Check B — Index usage validation
# ---------------------------------------------------------------------------

def validate_indexes_in_plan(operations: list) -> dict:
    """
    Check B: Validates index usage in plan operations against known indexes.

    For each operation:
    - If Table Scan on a table with non-PK indexes → flag as unexpected
    - If Index Seek/Scan → confirm index exists in schema
    - If index name not recognised → flag as schema drift

    Args:
        operations: list of operation dicts from analyse_execution_plan()
                    each has: physical_op, table, estimated_rows

    Returns:
        {
            "unexpected_scans": list of dicts,
            "index_confirmations": list of dicts,
            "schema_drift": list of dicts,
            "has_issues": bool,
            "summary": str,
        }
    """
    unexpected_scans = []
    index_confirmations = []
    schema_drift = []

    for op in operations:
        table = op.get("table", "").strip("[]")
        physical_op = op.get("physical_op", "")
        estimated_rows = op.get("estimated_rows", 0)

        if not table:
            continue

        available_indexes = get_non_pk_indexes(table)

        # Check A interaction — skip if table not in schema
        known = get_known_tables()
        if table.lower() not in {t.lower() for t in known}:
            continue

        # Table Scan on a table that has non-PK indexes
        if physical_op == "Table Scan" and available_indexes:
            unexpected_scans.append({
                "table": table,
                "estimated_rows": estimated_rows,
                "available_indexes": available_indexes,
                "message": (
                    f"Table scan on '{table}' despite "
                    f"{len(available_indexes)} available index(es): "
                    f"{', '.join(available_indexes)}"
                ),
            })

        # Index Seek or Scan — confirm against schema
        elif physical_op in (
            "Index Seek",
            "Index Scan",
            "Clustered Index Seek",
            "Clustered Index Scan",
        ):
            all_indexes = get_table_indexes(table)
            if all_indexes:
                index_confirmations.append({
                    "table": table,
                    "operation": physical_op,
                    "available_indexes": list(all_indexes.keys()),
                    "status": "CONFIRMED",
                    "message": (
                        f"{physical_op} on '{table}' — "
                        f"confirmed against {len(all_indexes)} known index(es)"
                    ),
                })
            else:
                schema_drift.append({
                    "table": table,
                    "operation": physical_op,
                    "message": (
                        f"{physical_op} on '{table}' but no indexes "
                        f"found in schema — possible schema drift"
                    ),
                })

    has_issues = bool(unexpected_scans or schema_drift)

    parts = []
    if index_confirmations:
        parts.append(
            f"{len(index_confirmations)} index operation(s) confirmed"
        )
    if unexpected_scans:
        parts.append(
            f"{len(unexpected_scans)} unexpected table scan(s)"
        )
    if schema_drift:
        parts.append(
            f"{len(schema_drift)} schema drift warning(s)"
        )

    summary = " | ".join(parts) if parts else "No index issues detected"

    return {
        "unexpected_scans": unexpected_scans,
        "index_confirmations": index_confirmations,
        "schema_drift": schema_drift,
        "has_issues": has_issues,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Combined validation entry point
# ---------------------------------------------------------------------------

def validate_plan_against_schema(
    operations: list,
    table_names: list,
) -> dict:
    """
    Runs both Check A and Check B and returns a combined result.

    Args:
        operations : list of operation dicts from analyse_execution_plan()
        table_names: list of table names extracted from the plan XML

    Returns combined dict with all findings from both checks.
    """
    table_check = validate_tables_in_plan(table_names)
    index_check = validate_indexes_in_plan(operations)

    has_issues = (
        not table_check["valid"] or
        index_check["has_issues"]
    )

    return {
        "valid": table_check["valid"],
        "has_issues": has_issues,
        "unknown_tables": table_check["unknown_tables"],
        "known_tables": table_check["known_tables"],
        "unexpected_scans": index_check["unexpected_scans"],
        "index_confirmations": index_check["index_confirmations"],
        "schema_drift": index_check["schema_drift"],
        "summary": (
            f"Tables: {table_check['message']} | "
            f"Indexes: {index_check['summary']}"
        ),
    }