import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from app.schemas.user_context import UserContext
from app.constants.app_constants import UserRole


@pytest.fixture
def guest_context():
    return UserContext(role=UserRole.GUEST)


@pytest.fixture
def customer_context():
    return UserContext(role=UserRole.CUSTOMER, customer_id=2)


@pytest.fixture
def admin_context():
    return UserContext(role=UserRole.ADMIN)


@pytest.fixture
def valid_select_sql():
    return "SELECT TOP 20 p.product_name, p.unit_price FROM products p"


@pytest.fixture
def valid_join_sql():
    return (
        "SELECT TOP 20 p.product_name, c.category_name "
        "FROM products p "
        "JOIN categories c ON p.category_id = c.category_id"
    )


@pytest.fixture
def valid_count_sql():
    return (
        "SELECT TOP 20 COUNT(p.product_id) AS total "
        "FROM products p "
        "JOIN categories c ON p.category_id = c.category_id "
        "WHERE c.category_name = 'Electronics'"
    )