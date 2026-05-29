import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Optional
import sqlglot

logger = logging.getLogger(__name__)

MAX_CACHE_SIZE = 100

# TTL in seconds per table
TABLE_TTL = {
    "categories":           3600,   # 1 hour
    "products":             3600,   # 1 hour
    "customers":            1800,   # 30 minutes
    "orders":               60,     # 1 minute
    "order_items":          60,     # 1 minute
    "query_audit":          0,      # no cache
    "conversation_history": 0,      # no cache
}

DEFAULT_TTL = 300  # 5 minutes for unknown tables


@dataclass
class CachedQuery:
    sql: str
    warn: bool
    warn_message: Optional[str]
    cached_at: float = field(default_factory=time.monotonic)
    ttl_seconds: int = DEFAULT_TTL

    @property
    def is_expired(self) -> bool:
        if self.ttl_seconds == 0:
            return True
        return (time.monotonic() - self.cached_at) > self.ttl_seconds


_cache: dict[str, CachedQuery] = {}


def _extract_tables(sql: str) -> list[str]:
    try:
        statements = sqlglot.parse(sql, dialect="tsql")
        tables = []
        for statement in statements:
            for table in statement.find_all(sqlglot.expressions.Table):
                name = table.name.lower()
                if name:
                    tables.append(name)
        return list(set(tables))
    except Exception:
        return []


def _calculate_ttl(sql: str) -> int:
    tables = _extract_tables(sql)
    if not tables:
        return DEFAULT_TTL

    ttls = []
    for table in tables:
        ttl = TABLE_TTL.get(table, DEFAULT_TTL)
        ttls.append(ttl)

    # Use the shortest TTL — most restrictive wins
    return min(ttls)


def _make_key(question: str, schema_context: str) -> str:
    raw = f"{question.strip().lower()}|{schema_context}"
    return hashlib.md5(raw.encode()).hexdigest()


def get_cached_query(question: str, schema_context: str) -> Optional[CachedQuery]:
    key = _make_key(question, schema_context)
    entry = _cache.get(key)

    if entry is None:
        return None

    if entry.is_expired:
        del _cache[key]
        logger.info("Cache expired for question: %s", question)
        return None

    logger.info(
        "Cache hit for question: %s (TTL remaining: %ds)",
        question,
        int(entry.ttl_seconds - (time.monotonic() - entry.cached_at)),
    )
    return entry


def set_cached_query(
    question: str,
    schema_context: str,
    sql: str,
    warn: bool = False,
    warn_message: str = None,
) -> None:
    ttl = _calculate_ttl(sql)

    if ttl == 0:
        logger.info("Query not cached — table has TTL=0: %s", question)
        return

    if len(_cache) >= MAX_CACHE_SIZE:
        # Evict all expired entries first
        expired_keys = [k for k, v in _cache.items() if v.is_expired]
        for k in expired_keys:
            del _cache[k]

        # If still full, evict oldest
        if len(_cache) >= MAX_CACHE_SIZE:
            oldest_key = next(iter(_cache))
            del _cache[oldest_key]

    key = _make_key(question, schema_context)
    _cache[key] = CachedQuery(
        sql=sql,
        warn=warn,
        warn_message=warn_message,
        ttl_seconds=ttl,
    )
    logger.info(
        "Cached query for question: %s (TTL: %ds, tables: %s)",
        question,
        ttl,
        _extract_tables(sql),
    )