# QueryBot

Natural Language to SQL — Multi-Agent Chatbot for eCommerce Data Analysis

QueryBot accepts plain English questions from users and returns accurate,
data-driven answers backed by validated T-SQL queries against a Microsoft
SQL Server eCommerce database. The system uses a multi-agent pipeline with
structured logging, session tracing, and a complete query audit trail.

---

## Agent Pipeline

Each user question passes through four agents in sequence:

```
User Question
      |
      v
[Agent 0: Schema Retriever]
  Input  : User question
  Action : Embeds question, queries ChromaDB vector store
  Output : Top 5 relevant schema chunks (cosine similarity)
      |
      v
[Agent 1: Query Generator]
  Input  : User question + schema context
  Action : Calls Groq/OpenAI LLM to generate T-SQL SELECT query
  Output : Raw SQL string
      |
      v
[Agent 2: Query Validator]
  Layer 1 - Hard Rules (pure Python, no LLM):
    - Statement must be SELECT only
    - No DML/DDL keywords (INSERT, UPDATE, DELETE, DROP, TRUNCATE, etc.)
    - No dangerous system calls (xp_, sp_, OPENROWSET, etc.)
    - No comment injection (--, /* */)
    - No semicolon stacking (multiple statements)
    - TOP clause must be present
    - No cartesian joins (implicit comma joins)
    - Valid T-SQL syntax (sqlglot parser)
  Layer 2 - LLM Guardrail:
    - Query answers the question correctly
    - Joins are logically correct
    - WHERE conditions are appropriate
    - No risk of misleading results
    - Flags unbounded queries (WARN verdict)
  Output : APPROVED / WARN / REJECTED + reason
      |
      |--- REJECTED --> retry loop (max 3 attempts) --> back to Agent 1
      |--- WARN     --> execute with warning flag set
      |--- APPROVED --> execute immediately
      v
[DB Query Tool]
  Input  : Validated SQL string
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
User Response
```

### Retry Loop

If Agent 2 rejects a query, the orchestrator sends the rejection reason
back to Agent 1 and requests a regenerated query. This retry loop runs
up to MAX_RETRIES times (default 3). If all attempts fail, the user
receives an informative error message.

### WARN Verdict

If the LLM guardrail detects that the question implies unbounded results
(e.g. "list all", "show every"), the query is approved with a WARN verdict.
The response includes a note that results may be incomplete due to the
20-row limit.

---

## Observability and Logging

Every agent emits structured JSON log lines. Each line carries:

- `session_id` — ties all events for one question together
- `agent` — which agent emitted the log
- `event` — what happened (query_generated, validation_failed, retry_attempt, etc.)
- `payload` — relevant data (SQL text, row count, latency ms, rule code)

A `SessionTrace` records the full lifecycle including per-agent spans
with latency, input/output summaries, and retry count. The complete
trace is emitted as a single JSON payload at session end.

Every query (approved or rejected) is written to the `query_audit` table
in MSSQL for governance, debugging, and client reporting.

---

## Tech Stack

| Component | Technology |
|---|---|
| API Framework | FastAPI |
| ORM | SQLAlchemy 2.x |
| Database | Microsoft SQL Server Express |
| Vector Store | ChromaDB (local persistent) |
| Embeddings | ChromaDB default (local) or OpenAI text-embedding-3-small |
| LLM (default) | Groq — llama-3.3-70b-versatile (free tier) |
| LLM (alternate) | OpenAI — gpt-4o-mini (paid) |
| SQL Parsing | sqlglot (T-SQL dialect) |
| UI | Gradio (Phase 5) |
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
│   │   └── chat_service.py          Orchestrator and retry loop
│   ├── routers/
│   │   └── chat.py                  POST /chat endpoint
│   ├── models/
│   │   └── audit.py                 QueryAudit ORM model
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
│   │   └── llm_client.py            Groq/OpenAI client factory
│   └── constants/
│       ├── app_constants.py         Roles, events, rule codes, limits
│       ├── prompts.py               All LLM prompt templates
│       └── messages.py              Log and user-facing strings
├── seed/
│   └── seed_data.py                 Standalone eCommerce DB seeder
├── ui/
│   └── gradio_app.py                Gradio chat UI (Phase 5)
├── tests/
│   ├── manual_test_db_tool.py
│   ├── manual_test_schema_retriever.py
│   ├── manual_test_pipeline.py
│   └── manual_test_full_pipeline.py
├── run.py                           Starts FastAPI + Gradio (Phase 5)
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

