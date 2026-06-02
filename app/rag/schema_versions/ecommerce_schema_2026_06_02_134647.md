<!-- AUTO-GENERATED SECTION — DO NOT EDIT MANUALLY -->
<!-- Last extracted: 2026-06-02T13:45:39.421303 -->
<!-- Changes to this section will be overwritten on next startup -->

# eCommerce Database Schema

## Database: QueryBotDB
## Dialect: Microsoft SQL Server (T-SQL)
## Extracted at: 2026-06-02T13:45:39.421303

---

## Table: categories

Columns:
- category_id (INT, PRIMARY KEY, AUTOINCREMENT, NOT NULL)
- category_name (VARCHAR(100), NOT NULL)
- description (TEXT, NULLABLE)
- is_active (BIT, NOT NULL, DEFAULT 1)

Primary Key: category_id

Indexes:
- PK__categori__D54EE9B41C0663C2 on (category_id) (UNIQUE, PRIMARY KEY)
- UQ__categori__5189E255EE6FFEBD on (category_name) (UNIQUE)

---

## Table: conversation_history

Columns:
- id (INT, PRIMARY KEY, AUTOINCREMENT, NOT NULL)
- session_id (VARCHAR(100), NOT NULL)
- turn_number (INT, NOT NULL)
- user_question (VARCHAR, NOT NULL)
- generated_sql (VARCHAR, NULLABLE)
- answer (VARCHAR, NOT NULL)
- created_at (DATETIME, NOT NULL)

Primary Key: id

Indexes:
- ix_conversation_session_id on (session_id)
- ix_conversation_turn on (session_id, turn_number)
- PK__conversa__3213E83F859CD3E0 on (id) (UNIQUE, PRIMARY KEY)

---

## Table: customers

Columns:
- customer_id (INT, PRIMARY KEY, AUTOINCREMENT, NOT NULL)
- first_name (VARCHAR(100), NOT NULL)
- last_name (VARCHAR(100), NOT NULL)
- email (VARCHAR(255), NOT NULL)
- phone (VARCHAR(20), NULLABLE)
- city (VARCHAR(100), NULLABLE)
- state (VARCHAR(100), NULLABLE)
- country (VARCHAR(100), NULLABLE)
- postal_code (VARCHAR(20), NULLABLE)
- created_at (DATETIME, NOT NULL, DEFAULT getdate)

Primary Key: customer_id

Indexes:
- PK__customer__CD65CB855BB7097A on (customer_id) (UNIQUE, PRIMARY KEY)
- UQ__customer__AB6E6164EE5B7ED8 on (email) (UNIQUE)

---

## Table: order_items

Columns:
- order_item_id (INT, PRIMARY KEY, AUTOINCREMENT, NOT NULL)
- order_id (INT, NOT NULL)
- product_id (INT, NOT NULL)
- quantity (INT, NOT NULL)
- unit_price (DECIMAL(10,2), NOT NULL)
- line_total (DECIMAL(12,2), NOT NULL)

Primary Key: order_item_id

Indexes:
- PK__order_it__3764B6BC98840DF4 on (order_item_id) (UNIQUE, PRIMARY KEY)

Foreign Keys:
- FK__order_ite__order__03F0984C: order_id -> orders.order_id
- FK__order_ite__produ__04E4BC85: product_id -> products.product_id

---

## Table: orders

Columns:
- order_id (INT, PRIMARY KEY, AUTOINCREMENT, NOT NULL)
- customer_id (INT, NOT NULL)
- order_date (DATETIME, NOT NULL, DEFAULT getdate)
- status (VARCHAR(50), NOT NULL, DEFAULT 'pending')
- total_amount (DECIMAL(12,2), NOT NULL, DEFAULT 0)
- shipping_city (VARCHAR(100), NULLABLE)
- shipping_country (VARCHAR(100), NULLABLE)
- notes (TEXT, NULLABLE)

Primary Key: order_id

Indexes:
- PK__orders__46596229FE1C60B4 on (order_id) (UNIQUE, PRIMARY KEY)

Foreign Keys:
- FK__orders__customer__7E37BEF6: customer_id -> customers.customer_id

---

## Table: products

Columns:
- product_id (INT, PRIMARY KEY, AUTOINCREMENT, NOT NULL)
- category_id (INT, NOT NULL)
- product_name (VARCHAR(255), NOT NULL)
- description (TEXT, NULLABLE)
- unit_price (DECIMAL(10,2), NOT NULL)
- stock_quantity (INT, NOT NULL, DEFAULT 0)
- sku (VARCHAR(100), NOT NULL)
- is_active (BIT, NOT NULL, DEFAULT 1)
- created_at (DATETIME, NOT NULL, DEFAULT getdate)

Primary Key: product_id

Indexes:
- PK__products__47027DF50F0231E1 on (product_id) (UNIQUE, PRIMARY KEY)
- UQ__products__DDDF4BE71C6A07AA on (sku) (UNIQUE)

Foreign Keys:
- FK__products__catego__74AE54BC: category_id -> categories.category_id

---

## Table: query_audit

Columns:
- audit_id (INT, PRIMARY KEY, AUTOINCREMENT, NOT NULL)
- session_id (VARCHAR(100), NOT NULL)
- user_question (VARCHAR, NOT NULL)
- generated_sql (VARCHAR, NOT NULL)
- was_approved (BIT, NOT NULL)
- rejection_reason (VARCHAR, NULLABLE)
- retry_count (INT, NOT NULL)
- rows_returned (INT, NULLABLE)
- execution_time_ms (INT, NULLABLE)
- plan_analysis (VARCHAR, NULLABLE)
- created_at (DATETIME, NOT NULL)

Primary Key: audit_id

Indexes:
- ix_query_audit_created_at on (created_at)
- ix_query_audit_session_id on (session_id)
- PK__query_au__5AF33E33BD756310 on (audit_id) (UNIQUE, PRIMARY KEY)

<!-- END AUTO-GENERATED SECTION -->

---

<!-- HUMAN ANNOTATIONS — SAFE TO EDIT -->
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

<!-- END HUMAN ANNOTATIONS -->
