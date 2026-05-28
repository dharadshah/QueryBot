import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


# This engine is only for our system's own audit table
engine = create_engine(
    settings.db_connection_string,
    echo=settings.app_env == "development",
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def verify_connection() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Audit database connection verified successfully")
        return True
    except Exception as e:
        logger.error("Audit database connection failed: %s", str(e))
        return False


def create_audit_tables() -> None:
    try:
        from app.models.audit import QueryAudit          # noqa: F401
        from app.models.conversation import ConversationHistory  # noqa: F401
        Base.metadata.create_all(bind=engine)
        logger.info("Audit tables created or verified successfully")
    except Exception as e:
        logger.error("Failed to create audit tables: %s", str(e))
        raise