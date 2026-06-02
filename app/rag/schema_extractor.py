
"""
schema_extractor.py
===================
Extracts the live database schema from MSSQL system tables and generates
a versioned markdown file for human review before ChromaDB embedding.

System tables used:
  sys.tables          - all user tables
  sys.columns         - column definitions per table
  sys.indexes         - index definitions per table
  sys.index_columns   - columns belonging to each index
  sys.foreign_keys    - foreign key relationships
  sys.key_constraints - primary key definitions
  INFORMATION_SCHEMA.TABLE_CONSTRAINTS + CONSTRAINT_COLUMN_USAGE
                      - constraint metadata

Versioning:
  On each run the extractor compares the newly generated schema with the
  current ecommerce_schema.md. If they differ, the old version is archived
  to schema_versions/ with a timestamp suffix and the new file is written.
  ChromaDB is NOT automatically re-embedded — a human must review the new
  file and manually trigger re-embedding via:
    poetry run python -m app.rag.embedder --force-reembed
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import hashlib
import logging
import os
import shutil
from datetime import datetime
from app.utils.db_connection import get_mssql_connection

logger = logging.getLogger(__name__)

SCHEMA_FILE_PATH = os.path.join(
    os.path.dirname(__file__),
    "schema_definitions",
    "ecommerce_schema.md",
)

VERSIONS_DIR = os.path.join(
    os.path.dirname(__file__),
    "schema_versions",
)

SCHEMA_DICT_PATH = os.path.join(
    os.path.dirname(__file__),
    "schema_definitions",
    "schema_dict.py",
)


# ---------------------------------------------------------------------------
# System table queries
# ---------------------------------------------------------------------------

_QUERY_TABLES = """
SELECT
    t.name          AS table_name,
    t.object_id     AS object_id
FROM sys.tables t
WHERE t.is_ms_shipped = 0
ORDER BY t.name
"""

_QUERY_COLUMNS = """
SELECT
    t.name                          AS table_name,
    c.name                          AS column_name,
    tp.name                         AS data_type,
    c.max_length                    AS max_length,
    c.precision                     AS precision,
    c.scale                         AS scale,
    c.is_nullable                   AS is_nullable,
    c.is_identity                   AS is_identity,
    OBJECT_DEFINITION(c.default_object_id) AS default_value
FROM sys.tables t
JOIN sys.columns c ON t.object_id = c.object_id
JOIN sys.types tp ON c.user_type_id = tp.user_type_id
WHERE t.is_ms_shipped = 0
ORDER BY t.name, c.column_id
"""

_QUERY_INDEXES = """
SELECT
    t.name          AS table_name,
    i.name          AS index_name,
    i.type_desc     AS index_type,
    i.is_unique     AS is_unique,
    i.is_primary_key AS is_primary_key
FROM sys.indexes i
JOIN sys.tables t ON i.object_id = t.object_id
WHERE t.is_ms_shipped = 0
  AND i.name IS NOT NULL
ORDER BY t.name, i.name
"""

_QUERY_INDEX_COLUMNS = """
SELECT
    t.name          AS table_name,
    i.name          AS index_name,
    c.name          AS column_name,
    ic.key_ordinal  AS key_ordinal,
    ic.is_included_column AS is_included
FROM sys.index_columns ic
JOIN sys.indexes i ON ic.object_id = i.object_id
    AND ic.index_id = i.index_id
JOIN sys.tables t ON i.object_id = t.object_id
JOIN sys.columns c ON ic.object_id = c.object_id
    AND ic.column_id = c.column_id
WHERE t.is_ms_shipped = 0
  AND i.name IS NOT NULL
ORDER BY t.name, i.name, ic.key_ordinal
"""

_QUERY_FOREIGN_KEYS = """
SELECT
    fk.name                         AS fk_name,
    tp.name                         AS parent_table,
    cp.name                         AS parent_column,
    tr.name                         AS referenced_table,
    cr.name                         AS referenced_column
FROM sys.foreign_keys fk
JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
JOIN sys.tables tp ON fkc.parent_object_id = tp.object_id
JOIN sys.columns cp ON fkc.parent_object_id = cp.object_id
    AND fkc.parent_column_id = cp.column_id
JOIN sys.tables tr ON fkc.referenced_object_id = tr.object_id
JOIN sys.columns cr ON fkc.referenced_object_id = cr.object_id
    AND fkc.referenced_column_id = cr.column_id
