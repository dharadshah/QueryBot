import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from app.constants.app_constants import AgentName


@dataclass
class AgentSpan:
    agent: str
    started_at: float = field(default_factory=time.monotonic)
    ended_at: Optional[float] = None
    input_summary: Optional[str] = None
    output_summary: Optional[str] = None
    success: bool = True
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def end(
        self,
        success: bool = True,
        output_summary: str = None,
        error: str = None,
        metadata: dict = None,
    ) -> None:
        self.ended_at = time.monotonic()
        self.success = success
        self.output_summary = output_summary
        self.error = error
        if metadata:
            self.metadata.update(metadata)

    @property
    def latency_ms(self) -> Optional[int]:
        if self.ended_at is None:
            return None
        return int((self.ended_at - self.started_at) * 1000)


@dataclass
class SessionTrace:
    session_id: str
    user_question: str
    started_at: datetime = field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None
    spans: list[AgentSpan] = field(default_factory=list)
    retry_count: int = 0
    final_sql: Optional[str] = None
    rows_returned: Optional[int] = None
    success: bool = False
    error: Optional[str] = None

    def start_span(self, agent: str, input_summary: str = None) -> AgentSpan:
        span = AgentSpan(agent=agent, input_summary=input_summary)
        self.spans.append(span)
        return span

    def end_session(
        self,
        success: bool,
        final_sql: str = None,
        rows_returned: int = None,
        error: str = None,
    ) -> None:
        self.ended_at = datetime.utcnow()
        self.success = success
        self.final_sql = final_sql
        self.rows_returned = rows_returned
        self.error = error

    @property
    def total_latency_ms(self) -> Optional[int]:
        if self.ended_at is None:
            return None
        delta = self.ended_at - self.started_at
        return int(delta.total_seconds() * 1000)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "user_question": self.user_question,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "total_latency_ms": self.total_latency_ms,
            "retry_count": self.retry_count,
            "final_sql": self.final_sql,
            "rows_returned": self.rows_returned,
            "success": self.success,
            "error": self.error,
            "spans": [
                {
                    "agent": s.agent,
                    "latency_ms": s.latency_ms,
                    "success": s.success,
                    "input_summary": s.input_summary,
                    "output_summary": s.output_summary,
                    "error": s.error,
                    "metadata": s.metadata,
                }
                for s in self.spans
            ],
        }