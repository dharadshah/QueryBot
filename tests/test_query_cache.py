import pytest
import time
from unittest.mock import patch
from app.services.query_cache import (
    get_cached_query,
    set_cached_query,
    _extract_tables,
    _calculate_ttl,
    _cache,
)


@pytest.fixture(autouse=True)
def clear_cache():
    _cache.clear()
    yield
    _cache.clear()


class TestExtractTables:

    def test_extracts_single_table(self):
        tables = _extract_tables("SELECT TOP 20 * FROM products")
        assert "products" in tables

    def test_extracts_multiple_tables(self):
        tables = _extract_tables(
            "SELECT TOP 20 * FROM products p "
            "JOIN categories c ON p.category_id = c.category_id"
        )
        assert "products" in tables
        assert "categories" in tables

    def test_returns_empty_on_invalid_sql(self):
        tables = _extract_tables("NOT VALID SQL")
        assert tables == []


class TestCalculateTTL:

    def test_categories_products_get_long_ttl(self):
        sql = (
            "SELECT TOP 20 p.product_name FROM products p "
            "JOIN categories c ON p.category_id = c.category_id"
        )
        ttl = _calculate_ttl(sql)
        assert ttl == 3600

    def test_orders_get_short_ttl(self):
        sql = "SELECT TOP 20 * FROM orders WHERE status = 'pending'"
        ttl = _calculate_ttl(sql)
        assert ttl == 60

    def test_mixed_tables_use_shortest_ttl(self):
        sql = (
            "SELECT TOP 20 o.order_id FROM orders o "
            "JOIN products p ON o.order_id = p.product_id"
        )
        ttl = _calculate_ttl(sql)
        assert ttl == 60

    def test_query_audit_not_cached(self):
        sql = "SELECT TOP 20 * FROM query_audit"
        ttl = _calculate_ttl(sql)
        assert ttl == 0


class TestCacheSetGet:

    def test_cache_hit_returns_entry(self):
        sql = "SELECT TOP 20 * FROM products"
        set_cached_query("test question", "schema", sql)
        result = get_cached_query("test question", "schema")
        assert result is not None
        assert result.sql == sql

    def test_cache_miss_returns_none(self):
        result = get_cached_query("unknown question", "schema")
        assert result is None

    def test_cache_is_case_insensitive_on_question(self):
        sql = "SELECT TOP 20 * FROM products"
        set_cached_query("How Many Products?", "schema", sql)
        result = get_cached_query("how many products?", "schema")
        assert result is not None

    def test_query_audit_not_stored(self):
        sql = "SELECT TOP 20 * FROM query_audit"
        set_cached_query("audit question", "schema", sql)
        result = get_cached_query("audit question", "schema")
        assert result is None

    def test_expired_entry_returns_none(self):
        sql = "SELECT TOP 20 * FROM products"
        set_cached_query("test question", "schema", sql)
        entry = get_cached_query("test question", "schema")
        assert entry is not None

        # Manually expire the entry
        entry.ttl_seconds = 0
        result = get_cached_query("test question", "schema")
        assert result is None