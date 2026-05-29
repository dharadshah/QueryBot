import pytest
from app.agents.query_validator import (
    _check_comment_injection,
    _check_semicolon_stacking,
    _check_syntax,
    _check_select_only,
    _check_disallowed_keywords,
    _check_dangerous_system_calls,
    _check_top_clause,
    _check_cartesian_join,
)
from app.constants.app_constants import ValidationResult, HardRuleCode


# ---------------------------------------------------------------------------
# Comment injection
# ---------------------------------------------------------------------------

class TestCommentInjection:
    def test_blocks_double_dash_comment(self):
        outcome = _check_comment_injection("SELECT TOP 20 * FROM products -- comment")
        assert outcome.verdict == ValidationResult.REJECTED
        assert outcome.rule_code == HardRuleCode.COMMENT_INJECTION

    def test_blocks_block_comment(self):
        outcome = _check_comment_injection("SELECT TOP 20 /* comment */ * FROM products")
        assert outcome.verdict == ValidationResult.REJECTED
        assert outcome.rule_code == HardRuleCode.COMMENT_INJECTION

    def test_allows_clean_query(self):
        outcome = _check_comment_injection("SELECT TOP 20 * FROM products")
        assert outcome.verdict == ValidationResult.APPROVED


# ---------------------------------------------------------------------------
# Semicolon stacking
# ---------------------------------------------------------------------------

class TestSemicolonStacking:
    def test_blocks_multiple_statements(self):
        outcome = _check_semicolon_stacking(
            "SELECT TOP 20 * FROM products; DROP TABLE products"
        )
        assert outcome.verdict == ValidationResult.REJECTED
        assert outcome.rule_code == HardRuleCode.SEMICOLON_STACKING

    def test_allows_trailing_semicolon(self):
        outcome = _check_semicolon_stacking("SELECT TOP 20 * FROM products;")
        assert outcome.verdict == ValidationResult.APPROVED

    def test_allows_no_semicolon(self):
        outcome = _check_semicolon_stacking("SELECT TOP 20 * FROM products")
        assert outcome.verdict == ValidationResult.APPROVED


# ---------------------------------------------------------------------------
# Syntax check
# ---------------------------------------------------------------------------

class TestSyntaxCheck:
    def test_approves_valid_sql(self):
        outcome = _check_syntax("SELECT TOP 20 * FROM products")
        assert outcome.verdict == ValidationResult.APPROVED

    def test_approves_valid_join(self):
        outcome = _check_syntax(
            "SELECT TOP 20 p.product_name FROM products p "
            "JOIN categories c ON p.category_id = c.category_id"
        )
        assert outcome.verdict == ValidationResult.APPROVED

    def test_blocks_garbage_input(self):
        outcome = _check_syntax("THIS IS NOT SQL AT ALL !!!!")
        assert outcome.verdict == ValidationResult.REJECTED
        assert outcome.rule_code == HardRuleCode.SYNTAX_ERROR


# ---------------------------------------------------------------------------
# SELECT only
# ---------------------------------------------------------------------------

class TestSelectOnly:
    def test_approves_select(self):
        outcome = _check_select_only("SELECT TOP 20 * FROM products")
        assert outcome.verdict == ValidationResult.APPROVED

    def test_blocks_insert(self):
        outcome = _check_select_only(
            "INSERT INTO products (product_name) VALUES ('test')"
        )
        assert outcome.verdict == ValidationResult.REJECTED
        assert outcome.rule_code == HardRuleCode.NOT_SELECT

    def test_blocks_update(self):
        outcome = _check_select_only(
            "UPDATE products SET unit_price = 0 WHERE product_id = 1"
        )
        assert outcome.verdict == ValidationResult.REJECTED
        assert outcome.rule_code == HardRuleCode.NOT_SELECT

    def test_blocks_delete(self):
        outcome = _check_select_only("DELETE FROM products WHERE product_id = 1")
        assert outcome.verdict == ValidationResult.REJECTED
        assert outcome.rule_code == HardRuleCode.NOT_SELECT


