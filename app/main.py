import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.config import settings
from app.database import verify_connection, create_audit_tables
from app.observability.logger import setup_logging
from app.rag.embedder import embed_schema
from app.constants.messages import (
    SESSION_STARTED,
    SESSION_COMPLETED,
    SESSION_FAILED,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---

    # 1. Initialise structured logging first so every subsequent
    #    step is captured in the correct format
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

    # 4. Embed schema into ChromaDB
    # Idempotent — skips chunks already embedded
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


@app.get("/health", tags=["health"])
def health_check():
    return {
        "status": "ok",
        "env": settings.app_env,
    }