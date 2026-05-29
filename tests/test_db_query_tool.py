import pytest
from app.tools.db_query_tool import enforce_top_clause
from app.constants.app_constants import AppConfig


class TestEnforceTopClause:

    def test_injects_top_when_missing(self):
        sql = "SELECT product_name FROM products"
        result, changed = enforce_top_clause(sql)
        assert f"TOP {AppConfig.MAX_ROWS}" in result.upper()
        assert changed is True

    def test_leaves_top_unchanged_when_under_limit(self):
        sql = "SELECT TOP 5 product_name FROM products"
        result, changed = enforce_top_clause(sql)
        assert "TOP 5" in result
        assert changed is False

    def test_caps_top_when_exceeds_limit(self):
        sql = "SELECT TOP 100 product_name FROM products"
        result, changed = enforce_top_clause(sql)
        assert f"TOP {AppConfig.MAX_ROWS}" in result
        assert changed is True

    def test_leaves_top_at_exact_limit(self):
        sql = f"SELECT TOP {AppConfig.MAX_ROWS} product_name FROM products"
        result, changed = enforce_top_clause(sql)
        assert changed is False

    def test_handles_top_with_parentheses(self):
        sql = "SELECT TOP (5) product_name FROM products"
        result, changed = enforce_top_clause(sql)
        assert changed is False

    def test_handles_top_exceeding_with_parentheses(self):
        sql = "SELECT TOP (50) product_name FROM products"
        result, changed = enforce_top_clause(sql)
        assert f"TOP {AppConfig.MAX_ROWS}" in result
        assert changed is True

    def test_case_insensitive(self):
        sql = "select product_name from products"
        result, changed = enforce_top_clause(sql)
        assert changed is True
        assert str(AppConfig.MAX_ROWS) in result