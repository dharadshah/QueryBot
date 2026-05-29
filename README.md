# QueryBot

Natural Language to SQL — Multi-Agent Chatbot for eCommerce Data Analysis

QueryBot accepts plain English questions from users and returns accurate,
data-driven answers backed by validated T-SQL queries against a Microsoft
SQL Server eCommerce database. The system uses a multi-agent pipeline with
structured logging, session tracing, conversation history, role-based access
control, and a complete query audit trail.

---

## Agent Pipeline

Each user question passes through four agents in sequence:

```
User Question
      |
      v
[Pre-flight Checks]
  - Write intent detection (add, insert, update, delete, etc.)
  - Role-based permission check on question keywords
  - Guest: blocks order/customer questions immediately
  - Customer: allowed, customer_id injected into context
      |
      v
[Agent 0: Schema Retriever]
  Input  : User question
  Action : Embeds question using local ChromaDB embeddings,
           queries ChromaDB vector store for relevant schema chunks
  Output : Top 5 relevant schema chunks (cosine similarity)
      |
      v
[Query Cache Check]
  - If identical question was asked recently and TTL has not expired:
    skip Agents 1 and 2, go directly to DB Query Tool
  - Cache is bypassed for Customer role (personal data must not be shared)
      |
      v
[Agent 1: Query Generator]
  Input  : User question + schema context + conversation history
           + customer context (for Customer role)
  Action : Calls OpenAI/Groq LLM to generate T-SQL SELECT query
  Output : Raw SQL string
      |
      v
[Agent 2: Query Validator — Two-Layer Hybrid]
  Layer 1 - Hard Rules (pure Python, no LLM, runs first):
    See detailed breakdown below
  Layer 2 - LLM Guardrail (runs only if Layer 1 passes):
    See detailed breakdown below
  Output : APPROVED / WARN / REJECTED + reason
      |
      |--- REJECTED --> retry loop (max 3 attempts) --> back to Agent 1
      |--- WARN     --> execute with warning flag set
      |--- APPROVED --> execute immediately
      |
      v
[SQL Permission Check]
  - Post-validation table-level access check
  - Guest: blocks if SQL touches orders, customers, order_items
  - Customer: blocks if SQL touches other customers' data
  - Admin: no restriction
      |
      v
[DB Query Tool]
  Input  : Validated and permission-checked SQL string
  Action : Executes query via pyodbc against MSSQL
           Enforces TOP 20 ceiling (hard cap)
           Detects if results are capped at 20 rows
  Output : list[dict] of rows
      |
      v
[Agent 3: Response Synthesiser]
  Input  : Original question + rows + warn flags
  Action : Calls LLM to produce natural language answer
           Appends cap warning if rows == 20
           Appends unbounded warning if WARN verdict
  Output : Human-readable answer string
      |
      v
[Conversation History]
  - Exchange saved to MSSQL conversation_history table
  - Last 5 turns loaded on next question in same session
      |
      v
User Response
```

---

## Query Validation — Two-Layer Approach

Agent 2 uses a hybrid validation strategy. Every generated SQL query must
pass both layers before it is allowed to execute.

### Layer 1 — Hard Rules (pure Python, no LLM, runs first)

Hard rules are deterministic, instant, and have zero LLM cost. Rules run
in order from cheapest to most expensive. First failure stops the chain.

| Order | Rule | Method | What is blocked |
|---|---|---|---|
| 1 | No comment injection | String search | SQL comments: -- and /* */ |
| 2 | No semicolon stacking | String search | Multiple statements via ; |
| 3 | Valid T-SQL syntax | sqlglot parser (tsql dialect) | Any parse error |
| 4 | SELECT only | sqlglot AST root node check | INSERT, UPDATE, DELETE, DROP, TRUNCATE, ALTER, CREATE, EXEC, MERGE |
| 5 | No disallowed keywords | Token blocklist + regex | All DML and DDL keywords |
| 6 | No dangerous system calls | String search | xp_, sp_, OPENROWSET, OPENDATASOURCE, OPENQUERY, BULK INSERT |
| 7 | TOP clause present | Regex on SELECT | Any SELECT without TOP N |
| 8 | No cartesian joins | Regex on FROM clause | Comma-separated tables without JOIN ... ON |
| 9 | Execution plan check | SET SHOWPLAN_XML ON | Table scans on large tables, MSSQL missing index warnings |