Create a `.env` file in the project root:

```env
MSSQL_SERVER=localhost\SQLEXPRESS
MSSQL_DATABASE=QueryBotDB
MSSQL_USE_WINDOWS_AUTH=true
MSSQL_DRIVER=ODBC Driver 17 for SQL Server

LLM_PROVIDER=groq
GROQ_API_KEY=gsk_your_key_here
OPENAI_API_KEY=sk_your_key_here

CHROMA_PERSIST_PATH=chroma_store
CHROMA_COLLECTION_NAME=ecommerce_schema
TOP_K_CHUNKS=5
MAX_RETRIES=3
MAX_ROWS=20
APP_ENV=development
LOG_LEVEL=INFO
```

### 3. Create the database

In SQL Server Management Studio, connect to `localhost\SQLEXPRESS`
with Windows Authentication and run:

```sql
CREATE DATABASE QueryBotDB;
```

### 4. Seed the eCommerce data

```powershell
poetry run python seed/seed_data.py
```

### 5. Start the application

```powershell
poetry run uvicorn app.main:app --reload
```

On first startup the app will:
- Verify the MSSQL connection
- Create the `query_audit` table
- Embed the schema into ChromaDB (one time only, idempotent)

### 6. Test the API

```
GET  http://localhost:8000/health

POST http://localhost:8000/chat
     Body: {"question": "Show me all products in the electronics category"}
```

---

## LLM Provider Switching

Switch between Groq and OpenAI with one line in `.env`. No code changes required.

```env
LLM_PROVIDER=groq    # uses llama-3.3-70b-versatile — free tier
LLM_PROVIDER=openai  # uses gpt-4o-mini — paid
```

---

## Query Safety Rules

### Layer 1 — Hard Rules (instant, no LLM cost)

| Rule | What is blocked |
|---|---|
| SELECT only | INSERT, UPDATE, DELETE, DROP, TRUNCATE, ALTER, CREATE, EXEC, MERGE |
| No system calls | xp_, sp_, OPENROWSET, OPENDATASOURCE, OPENQUERY, BULK INSERT |
| No injection | SQL comments: -- and /* */ |
| No stacking | Multiple statements separated by semicolons |
| TOP required | Any SELECT without a TOP clause |
| No cartesian joins | Comma-separated tables in FROM clause |
| Valid syntax | Any T-SQL parse error detected by sqlglot |

### Layer 2 — LLM Guardrail

The LLM reviews the query against the original question and schema context.
Returns one of three verdicts:

| Verdict | Meaning | Action |
|---|---|---|
| APPROVED | Query is correct and safe | Execute immediately |
| WARN | Query correct but may return incomplete results | Execute with warning message to user |
| REJECTED | Query is incorrect or unsafe | Retry with rejection reason (up to MAX_RETRIES) |

---

## Row Limit Policy

- Maximum 20 rows returned per query (hard ceiling enforced by db_query_tool)
- If the query has TOP N where N is less than 20, the lower limit is respected
- If the query has no TOP clause, TOP 20 is injected automatically
- If results are capped at 20, a warning is appended to the user response
- If the question implies all results, a warning is appended regardless of row count

---

## Audit Trail

Every query is written to the `query_audit` table in MSSQL:

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
| created_at | UTC timestamp when the audit record was created |

---

## Future Phases

| Phase | Scope |
|---|---|
| Phase 5 | Gradio chat UI — simple web interface for the chatbot |
| Phase 6 | User authentication and role-based query filtering |
| | Guest: product catalogue queries only |
| | Customer: own orders and purchase history only |
| | Admin: full access including sales aggregations and audit data |
