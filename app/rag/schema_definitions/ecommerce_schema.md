# eCommerce Database Schema

## Database: QueryBotDB
## Dialect: Microsoft SQL Server (T-SQL)

---

## Table: users

Description: Stores all user accounts for the system. Every person who interacts with the system has a user record. A user can have one of three roles: guest, customer, or admin.

Columns:
- user_id (INT, PRIMARY KEY, AUTOINCREMENT): Unique identifier for the user.
- username (VARCHAR 100, NOT NULL, UNIQUE): Login username.
- email (VARCHAR 255, NOT NULL, UNIQUE): User email address.
- password_hash (VARCHAR 255, NOT NULL): Hashed password, never returned in queries.
- role (VARCHAR 20, NOT NULL, DEFAULT guest): Access role. Values: guest, customer, admin.
- is_active (BIT, NOT NULL, DEFAULT 1): Whether the user account is active.
- created_at (DATETIME, NOT NULL): Timestamp when the user was created.

Indexes:
- ix_users_email on (email)
- ix_users_role on (role)

Relationships:
- One user can have zero or one customer record (one-to-one with customers table).

---

## Table: categories

Description: Master table for product categories. Every product belongs to one category.

Columns:
- category_id (INT, PRIMARY KEY, AUTOINCREMENT): Unique identifier for the category.
- category_name (VARCHAR 100, NOT NULL, UNIQUE): Name of the category. Examples: Electronics, Clothing, Books, Home Appliances, Sports.
- description (TEXT, NULLABLE): Optional description of the category.
- is_active (BIT, NOT NULL, DEFAULT 1): Whether the category is active.

Indexes:
- ix_categories_name on (category_name)

Relationships:
- One category can have many products (one-to-many with products table).

---

## Table: products

Description: Master table for all products available in the eCommerce store. Each product belongs to one category.

Columns:
- product_id (INT, PRIMARY KEY, AUTOINCREMENT): Unique identifier for the product.
- category_id (INT, NOT NULL, FOREIGN KEY -> categories.category_id): The category this product belongs to.
- product_name (VARCHAR 255, NOT NULL): Name of the product.
- description (TEXT, NULLABLE): Optional product description.
- unit_price (DECIMAL 10,2, NOT NULL): Price per unit in USD.
- stock_quantity (INT, NOT NULL, DEFAULT 0): Current stock available.
- sku (VARCHAR 100, NOT NULL, UNIQUE): Stock Keeping Unit code, unique per product.
- is_active (BIT, NOT NULL, DEFAULT 1): Whether the product is available for sale.
- created_at (DATETIME, NOT NULL): Timestamp when the product was added.

Indexes:
- ix_products_category_id on (category_id)
- ix_products_sku on (sku)
- ix_products_name on (product_name)

Relationships:
- Each product belongs to one category (many-to-one with categories table).
- One product can appear in many order items (one-to-many with order_items table).

---

## Table: customers

Description: Stores customer profile information. Every customer must have a linked user account. Customer address information is stored directly in this table.

Columns:
- customer_id (INT, PRIMARY KEY, AUTOINCREMENT): Unique identifier for the customer.
- user_id (INT, NOT NULL, UNIQUE, FOREIGN KEY -> users.user_id): The linked user account.
- first_name (VARCHAR 100, NOT NULL): Customer first name.
- last_name (VARCHAR 100, NOT NULL): Customer last name.
- email (VARCHAR 255, NOT NULL, UNIQUE): Customer email address.
- phone (VARCHAR 20, NULLABLE): Customer phone number.
- city (VARCHAR 100, NULLABLE): Customer city.
- state (VARCHAR 100, NULLABLE): Customer state or province.
- country (VARCHAR 100, NULLABLE): Customer country.
- postal_code (VARCHAR 20, NULLABLE): Customer postal or zip code.
- created_at (DATETIME, NOT NULL): Timestamp when the customer record was created.

Indexes:
- ix_customers_user_id on (user_id)
- ix_customers_email on (email)
- ix_customers_city_country on (city, country)

Relationships:
- Each customer is linked to exactly one user account (one-to-one with users table).
- One customer can have many orders (one-to-many with orders table).

---

## Table: orders

Description: Stores all customer orders. Each order belongs to one customer and contains one or more order items. The total_amount reflects the sum of all line totals in order_items.