# ---------------------------------------------------------------------------
# Disallowed keywords
# ---------------------------------------------------------------------------

class TestDisallowedKeywords:
    def test_blocks_drop(self):
        outcome = _check_disallowed_keywords("DROP TABLE products")
        assert outcome.verdict == ValidationResult.REJECTED
        assert outcome.rule_code == HardRuleCode.DISALLOWED_KEYWORD

    def test_blocks_truncate(self):
        outcome = _check_disallowed_keywords("TRUNCATE TABLE products")
        assert outcome.verdict == ValidationResult.REJECTED
        assert outcome.rule_code == HardRuleCode.DISALLOWED_KEYWORD

    def test_blocks_exec(self):
        outcome = _check_disallowed_keywords("EXEC sp_helptext 'products'")
        assert outcome.verdict == ValidationResult.REJECTED
        assert outcome.rule_code == HardRuleCode.DISALLOWED_KEYWORD

    def test_allows_select_with_no_keywords(self):
        outcome = _check_disallowed_keywords(
            "SELECT TOP 20 p.product_name FROM products p"
        )
        assert outcome.verdict == ValidationResult.APPROVED


# ---------------------------------------------------------------------------
# Dangerous system calls
# ---------------------------------------------------------------------------

class TestDangerousSystemCalls:
    def test_blocks_xp_cmdshell(self):
        outcome = _check_dangerous_system_calls("EXEC xp_cmdshell 'dir'")
        assert outcome.verdict == ValidationResult.REJECTED
        assert outcome.rule_code == HardRuleCode.DANGEROUS_SYSTEM_CALL

    def test_blocks_openrowset(self):
        outcome = _check_dangerous_system_calls(
            "SELECT * FROM OPENROWSET('SQLNCLI', 'server=remote')"
        )
        assert outcome.verdict == ValidationResult.REJECTED
        assert outcome.rule_code == HardRuleCode.DANGEROUS_SYSTEM_CALL

    def test_allows_clean_query(self):
        outcome = _check_dangerous_system_calls(
            "SELECT TOP 20 * FROM products"
        )
        assert outcome.verdict == ValidationResult.APPROVED


# ---------------------------------------------------------------------------
# TOP clause
# ---------------------------------------------------------------------------

class TestTopClause:
    def test_approves_top_20(self):
        outcome = _check_top_clause("SELECT TOP 20 * FROM products")
        assert outcome.verdict == ValidationResult.APPROVED

    def test_approves_top_5(self):
        outcome = _check_top_clause("SELECT TOP 5 * FROM products")
        assert outcome.verdict == ValidationResult.APPROVED

    def test_approves_top_with_parens(self):
        outcome = _check_top_clause("SELECT TOP (10) * FROM products")
        assert outcome.verdict == ValidationResult.APPROVED

    def test_blocks_missing_top(self):
        outcome = _check_top_clause("SELECT * FROM products")
        assert outcome.verdict == ValidationResult.REJECTED
        assert outcome.rule_code == HardRuleCode.MISSING_TOP_CLAUSE

    def test_blocks_select_without_top(self):
        outcome = _check_top_clause(
            "SELECT product_name FROM products WHERE is_active = 1"
        )
        assert outcome.verdict == ValidationResult.REJECTED


# ---------------------------------------------------------------------------
# Cartesian join
# ---------------------------------------------------------------------------

class TestCartesianJoin:
    def test_blocks_implicit_comma_join(self):
        outcome = _check_cartesian_join(
            "SELECT TOP 20 * FROM products, categories"
        )
        assert outcome.verdict == ValidationResult.REJECTED
        assert outcome.rule_code == HardRuleCode.CARTESIAN_JOIN

    def test_allows_explicit_join(self):
        outcome = _check_cartesian_join(
            "SELECT TOP 20 p.product_name FROM products p "
            "JOIN categories c ON p.category_id = c.category_id"
        )
        assert outcome.verdict == ValidationResult.APPROVED

    def test_allows_single_table(self):
        outcome = _check_cartesian_join("SELECT TOP 20 * FROM products")
        assert outcome.verdict == ValidationResult.APPROVED