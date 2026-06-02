import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.config import settings
from app.database import verify_connection, create_audit_tables
from app.observability.logger import setup_logging
from app.rag.embedder import embed_schema
from app.routers.chat import router as chat_router
from app.routers.customers import router as customers_router
from app.constants.messages import (
    SESSION_STARTED,
    SESSION_COMPLETED,
    SESSION_FAILED,
)
from app.rag.schema_extractor import run_extraction

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---

    # 1. Initialise structured logging first
    setup_logging(log_level=settings.log_level)
    logger.info(
        SESSION_STARTED.format(session_id="app_startup"),
        extra={
            "agent": "app",
            "event": "startup_initiated",
            "session_id": "app_startup",
            "payload": {
                "env": settings.app_env,
                "log_level": settings.log_level,
            },
        },
    )

    # 2. Verify database connection
    logger.info(
        "Verifying database connection",
        extra={
            "agent": "app",
            "event": "db_connection_check",
            "session_id": "app_startup",
            "payload": {},
        },
    )
    if not verify_connection():
        logger.error(
            SESSION_FAILED.format(
                session_id="app_startup",
                error="Database connection could not be established",
            ),
            extra={
                "agent": "app",
                "event": "db_connection_failed",
                "session_id": "app_startup",
                "payload": {},
            },
        )
        raise RuntimeError("Database connection could not be established. Aborting startup.")

    # 3. Create audit tables if they do not exist
    logger.info(
        "Creating audit tables if not present",
        extra={
            "agent": "app",
            "event": "audit_table_init",
            "session_id": "app_startup",
            "payload": {},
        },
    )
    create_audit_tables()

    # 3b. Check for schema changes against live database
    logger.info(
        "Checking for schema changes",
        extra={
            "agent": "app",
            "event": "schema_check",
            "session_id": "app_startup",
            "payload": {},
        },
    )
    try:
        extraction_result = run_extraction()
        if extraction_result["changed"]:
            logger.warning(
                "DATABASE SCHEMA HAS CHANGED — human review required before re-embedding.\n"
                "%s",
                extraction_result["message"],
                extra={
                    "agent": "app",
                    "event": "schema_changed",
                    "session_id": "app_startup",
                    "payload": {
                        "table_count": extraction_result["table_count"],
                        "archive_path": extraction_result["archive_path"],
                        "message": extraction_result["message"],
                    },
                },
            )
            print(
                f"\n{'=' * 60}\n"
                f"  SCHEMA CHANGE DETECTED\n"
                f"  {extraction_result['table_count']} tables found\n"
                f"  Old version archived to:\n"
                f"  {extraction_result['archive_path']}\n"
                f"\n"
                f"  Review the updated schema file at:\n"
                f"  app/rag/schema_definitions/ecommerce_schema.md\n"
                f"\n"
                f"  When satisfied, re-embed ChromaDB by running:\n"
                f"  poetry run python -m app.rag.embedder --force-reembed\n"
                f"{'=' * 60}\n"
            )
        else:
            logger.info(
                "Schema unchanged — %d tables. No re-embedding required.",
                extraction_result["table_count"],
                extra={
                    "agent": "app",
                    "event": "schema_unchanged",
                    "session_id": "app_startup",
                    "payload": {
                        "table_count": extraction_result["table_count"],
                    },
                },
            )
    except Exception as e:
        logger.warning(
            "Schema check failed — continuing with existing schema: %s",
            str(e),
            extra={
                "agent": "app",
                "event": "schema_check_failed",
                "session_id": "app_startup",
                "payload": {"error": str(e)},
            },
        )

    # 4. Embed schema into ChromaDB — idempotent
    logger.info(
        "Starting schema embedding into ChromaDB",
        extra={
            "agent": "app",
            "event": "schema_embedding_init",
            "session_id": "app_startup",
            "payload": {
                "collection": settings.chroma_collection_name,
                "persist_path": settings.chroma_persist_path,
            },
        },
    )
    embed_schema()

    logger.info(
        SESSION_COMPLETED.format(session_id="app_startup"),
        extra={
            "agent": "app",
            "event": "startup_completed",
            "session_id": "app_startup",
            "payload": {},
        },
    )

    yield

    # --- Shutdown ---
    logger.info(
        "Application shutting down",
        extra={
            "agent": "app",
            "event": "shutdown",
            "session_id": "app_shutdown",
            "payload": {},
        },
    )


app = FastAPI(
    title="QueryBot",
    description="Natural language to SQL query chatbot for eCommerce data",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(chat_router)
app.include_router(customers_router)


@app.get("/health", tags=["health"])
def health_check():
    return {
        "status": "ok",
        "env": settings.app_env,
    }