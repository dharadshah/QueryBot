import pyodbc
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings

def get_connection_string() -> str:
    if settings.mssql_use_windows_auth:
        return (
            f"DRIVER={{{settings.mssql_driver}}};"
            f"SERVER={settings.mssql_server};"
            f"DATABASE={settings.mssql_database};"
            f"Trusted_Connection=yes;"
            f"TrustServerCertificate=yes;"
        )
    return (
        f"DRIVER={{{settings.mssql_driver}}};"
        f"SERVER={settings.mssql_server};"
        f"DATABASE={settings.mssql_database};"
        f"UID={settings.mssql_username};"
        f"PWD={settings.mssql_password};"
        f"TrustServerCertificate=yes;"
    )

def get_connection():
    return pyodbc.connect(get_connection_string())


def create_tables(cursor):
    cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='categories' AND xtype='U')
        CREATE TABLE categories (
            category_id   INT PRIMARY KEY IDENTITY(1,1),
            category_name VARCHAR(100) NOT NULL UNIQUE,
            description   TEXT,
            is_active     BIT NOT NULL DEFAULT 1
        )
    """)

    cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='products' AND xtype='U')
        CREATE TABLE products (
            product_id     INT PRIMARY KEY IDENTITY(1,1),
            category_id    INT NOT NULL REFERENCES categories(category_id),
            product_name   VARCHAR(255) NOT NULL,
            description    TEXT,
            unit_price     DECIMAL(10,2) NOT NULL,
            stock_quantity INT NOT NULL DEFAULT 0,
            sku            VARCHAR(100) NOT NULL UNIQUE,
            is_active      BIT NOT NULL DEFAULT 1,
            created_at     DATETIME NOT NULL DEFAULT GETDATE()
        )
    """)

    cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='customers' AND xtype='U')
        CREATE TABLE customers (
            customer_id INT PRIMARY KEY IDENTITY(1,1),
            first_name  VARCHAR(100) NOT NULL,
            last_name   VARCHAR(100) NOT NULL,
            email       VARCHAR(255) NOT NULL UNIQUE,
            phone       VARCHAR(20),
            city        VARCHAR(100),
            state       VARCHAR(100),
            country     VARCHAR(100),
            postal_code VARCHAR(20),
            created_at  DATETIME NOT NULL DEFAULT GETDATE()
        )
    """)

    cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='orders' AND xtype='U')
        CREATE TABLE orders (
            order_id         INT PRIMARY KEY IDENTITY(1,1),
            customer_id      INT NOT NULL REFERENCES customers(customer_id),
            order_date       DATETIME NOT NULL DEFAULT GETDATE(),
            status           VARCHAR(50) NOT NULL DEFAULT 'pending',
            total_amount     DECIMAL(12,2) NOT NULL DEFAULT 0,
            shipping_city    VARCHAR(100),
            shipping_country VARCHAR(100),
            notes            TEXT
        )
    """)

    cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='order_items' AND xtype='U')
        CREATE TABLE order_items (
            order_item_id INT PRIMARY KEY IDENTITY(1,1),
            order_id      INT NOT NULL REFERENCES orders(order_id),
            product_id    INT NOT NULL REFERENCES products(product_id),
            quantity      INT NOT NULL,
            unit_price    DECIMAL(10,2) NOT NULL,
            line_total    DECIMAL(12,2) NOT NULL
        )
    """)

    print("Tables created or verified.")


def seed_categories(cursor):
    categories = [
        ("Electronics", "Electronic devices and accessories"),
        ("Clothing", "Apparel and fashion items"),
        ("Books", "Physical and digital books"),
        ("Home Appliances", "Household appliances and equipment"),
        ("Sports", "Sports and fitness equipment"),
    ]
    for name, desc in categories:
        cursor.execute("""
            IF NOT EXISTS (SELECT 1 FROM categories WHERE category_name = ?)
            INSERT INTO categories (category_name, description) VALUES (?, ?)
        """, name, name, desc)
    print("Categories seeded.")


def seed_products(cursor):
    products = [
        (1, "Laptop Pro 15",       "High performance laptop",         1299.99, 50,  "SKU-LP-001"),
        (1, "Wireless Mouse",      "Ergonomic wireless mouse",          29.99, 200, "SKU-WM-002"),
        (1, "USB-C Hub",           "7-in-1 USB-C hub",                  49.99, 150, "SKU-UH-003"),
        (1, "4K Monitor",          "27 inch 4K display",               399.99,  30, "SKU-MN-004"),
        (1, "Mechanical Keyboard", "RGB mechanical keyboard",          129.99,  75, "SKU-KB-005"),
        (2, "Running Shoes",       "Lightweight running shoes",         89.99, 120, "SKU-RS-006"),
        (2, "Denim Jacket",        "Classic blue denim jacket",         59.99,  80, "SKU-DJ-007"),
        (2, "Cotton T-Shirt",      "100% cotton crew neck",             19.99, 300, "SKU-TS-008"),
        (3, "Python Programming",  "Learn Python from scratch",         39.99, 500, "SKU-PY-009"),
        (3, "Data Science Guide",  "Practical data science handbook",   44.99, 250, "SKU-DS-010"),
        (4, "Air Purifier",        "HEPA air purifier for large rooms", 199.99,  40, "SKU-AP-011"),
        (4, "Coffee Maker",        "12-cup programmable coffee maker",  79.99,  60, "SKU-CM-012"),
        (5, "Yoga Mat",            "Non-slip yoga mat 6mm",             29.99, 180, "SKU-YM-013"),
        (5, "Dumbbells Set",       "Adjustable dumbbell set 5-25kg",   149.99,  35, "SKU-DB-014"),
        (5, "Resistance Bands",    "Set of 5 resistance bands",         24.99, 220, "SKU-RB-015"),
    ]
    for cat_id, name, desc, price, stock, sku in products:
        cursor.execute("""
            IF NOT EXISTS (SELECT 1 FROM products WHERE sku = ?)
            INSERT INTO products (category_id, product_name, description, unit_price, stock_quantity, sku)
            VALUES (?, ?, ?, ?, ?, ?)
        """, sku, cat_id, name, desc, price, stock, sku)
    print("Products seeded.")


def seed_customers(cursor):
    customers = [
        ("Alice",   "Johnson", "alice.johnson@email.com",  "+1-555-0101", "New York",    "NY", "USA", "10001"),
        ("Bob",     "Smith",   "bob.smith@email.com",      "+1-555-0102", "Los Angeles", "CA", "USA", "90001"),
        ("Carol",   "White",   "carol.white@email.com",    "+1-555-0103", "Chicago",     "IL", "USA", "60601"),
        ("David",   "Brown",   "david.brown@email.com",    "+1-555-0104", "Houston",     "TX", "USA", "77001"),
        ("Eva",     "Davis",   "eva.davis@email.com",      "+1-555-0105", "Phoenix",     "AZ", "USA", "85001"),
        ("Frank",   "Miller",  "frank.miller@email.com",   "+1-555-0106", "London",      None, "UK",  "EC1A"),
        ("Grace",   "Wilson",  "grace.wilson@email.com",   "+1-555-0107", "Toronto",     "ON", "Canada", "M5H"),
        ("Henry",   "Moore",   "henry.moore@email.com",    "+1-555-0108", "Sydney",      "NSW","Australia","2000"),
        ("Iris",    "Taylor",  "iris.taylor@email.com",    "+1-555-0109", "Mumbai",      "MH", "India",  "400001"),
        ("James",   "Anderson","james.anderson@email.com", "+1-555-0110", "Berlin",      None, "Germany","10115"),
    ]
    for first, last, email, phone, city, state, country, postal in customers:
        cursor.execute("""
            IF NOT EXISTS (SELECT 1 FROM customers WHERE email = ?)
            INSERT INTO customers (first_name, last_name, email, phone, city, state, country, postal_code)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, email, first, last, email, phone, city, state, country, postal)
    print("Customers seeded.")