ORDER BY tp.name, fk.name
"""

_QUERY_PRIMARY_KEYS = """
SELECT
    t.name          AS table_name,
    c.name          AS column_name
FROM sys.key_constraints kc
JOIN sys.tables t ON kc.parent_object_id = t.object_id
JOIN sys.index_columns ic ON kc.parent_object_id = ic.object_id
    AND kc.unique_index_id = ic.index_id
JOIN sys.columns c ON ic.object_id = c.object_id
    AND ic.column_id = c.column_id
WHERE kc.type = 'PK'
  AND t.is_ms_shipped = 0
ORDER BY t.name
"""


# ---------------------------------------------------------------------------
# Schema extraction
# ---------------------------------------------------------------------------

def extract_schema_dict() -> dict:
    """
    Connects to the live MSSQL database and extracts the full schema
    as a structured Python dict.

    Returns:
        dict with structure:
        {
            "tables": {
                "table_name": {
                    "columns": {
                        "col_name": {
                            "type": str,
                            "max_length": int,
                            "nullable": bool,
                            "is_identity": bool,
                            "is_pk": bool,
                            "default": str or None,
                        }
                    },
                    "indexes": {
                        "index_name": {
                            "type": str,
                            "unique": bool,
                            "primary_key": bool,
                            "columns": [str],
                            "included_columns": [str],
                        }
                    },
                    "foreign_keys": {
                        "fk_name": {
                            "column": str,
                            "references_table": str,
                            "references_column": str,
                        }
                    },
                    "primary_keys": [str],
                }
            },
            "extracted_at": str (ISO timestamp),
            "database": str,
        }
    """
    conn = get_mssql_connection()
    cursor = conn.cursor()

    schema = {
        "tables": {},
        "extracted_at": datetime.utcnow().isoformat(),
        "database": "",
    }

    # Get database name
    cursor.execute("SELECT DB_NAME()")
    row = cursor.fetchone()
    schema["database"] = row[0] if row else "unknown"

    # Extract tables
    cursor.execute(_QUERY_TABLES)
    for row in cursor.fetchall():
        schema["tables"][row.table_name] = {
            "columns": {},
            "indexes": {},
            "foreign_keys": {},
            "primary_keys": [],
        }

    # Extract columns
    cursor.execute(_QUERY_COLUMNS)
    for row in cursor.fetchall():
        if row.table_name not in schema["tables"]:
            continue
        col_type = row.data_type
        if row.max_length and row.max_length > 0 and col_type in ("varchar", "nvarchar", "char", "nchar"):
            display_length = row.max_length // 2 if col_type.startswith("n") else row.max_length
            if display_length == -1:
                col_type = f"{col_type}(max)"
            else:
                col_type = f"{col_type}({display_length})"
        elif col_type in ("decimal", "numeric") and row.precision:
            col_type = f"{col_type}({row.precision},{row.scale})"

        schema["tables"][row.table_name]["columns"][row.column_name] = {
            "type": col_type,
            "nullable": bool(row.is_nullable),
            "is_identity": bool(row.is_identity),
            "is_pk": False,
            "default": row.default_value,
        }

    # Extract primary keys and mark columns
    cursor.execute(_QUERY_PRIMARY_KEYS)
    for row in cursor.fetchall():
        if row.table_name not in schema["tables"]:
            continue
        schema["tables"][row.table_name]["primary_keys"].append(row.column_name)
        if row.column_name in schema["tables"][row.table_name]["columns"]:
            schema["tables"][row.table_name]["columns"][row.column_name]["is_pk"] = True

    # Extract indexes
    cursor.execute(_QUERY_INDEXES)
    for row in cursor.fetchall():
        if row.table_name not in schema["tables"]:
            continue
        schema["tables"][row.table_name]["indexes"][row.index_name] = {
            "type": row.index_type,
            "unique": bool(row.is_unique),
            "primary_key": bool(row.is_primary_key),
            "columns": [],
            "included_columns": [],
        }

    # Extract index columns
    cursor.execute(_QUERY_INDEX_COLUMNS)
    for row in cursor.fetchall():
        if row.table_name not in schema["tables"]:
            continue
        if row.index_name not in schema["tables"][row.table_name]["indexes"]:
            continue
        idx = schema["tables"][row.table_name]["indexes"][row.index_name]
        if row.is_included:
            idx["included_columns"].append(row.column_name)
        else:
            idx["columns"].append(row.column_name)

    # Extract foreign keys
    cursor.execute(_QUERY_FOREIGN_KEYS)
    for row in cursor.fetchall():
        if row.parent_table not in schema["tables"]:
            continue
        schema["tables"][row.parent_table]["foreign_keys"][row.fk_name] = {
            "column": row.parent_column,
            "references_table": row.referenced_table,
            "references_column": row.referenced_column,
        }

    cursor.close()
    conn.close()

    logger.info(
        "Schema extracted: %d tables from database %s",
        len(schema["tables"]),
        schema["database"],
    )
    return schema


# ---------------------------------------------------------------------------
# Markdown generation
# ---------------------------------------------------------------------------

def _format_column(name: str, col: dict) -> str:
    parts = [f"- {name} ({col['type'].upper()}"]
    if col["is_pk"]:
        parts[0] += ", PRIMARY KEY"
    if col["is_identity"]:
        parts[0] += ", AUTOINCREMENT"
    if not col["nullable"]:
        parts[0] += ", NOT NULL"
    else:
        parts[0] += ", NULLABLE"
    if col["default"]:
        default = col["default"].strip("()")
        parts[0] += f", DEFAULT {default}"
    parts[0] += ")"
    return parts[0]

# Markers for the two sections
AUTO_START = "<!-- AUTO-GENERATED SECTION — DO NOT EDIT MANUALLY -->"
AUTO_END   = "<!-- END AUTO-GENERATED SECTION -->"
HUMAN_START = "<!-- HUMAN ANNOTATIONS — SAFE TO EDIT -->"
HUMAN_END   = "<!-- END HUMAN ANNOTATIONS -->"

DEFAULT_HUMAN_ANNOTATIONS = """<!-- HUMAN ANNOTATIONS — SAFE TO EDIT -->
<!-- This section is never overwritten by the extractor -->
<!-- Add business context, column value examples, join patterns, notes here -->