**Execution Plan Check (Rule 9) — How it works:**

The query is submitted to MSSQL using SET SHOWPLAN_XML ON. This returns
the estimated execution plan as XML without executing the query — zero rows
are read, zero data is touched. The XML is parsed to detect:

- PhysicalOp="Table Scan" on tables with estimated rows above threshold (1000)
- MissingIndexes nodes where MSSQL itself recommends a better index

If either is found the query is rejected and Agent 1 is asked to rewrite
using indexed columns. The plan analysis is logged and persisted to the
query_audit table for every approved query.

### Layer 2 — LLM Guardrail (runs only if Layer 1 passes)

The LLM evaluates semantic correctness — things deterministic rules cannot assess.

| Check | What the LLM evaluates |
|---|---|
| Intent match | Does the query answer what the user actually asked? |
| Join correctness | Are table joins logically valid based on the schema? |
| WHERE appropriateness | Are filter conditions sensible and not overly broad? |
| Misleading results | Could the query return data that misrepresents reality? |
| Unbounded detection | Does the question imply all results with no practical limit? |
| COUNT + TOP awareness | SELECT TOP N COUNT(...) is valid T-SQL — not rejected |
| Conversation context | Does the query correctly resolve references to prior questions? |

Returns one of three structured verdicts:

| Verdict | Meaning | Action |
|---|---|---|
| APPROVED | Query is correct and safe | Execute immediately |
| WARN | Query correct but question implies unbounded results | Execute with warning message appended to response |
| REJECTED | Query is logically incorrect or semantically unsafe | Retry with rejection reason sent back to Agent 1 |

**Fail-open policy:** If the LLM guardrail call fails (API timeout,
malformed JSON), the validator fails open — the query is approved if it
passed all hard rules. LLM availability issues do not block valid queries.

**Optional:** LLM guardrail can be disabled via ENABLE_LLM_GUARDRAIL=false
in .env to reduce latency by ~3 seconds per query. Recommended for demos.

---

## Role-Based Access Control

Three roles with different data access levels:

| Role | Allowed Tables | Restriction |
|---|---|---|
| Guest | products, categories | Order and customer questions blocked at keyword level and SQL level |
| Customer | products, categories, customers, orders, order_items | Queries automatically scoped to own customer_id only |
| Admin | All tables | No restrictions |

**Two-layer enforcement:**

1. Pre-generation keyword check — fast, no LLM cost, blocks obvious cases
2. Post-validation SQL table check — parses generated SQL with sqlglot,
   blocks if restricted tables are referenced regardless of how the question was phrased

**Customer scoping:** When a customer is logged in, the query generator
receives an instruction to always filter orders and order_items by the
customer's own customer_id. This is enforced in the prompt and verified
in the SQL-level permission check.

---

## Conversation History

Each session maintains a sliding window of the last 5 exchanges persisted
to the MSSQL conversation_history table. On every question the prior turns
are loaded and injected into the query generator and LLM guardrail prompts,
enabling follow-up questions like:

- "List all pending orders with customer names"
- "How many of those were to USA?"
- "What is the total value of those orders?"

The LLM resolves references like "those", "them", "the delivered ones"
using the conversation context. History is session-scoped and persists
across browser refreshes as long as the session_id is preserved.

---

## Query Cache

A TTL-based in-memory cache prevents redundant LLM calls for repeated questions.
Cache TTL is determined by which tables the approved SQL touches:

| Tables touched | TTL | Rationale |
|---|---|---|
| categories, products | 3600s (1 hour) | Rarely changes |
| customers | 1800s (30 minutes) | Occasionally changes |
| orders, order_items | 60s (1 minute) | Changes frequently |
| query_audit, conversation_history | 0s (no cache) | System tables |
| Mixed tables | Shortest TTL of all tables | Most restrictive wins |

Cache is bypassed for Customer role — personal data queries must always
be regenerated with the customer_id filter injected.