def seed_orders(cursor):
    from datetime import datetime, timedelta

    today = datetime.utcnow()

    def days_ago(n):
        return (today - timedelta(days=n)).strftime("%Y-%m-%d")

    orders = [
        (1,  days_ago(5),  "delivered", 1329.98, "New York",    "USA"),
        (1,  days_ago(3),  "delivered",   49.99, "New York",    "USA"),
        (2,  days_ago(10), "delivered",  399.99, "Los Angeles", "USA"),
        (2,  days_ago(2),  "shipped",    149.98, "Los Angeles", "USA"),
        (3,  days_ago(8),  "delivered",   84.98, "Chicago",     "USA"),
        (4,  days_ago(1),  "confirmed",  199.99, "Houston",     "USA"),
        (5,  days_ago(4),  "pending",     54.98, "Phoenix",     "USA"),
        (6,  days_ago(15), "delivered",  169.98, "London",      "UK"),
        (7,  days_ago(7),  "delivered",   74.98, "Toronto",     "Canada"),
        (8,  days_ago(6),  "shipped",    129.99, "Sydney",      "Australia"),
        (9,  days_ago(3),  "pending",     39.99, "Mumbai",      "India"),
        (10, days_ago(2),  "confirmed",  179.98, "Berlin",      "Germany"),
    ]
    for cust_id, date, status, total, city, country in orders:
        cursor.execute("""
            INSERT INTO orders (customer_id, order_date, status, total_amount, shipping_city, shipping_country)
            VALUES (?, ?, ?, ?, ?, ?)
        """, cust_id, date, status, total, city, country)
    print("Orders seeded.")