## Business Context

### General Notes
- Add any business-specific notes about the data here
- Describe what each table is used for in your business context

### Column Value Reference

#### orders.status
Possible values: pending, confirmed, shipped, delivered, cancelled

#### products.is_active
1 = product is available for sale, 0 = product is discontinued

### Common Query Patterns
- To find all orders for a customer: JOIN orders o ON o.customer_id = cu.customer_id
- To find products in a category: JOIN categories c ON p.category_id = c.category_id
- To find order line items: JOIN order_items oi ON oi.order_id = o.order_id

<!-- END HUMAN ANNOTATIONS -->"""


def generate_markdown(schema: dict) -> str:
    """Generates only the auto-generated section content."""
    lines = []
    lines.append(AUTO_START)
    lines.append(f"<!-- Last extracted: {schema['extracted_at']} -->")
    lines.append(
        "<!-- Changes to this section will be overwritten on next startup -->"
    )
    lines.append(f"")
    lines.append(f"# eCommerce Database Schema")
    lines.append(f"")
    lines.append(f"## Database: {schema['database']}")
    lines.append(f"## Dialect: Microsoft SQL Server (T-SQL)")
    lines.append(f"## Extracted at: {schema['extracted_at']}")
    lines.append(f"")

    for table_name, table in sorted(schema["tables"].items()):
        lines.append(f"---")
        lines.append(f"")
        lines.append(f"## Table: {table_name}")
        lines.append(f"")

        lines.append(f"Columns:")
        for col_name, col in table["columns"].items():
            lines.append(_format_column(col_name, col))
        lines.append(f"")

        if table["primary_keys"]:
            lines.append(
                f"Primary Key: {', '.join(table['primary_keys'])}"
            )
            lines.append(f"")

        if table["indexes"]:
            lines.append(f"Indexes:")
            for idx_name, idx in table["indexes"].items():
                cols = ", ".join(idx["columns"])
                flags = []
                if idx["unique"]:
                    flags.append("UNIQUE")
                if idx["primary_key"]:
                    flags.append("PRIMARY KEY")
                flag_str = f" ({', '.join(flags)})" if flags else ""
                lines.append(f"- {idx_name} on ({cols}){flag_str}")
                if idx["included_columns"]:
                    lines.append(
                        f"  INCLUDE: {', '.join(idx['included_columns'])}"
                    )
            lines.append(f"")

        if table["foreign_keys"]:
            lines.append(f"Foreign Keys:")
            for fk_name, fk in table["foreign_keys"].items():
                lines.append(
                    f"- {fk_name}: {fk['column']} -> "
                    f"{fk['references_table']}.{fk['references_column']}"
                )
            lines.append(f"")

    lines.append(AUTO_END)
    return "\n".join(lines)


def _extract_auto_section(content: str) -> str:
    """Extracts only the auto-generated section from a file."""
    start = content.find(AUTO_START)
    end = content.find(AUTO_END)
    if start == -1 or end == -1:
        return content
    return content[start:end + len(AUTO_END)]


def _extract_human_section(content: str) -> str:
    """Extracts the human annotations section from a file."""
    start = content.find(HUMAN_START)
    end = content.find(HUMAN_END)
    if start == -1 or end == -1:
        return DEFAULT_HUMAN_ANNOTATIONS
    return content[start:end + len(HUMAN_END)]


def _combine_sections(auto_section: str, human_section: str) -> str:
    """Combines auto and human sections into the final file."""
    return (
        auto_section
        + "\n\n---\n\n"
        + human_section
        + "\n"
    )


# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------

def _file_hash(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return hashlib.md5(f.read().encode()).hexdigest()


def _archive_current_schema() -> str:
    if not os.path.exists(SCHEMA_FILE_PATH):
        return ""
    os.makedirs(VERSIONS_DIR, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y_%m_%d_%H%M%S")
    archive_path = os.path.join(
        VERSIONS_DIR,
        f"ecommerce_schema_{timestamp}.md",
    )
    shutil.copy2(SCHEMA_FILE_PATH, archive_path)
    logger.info("Archived current schema to: %s", archive_path)
    return archive_path


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_extraction() -> dict:
    """
    Full extraction pipeline:
    1. Extract schema from live database
    2. Generate auto section markdown
    3. Compare auto section only with current file (ignores human edits)
    4. If changed: archive old version, write new auto section + preserve human section
    5. Return status dict
    """
    logger.info("Starting schema extraction from live database")

    schema_dict = extract_schema_dict()
    new_auto_section = generate_markdown(schema_dict)

    # Read existing file
    existing_content = ""
    if os.path.exists(SCHEMA_FILE_PATH):
        with open(SCHEMA_FILE_PATH, "r", encoding="utf-8") as f:
            existing_content = f.read()

    # Compare only the auto-generated section
    existing_auto = _extract_auto_section(existing_content)
    existing_human = _extract_human_section(existing_content)

    # Strip timestamps from comparison to avoid false positives
    def _strip_timestamp(text: str) -> str:
        import re
        # Strip the comment timestamp
        text = re.sub(
            r"<!-- Last extracted: .*? -->",
            "<!-- Last extracted: TIMESTAMP -->",
            text,
        )
        # Strip the body timestamp
        text = re.sub(
            r"## Extracted at: .*",
            "## Extracted at: TIMESTAMP",
            text,
        )
        return text

    existing_auto_clean = _strip_timestamp(existing_auto)
    new_auto_clean = _strip_timestamp(new_auto_section)

    existing_hash = hashlib.md5(existing_auto_clean.encode()).hexdigest()
    new_hash = hashlib.md5(new_auto_clean.encode()).hexdigest()

    if existing_hash == new_hash:
        logger.info(
            "Schema unchanged — no update needed. Tables: %d",
            len(schema_dict["tables"]),
        )
        return {
            "changed": False,
            "table_count": len(schema_dict["tables"]),
            "archive_path": None,
            "message": "Schema is unchanged. ChromaDB re-embedding not required.",
            "schema_dict": schema_dict,
        }

    # Schema has changed — archive old and write new
    archive_path = _archive_current_schema()

    # Combine new auto section with preserved human section
    final_content = _combine_sections(new_auto_section, existing_human)

    with open(SCHEMA_FILE_PATH, "w", encoding="utf-8") as f:
        f.write(final_content)

    logger.warning(
        "Schema has changed. New file written to %s. "
        "Human annotations preserved. "
        "Please review before re-embedding ChromaDB.",
        SCHEMA_FILE_PATH,
    )

    return {
        "changed": True,
        "table_count": len(schema_dict["tables"]),
        "archive_path": archive_path,
        "message": (
            f"Schema has changed. New file written to ecommerce_schema.md. "
            f"Human annotations preserved. "
            f"Old version archived to {archive_path}. "
            f"Review the new file and run: "
            f"poetry run python -m app.rag.embedder --force-reembed"
        ),
        "schema_dict": schema_dict,
    }


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )))
    from app.observability.logger import setup_logging
    setup_logging("INFO")

    result = run_extraction()
    print(f"\nTable count : {result['table_count']}")
    print(f"Changed     : {result['changed']}")
    print(f"Message     : {result['message']}")