**Performance impact:** Cached queries skip Agent 1 and Agent 2 entirely,
reducing latency from ~10 seconds to ~2.5 seconds (75% reduction).

---

## Observability and Logging

Every agent emits structured JSON log lines. Each line carries:

- session_id — ties all events for one question together
- agent — which agent emitted the log
- event — what happened (query_generated, validation_failed, retry_attempt, etc.)
- payload — relevant data (SQL text, row count, latency ms, rule code)

A SessionTrace records the full lifecycle including per-agent spans with
latency, input/output summaries, and retry count. The complete trace is
emitted as a single JSON payload at session end.

Every query (approved or rejected) is written to the query_audit table
in MSSQL for governance, debugging, and client reporting.

---

## Tech Stack

| Component | Technology |
|---|---|
| API Framework | FastAPI |
| ORM | SQLAlchemy 2.x |
| Database | Microsoft SQL Server Express |
| Vector Store | ChromaDB (local persistent) |
| Embeddings | ChromaDB default (local, free) or OpenAI text-embedding-3-small |
| LLM (default) | OpenAI — gpt-4o-mini |
| LLM (alternate) | Groq — llama-3.1-8b-instant (free tier) |
| SQL Parsing | sqlglot (T-SQL dialect) |
| Execution Plan | SET SHOWPLAN_XML ON (pre-execution, no data read) |
| UI | Gradio 6.x |
| Package Manager | Poetry |
| Python | 3.11.9 |

---

## Project Structure

```
D:\QueryBot\
├── app/
│   ├── main.py                      FastAPI app, lifespan startup
│   ├── config.py                    Settings from .env
│   ├── database.py                  Audit table engine and session
│   ├── agents/
│   │   ├── schema_retriever.py      Agent 0 — ChromaDB retrieval
│   │   ├── query_generator.py       Agent 1 — LLM SQL generation
│   │   ├── query_validator.py       Agent 2 — Hard rules + LLM guardrail
│   │   └── response_synthesiser.py  Agent 3 — Natural language response
│   ├── tools/
│   │   └── db_query_tool.py         SQL executor with TOP 20 ceiling
│   ├── services/
│   │   ├── chat_service.py          Orchestrator and retry loop
│   │   ├── conversation_store.py    MSSQL-backed conversation history
│   │   ├── permission_filter.py     Role-based access enforcement
│   │   └── query_cache.py           TTL-based in-memory SQL cache
│   ├── routers/
│   │   ├── chat.py                  POST /chat endpoint
│   │   └── customers.py             GET /customers endpoint
│   ├── models/
│   │   ├── audit.py                 QueryAudit ORM model
│   │   └── conversation.py          ConversationHistory ORM model
│   ├── schemas/
│   │   ├── chat.py                  ChatRequest, ChatResponse
│   │   └── user_context.py          UserContext (role, customer_id)
│   ├── rag/
│   │   ├── schema_loader.py         Chunks schema markdown document
│   │   ├── embedder.py              ChromaDB embed and retrieve
│   │   └── schema_definitions/
│   │       └── ecommerce_schema.md  Full schema document for RAG
│   ├── observability/
│   │   ├── logger.py                Structured JSON logger + AgentLogger
│   │   └── tracer.py                SessionTrace and AgentSpan
│   ├── utils/
│   │   ├── llm_client.py            OpenAI/Groq client factory
│   │   └── execution_plan.py        SHOWPLAN_XML retrieval and analysis
│   └── constants/
│       ├── app_constants.py         Roles, events, rule codes, limits
│       ├── prompts.py               All LLM prompt templates
│       └── messages.py              Log and user-facing strings
├── seed/
│   └── seed_data.py                 Standalone eCommerce DB seeder
├── ui/
│   └── gradio_app.py                Gradio chat UI with role selector
├── tests/
│   ├── manual_test_db_tool.py
│   ├── manual_test_schema_retriever.py
│   ├── manual_test_pipeline.py
│   └── manual_test_full_pipeline.py
├── run.py                           Starts FastAPI + Gradio together
├── .env                             Secrets and config (not in Git)
├── pyproject.toml
└── requirements.txt
```

---

## Setup Instructions

### Prerequisites

- Python 3.11.9
- Poetry 2.x
- Microsoft SQL Server Express (local)
- ODBC Driver 17 for SQL Server
- Git

