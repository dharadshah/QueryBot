import pytest
from app.services.permission_filter import (
    check_question_permission,
    check_sql_permission,
    get_customer_context_instruction,
)
from app.schemas.user_context import UserContext
from app.constants.app_constants import UserRole


class TestQuestionPermission:

    def test_guest_blocked_on_orders_keyword(self):
        context = UserContext(role=UserRole.GUEST)
        allowed, reason = check_question_permission("show me all orders", context)
        assert allowed is False
        assert reason != ""

    def test_guest_blocked_on_purchase_keyword(self):
        context = UserContext(role=UserRole.GUEST)
        allowed, _ = check_question_permission("what are my purchases", context)
        assert allowed is False

    def test_guest_allowed_on_products(self):
        context = UserContext(role=UserRole.GUEST)
        allowed, _ = check_question_permission(
            "show me all products in electronics", context
        )
        assert allowed is True

    def test_customer_allowed_on_orders(self):
        context = UserContext(role=UserRole.CUSTOMER, customer_id=1)
        allowed, _ = check_question_permission("show me my orders", context)
        assert allowed is True

    def test_admin_allowed_on_everything(self):
        context = UserContext(role=UserRole.ADMIN)
        allowed, _ = check_question_permission("show me all orders", context)
        assert allowed is True


class TestSQLPermission:

    def test_guest_blocked_on_orders_table(self):
        context = UserContext(role=UserRole.GUEST)
        sql = (
            "SELECT TOP 20 o.order_id FROM orders o "
            "JOIN customers c ON o.customer_id = c.customer_id"
        )
        allowed, reason = check_sql_permission(sql, context)
        assert allowed is False
        assert reason != ""

    def test_guest_allowed_on_products_table(self):
        context = UserContext(role=UserRole.GUEST)
        sql = "SELECT TOP 20 p.product_name FROM products p"
        allowed, _ = check_sql_permission(sql, context)
        assert allowed is True

    def test_guest_allowed_on_products_and_categories(self):
        context = UserContext(role=UserRole.GUEST)
        sql = (
            "SELECT TOP 20 p.product_name, c.category_name "
            "FROM products p "
            "JOIN categories c ON p.category_id = c.category_id"
        )
        allowed, _ = check_sql_permission(sql, context)
        assert allowed is True

    def test_customer_allowed_on_orders(self):
        context = UserContext(role=UserRole.CUSTOMER, customer_id=2)
        sql = (
            "SELECT TOP 20 o.order_id FROM orders o "
            "WHERE o.customer_id = 2"
        )
        allowed, _ = check_sql_permission(sql, context)
        assert allowed is True

    def test_admin_allowed_on_all_tables(self):
        context = UserContext(role=UserRole.ADMIN)
        sql = (
            "SELECT TOP 20 o.order_id, c.first_name "
            "FROM orders o "
            "JOIN customers c ON o.customer_id = c.customer_id"
        )
        allowed, _ = check_sql_permission(sql, context)
        assert allowed is True


class TestCustomerContextInstruction:

    def test_returns_instruction_for_customer(self):
        context = UserContext(role=UserRole.CUSTOMER, customer_id=5)
        instruction = get_customer_context_instruction(context)
        assert "5" in instruction
        assert instruction != ""

    def test_returns_empty_for_guest(self):
        context = UserContext(role=UserRole.GUEST)
        instruction = get_customer_context_instruction(context)
        assert instruction == ""

    def test_returns_empty_for_admin(self):
        context = UserContext(role=UserRole.ADMIN)
        instruction = get_customer_context_instruction(context)
        assert instruction == ""

    def test_returns_empty_for_customer_without_id(self):
        context = UserContext(role=UserRole.CUSTOMER, customer_id=None)
        instruction = get_customer_context_instruction(context)
        assert instruction == ""