Columns:
- order_id (INT, PRIMARY KEY, AUTOINCREMENT): Unique identifier for the order.
- customer_id (INT, NOT NULL, FOREIGN KEY -> customers.customer_id): The customer who placed the order.
- order_date (DATETIME, NOT NULL): Timestamp when the order was placed.
- status (VARCHAR 50, NOT NULL, DEFAULT pending): Current order status. Values: pending, confirmed, shipped, delivered, cancelled.
- total_amount (DECIMAL 12,2, NOT NULL, DEFAULT 0): Total value of the order in USD.
- shipping_city (VARCHAR 100, NULLABLE): City where the order is shipped to.
- shipping_country (VARCHAR 100, NULLABLE): Country where the order is shipped to.
- notes (TEXT, NULLABLE): Optional notes on the order.

Indexes:
- ix_orders_customer_id on (customer_id)
- ix_orders_order_date on (order_date)
- ix_orders_status on (status)

Relationships:
- Each order belongs to one customer (many-to-one with customers table).
- One order can have many order items (one-to-many with order_items table).

---

## Table: order_items

Description: Child table of orders. Each row represents one product line within an order. The line_total is quantity multiplied by unit_price at the time of the order.

Columns:
- order_item_id (INT, PRIMARY KEY, AUTOINCREMENT): Unique identifier for the order item.
- order_id (INT, NOT NULL, FOREIGN KEY -> orders.order_id): The parent order.
- product_id (INT, NOT NULL, FOREIGN KEY -> products.product_id): The product ordered.
- quantity (INT, NOT NULL): Number of units ordered.
- unit_price (DECIMAL 10,2, NOT NULL): Price per unit at the time of the order.
- line_total (DECIMAL 12,2, NOT NULL): Total for this line (quantity x unit_price).

Indexes:
- ix_order_items_order_id on (order_id)
- ix_order_items_product_id on (product_id)

Relationships:
- Each order item belongs to one order (many-to-one with orders table).
- Each order item references one product (many-to-one with products table).

---

## Table: query_audit

Description: Internal audit log table. Every SQL query generated by the system is recorded here regardless of whether it was approved or rejected. Used for governance, debugging, and monitoring.

Columns:
- audit_id (INT, PRIMARY KEY, AUTOINCREMENT): Unique identifier for the audit record.
- session_id (VARCHAR 100, NOT NULL): The session that generated the query.
- user_question (TEXT, NOT NULL): The original question asked by the user.
- generated_sql (TEXT, NOT NULL): The SQL query that was generated.
- was_approved (BIT, NOT NULL): Whether the query passed validation.
- rejection_reason (TEXT, NULLABLE): Reason for rejection if was_approved is false.
- retry_count (INT, NOT NULL, DEFAULT 0): Number of retries before this query was generated.
- rows_returned (INT, NULLABLE): Number of rows returned if the query was executed.
- execution_time_ms (INT, NULLABLE): Query execution time in milliseconds.
- created_at (DATETIME, NOT NULL): Timestamp when this audit record was created.

Indexes:
- ix_query_audit_session_id on (session_id)
- ix_query_audit_created_at on (created_at)

---

## Common Join Patterns

The following join patterns are commonly used in this schema:

### Products with their category:
SELECT TOP 20 p.product_name, p.unit_price, c.category_name
FROM products p
JOIN categories c ON p.category_id = c.category_id

### Orders with customer details:
SELECT TOP 20 o.order_id, o.order_date, o.total_amount, o.status,
       cu.first_name, cu.last_name, cu.email
FROM orders o
JOIN customers cu ON o.customer_id = cu.customer_id

### Order items with product and order details:
SELECT TOP 20 o.order_id, o.order_date, p.product_name,
       oi.quantity, oi.unit_price, oi.line_total
FROM order_items oi
JOIN orders o ON oi.order_id = o.order_id
JOIN products p ON oi.product_id = p.product_id

### Full order summary per customer:
SELECT TOP 20 cu.first_name, cu.last_name,
       COUNT(o.order_id) AS total_orders,
       SUM(o.total_amount) AS total_spent
FROM customers cu
JOIN orders o ON cu.customer_id = o.customer_id
GROUP BY cu.first_name, cu.last_name