### 1. Install dependencies

```powershell
poetry install
```

### 2. Configure environment

Create a .env file in the project root:

```env
MSSQL_SERVER=localhost\SQLEXPRESS
MSSQL_DATABASE=QueryBotDB
MSSQL_USE_WINDOWS_AUTH=true
MSSQL_DRIVER=ODBC Driver 17 for SQL Server

LLM_PROVIDER=openai
OPENAI_API_KEY=sk_your_key_here
OPENAI_CHAT_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

GROQ_API_KEY=gsk_your_key_here
GROQ_CHAT_MODEL=llama-3.1-8b-instant

CHROMA_PERSIST_PATH=chroma_store
CHROMA_COLLECTION_NAME=ecommerce_schema
TOP_K_CHUNKS=5

MAX_RETRIES=3
MAX_ROWS=20
ENABLE_LLM_GUARDRAIL=true

APP_ENV=development
LOG_LEVEL=INFO
```

### 3. Create the database

In SQL Server Management Studio connect to localhost\SQLEXPRESS with
Windows Authentication and run:

```sql
CREATE DATABASE QueryBotDB;
```

### 4. Seed the eCommerce data

```powershell
poetry run python seed/seed_data.py
```

### 5. Start the application

```powershell
poetry run python run.py
```

On first startup the app will:
- Verify the MSSQL connection
- Create the query_audit and conversation_history tables
- Embed the schema into ChromaDB (one time only, idempotent)
- Load the customer list for the UI dropdown

### 6. Access the UI

```
http://localhost:7860
```

### 7. Test the API directly

```
GET  http://localhost:8000/health
GET  http://localhost:8000/customers

POST http://localhost:8000/chat
     Body: {
       "question": "Show me all products in the electronics category",
       "session_id": "optional-uuid",
       "role": "guest",
       "customer_id": null
     }
```

---

## LLM Provider Switching

Switch between OpenAI and Groq with one line in .env. No code changes required.

```env
LLM_PROVIDER=openai   # uses gpt-4o-mini — paid, higher quality
LLM_PROVIDER=groq     # uses llama-3.1-8b-instant — free tier
```

---

## Row Limit Policy

- Maximum 20 rows returned per query (hard ceiling enforced by db_query_tool)
- If the query has TOP N where N is less than 20, the lower limit is respected
- If the query has no TOP clause, TOP 20 is injected automatically
- If results are capped at 20, a warning is appended to the user response
- If the question implies all results, a warning is appended regardless of row count

---

## Audit Trail

Every query is written to the query_audit table in MSSQL:

| Column | Description |
|---|---|
| session_id | Unique ID per user question (UUID) |
| user_question | Original question text as typed by the user |
| generated_sql | The SQL generated by Agent 1 |
| was_approved | True if the query passed all validation layers |
| rejection_reason | Reason for rejection if was_approved is False |
| retry_count | Number of regeneration attempts before approval or failure |
| rows_returned | Number of rows returned if the query was executed |
| execution_time_ms | Query execution time in milliseconds |
| plan_analysis | JSON summary of execution plan (table scans, missing indexes) |
| created_at | UTC timestamp when the audit record was created |

---

## Performance

| Optimisation | Impact |
|---|---|
| Local ChromaDB embeddings | Saves ~2.5s per query vs OpenAI embeddings |
| max_tokens limits on LLM calls | Saves ~1-2s per query |
| TTL-based query cache | Saves ~7.5s on repeated questions (75% reduction) |
| Optional LLM guardrail | Saves ~3s when disabled |
| COUNT+TOP guardrail fix | Eliminates unnecessary retry cycles on aggregate queries |

Typical latency on new questions: 8-12 seconds
Typical latency on cached questions: 2-3 seconds

---

## Future Phases

| Phase | Scope |
|---|---|
| Pytest suite | Automated tests for validator hard rules, orchestrator, and cache |
| Docker | Containerised deployment for cloud environments |
| JWT authentication | Replace UI role selector with real session-based auth |
| Admin dashboard | Query audit viewer and performance metrics |
| Multi-database support | Connect to additional databases via configurable connection strings |