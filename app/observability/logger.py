import json
import logging
import sys
from datetime import datetime
from app.constants.app_constants import LogField


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            LogField.TIMESTAMP: datetime.utcnow().isoformat(),
            LogField.LEVEL: record.levelname,
            LogField.AGENT: getattr(record, "agent", "app"),
            LogField.EVENT: getattr(record, "event", "log"),
            LogField.SESSION_ID: getattr(record, "session_id", None),
            LogField.PAYLOAD: getattr(record, "payload", None),
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


def setup_logging(log_level: str = "INFO") -> None:
    level = getattr(logging, log_level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    if root_logger.handlers:
        root_logger.handlers.clear()

    root_logger.addHandler(handler)

    if settings.demo_mode:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("openai").setLevel(logging.WARNING)
        logging.getLogger("groq").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
        logging.getLogger("chromadb").setLevel(logging.WARNING)
        # Suppress all app JSON logs in demo mode
        # Demo logger handles the output instead
        logging.getLogger().setLevel(logging.CRITICAL)


class AgentLogger:
    def __init__(self, agent_name: str, session_id: str):
        self._logger = logging.getLogger(agent_name)
        self._agent = agent_name
        self._session_id = session_id

    def _extra(self, event: str, payload: dict = None) -> dict:
        return {
            "agent": self._agent,
            "event": event,
            "session_id": self._session_id,
            "payload": payload or {},
        }

    def info(self, message: str, event: str, payload: dict = None) -> None:
        self._logger.info(message, extra=self._extra(event, payload))

    def warning(self, message: str, event: str, payload: dict = None) -> None:
        self._logger.warning(message, extra=self._extra(event, payload))

    def error(self, message: str, event: str, payload: dict = None, exc_info=False) -> None:
        self._logger.error(message, extra=self._extra(event, payload), exc_info=exc_info)