def seed_order_items(cursor):
    order_items = [
        (1,  1, 1, 1299.99, 1299.99),
        (1,  2, 1,   29.99,   29.99),
        (2,  3, 1,   49.99,   49.99),
        (3,  4, 1,  399.99,  399.99),
        (4,  6, 1,   89.99,   89.99),
        (4,  8, 3,   19.99,   59.99),
        (5,  9, 1,   39.99,   39.99),
        (5, 13, 1,   29.99,   29.99),
        (5,  8, 1,   19.99,   19.99),
        (6, 11, 1,  199.99,  199.99),
        (7, 13, 1,   29.99,   29.99),
        (7, 15, 1,   24.99,   24.99),
        (7,  8, 1,   19.99,   19.99),
        (8,  6, 1,   89.99,   89.99),
        (8,  8, 4,   19.99,   79.99),
        (9,  5, 1,  129.99,  129.99),
        (10, 9, 1,   39.99,   39.99),
        (11, 9, 1,   39.99,   39.99),
        (12,13, 2,   29.99,   59.99),
        (12,15, 4,   24.99,   99.99),
        (12, 8, 1,   19.99,   19.99),
    ]
    for order_id, product_id, qty, unit_price, line_total in order_items:
        cursor.execute("""
            INSERT INTO order_items (order_id, product_id, quantity, unit_price, line_total)
            VALUES (?, ?, ?, ?, ?)
        """, order_id, product_id, qty, unit_price, line_total)
    print("Order items seeded.")


def run():
    print("Connecting to database...")
    conn = get_connection()
    cursor = conn.cursor()

    print("Creating tables...")
    create_tables(cursor)
    conn.commit()

    print("Seeding data...")
    seed_categories(cursor)
    seed_products(cursor)
    seed_customers(cursor)
    conn.commit()

    seed_orders(cursor)
    conn.commit()          # commit orders before reading IDs for order_items

    seed_order_items(cursor)
    conn.commit()

    cursor.close()
    conn.close()
    print("Seed completed successfully.")


if __name__ == "__main__":
    run()