from datetime import datetime
from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class QueryAudit(Base):
    __tablename__ = "query_audit"

    audit_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(100), nullable=False)
    user_question: Mapped[str] = mapped_column(Text, nullable=False)
    generated_sql: Mapped[str] = mapped_column(Text, nullable=False)
    was_approved: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rejection_reason: Mapped[str] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_returned: Mapped[int] = mapped_column(Integer, nullable=True)
    execution_time_ms: Mapped[int] = mapped_column(Integer, nullable=True)
    plan_analysis: Mapped[str] = mapped_column(Text, nullable=True)   # new
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_query_audit_session_id", "session_id"),
        Index("ix_query_audit_created_at", "created_at"),
    )