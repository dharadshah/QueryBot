import pytest
from app.services.chat_service import _detect_write_intent


class TestWriteIntentDetection:

    def test_detects_add(self):
        assert _detect_write_intent("add a new product") is True

    def test_detects_insert(self):
        assert _detect_write_intent("insert customer details") is True

    def test_detects_update(self):
        assert _detect_write_intent("update the order status") is True

    def test_detects_delete(self):
        assert _detect_write_intent("delete all pending orders") is True

    def test_detects_remove(self):
        assert _detect_write_intent("remove this product") is True

    def test_detects_create(self):
        assert _detect_write_intent("create a new category") is True

    def test_allows_show(self):
        assert _detect_write_intent("show me all products") is False

    def test_allows_list(self):
        assert _detect_write_intent("list all pending orders") is False

    def test_allows_how_many(self):
        assert _detect_write_intent("how many products are in electronics") is False

    def test_allows_what(self):
        assert _detect_write_intent("what are the total sales") is False

    def test_allows_which(self):
        assert _detect_write_intent("which product has the highest price") is False

    def test_handles_empty_string(self):
        assert _detect_write_intent("") is False

    def test_handles_mixed_case(self):
        assert _detect_write_intent("ADD a new product") is True

    def test_handles_leading_spaces(self):
        assert _detect_write_intent("  delete all orders") is True