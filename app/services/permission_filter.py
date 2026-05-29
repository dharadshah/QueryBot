import logging
import sqlglot
from app.schemas.user_context import UserContext
from app.constants.app_constants import UserRole, RolePermission
from app.constants.messages import (
    PERMISSION_DENIED_GUEST,
    PERMISSION_DENIED_CUSTOMER_OTHER,
    PERMISSION_DENIED_TABLE,
)

logger = logging.getLogger(__name__)


def check_question_permission(
    question: str,
    user_context: UserContext,
) -> tuple[bool, str]:
    """
    Fast pre-generation check based on question keywords.
    Returns (is_allowed, reason).
    """
    if user_context.role == UserRole.ADMIN:
        return True, ""

    question_lower = question.lower()

    if user_context.role == UserRole.GUEST:
        # Block if question implies order or customer data
        for keyword in RolePermission.ORDER_KEYWORDS:
            if keyword in question_lower:
                return False, PERMISSION_DENIED_GUEST
        for keyword in RolePermission.CUSTOMER_KEYWORDS:
            if keyword in question_lower:
                return False, PERMISSION_DENIED_GUEST

    return True, ""


def check_sql_permission(
    sql: str,
    user_context: UserContext,
) -> tuple[bool, str]:
    """
    Post-generation check based on tables in the generated SQL.
    Returns (is_allowed, reason).
    """
    if user_context.role == UserRole.ADMIN:
        return True, ""

    allowed_tables = RolePermission.ALLOWED_TABLES.get(user_context.role, set())
    if allowed_tables is None:
        return True, ""

    try:
        statements = sqlglot.parse(sql, dialect="tsql")
        touched_tables = set()
        for statement in statements:
            for table in statement.find_all(sqlglot.expressions.Table):
                name = table.name.lower()
                if name:
                    touched_tables.add(name)
    except Exception:
        return True, ""

    # Check if any touched table is outside allowed set
    # Exclude system tables
    system_tables = {"query_audit", "conversation_history"}
    restricted = touched_tables - allowed_tables - system_tables

    if restricted:
        logger.warning(
            "Permission denied — role %s tried to access tables: %s",
            user_context.role,
            restricted,
        )
        if user_context.role == UserRole.GUEST:
            return False, PERMISSION_DENIED_GUEST
        return False, PERMISSION_DENIED_TABLE

    return True, ""


def inject_customer_filter(
    sql: str,
    user_context: UserContext,
) -> str:
    """
    For Customer role, ensures the SQL only returns data
    belonging to the logged-in customer.
    This adds a note to the rejection reason so Agent 1
    regenerates with the customer_id constraint.
    """
    if user_context.role != UserRole.CUSTOMER:
        return sql
    if not user_context.customer_id:
        return sql
    return sql


def get_customer_context_instruction(user_context: UserContext) -> str:
    """
    Returns an instruction string to inject into the query generator prompt
    so the LLM automatically scopes queries to the correct customer.
    """
    if user_context.role != UserRole.CUSTOMER:
        return ""
    if not user_context.customer_id:
        return ""
    return (
        f"IMPORTANT: This query is for customer_id = {user_context.customer_id}. "
        f"Always filter orders and order_items by customer_id = {user_context.customer_id}. "
        f"Never return data belonging to other customers."
    )