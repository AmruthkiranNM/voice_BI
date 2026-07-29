"""
Query result cache for repeated natural-language questions.

Caches full pipeline responses keyed by query text, model, mode flags,
and a database schema fingerprint so stale results are not served after uploads.
"""

import hashlib
import logging
import time
from pathlib import Path
from typing import Any

from config import CACHE_MAX_ENTRIES, CACHE_TTL_SECONDS
from services.database import get_all_table_names, get_database_path

logger = logging.getLogger(__name__)

_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def get_schema_fingerprint() -> str:
    """Fingerprint current DB tables + file mtime for cache invalidation."""
    tables = ",".join(sorted(get_all_table_names()))
    db_path = Path(get_database_path())
    mtime = db_path.stat().st_mtime if db_path.exists() else 0
    raw = f"{tables}:{mtime}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _cache_key(
    query: str,
    model: str | None,
    fast_mode: bool,
    skip_insight: bool,
    table_name: str | None = None,
) -> str:
    from services.auth import current_user_id

    normalized = " ".join(query.strip().lower().split())
    model_name = model or "default"
    table = table_name or "*"
    # get_database_path() already differs per user, but include the user id
    # explicitly so cache entries can never collide across accounts even if
    # two users' DB fingerprints happened to coincide.
    user = current_user_id.get()
    payload = f"user={user}|{normalized}|{model_name}|fast={fast_mode}|insight={not skip_insight}|table={table}"
    fingerprint = get_schema_fingerprint()
    return hashlib.sha256(f"{payload}|{fingerprint}".encode()).hexdigest()


def _evict_expired() -> None:
    now = time.time()
    expired = [k for k, (ts, _) in _cache.items() if now - ts > CACHE_TTL_SECONDS]
    for key in expired:
        del _cache[key]


def _evict_oldest() -> None:
    if len(_cache) < CACHE_MAX_ENTRIES:
        return
    oldest_key = min(_cache, key=lambda k: _cache[k][0])
    del _cache[oldest_key]


def get(
    query: str,
    model: str | None,
    fast_mode: bool,
    skip_insight: bool,
    table_name: str | None = None,
) -> dict[str, Any] | None:
    """Return a cached response if available and still valid."""
    _evict_expired()
    key = _cache_key(query, model, fast_mode, skip_insight, table_name)
    entry = _cache.get(key)
    if not entry:
        return None

    stored_at, response = entry
    if time.time() - stored_at > CACHE_TTL_SECONDS:
        del _cache[key]
        return None

    logger.info("[QueryCache] HIT for query: %s", query[:80])
    cached = dict(response)
    metadata = dict(cached.get("metadata") or {})
    metadata["cache_hit"] = True
    metadata["cached_at_seconds_ago"] = round(time.time() - stored_at, 1)
    metadata["pipeline_time_seconds"] = 0.001
    cached["metadata"] = metadata

    agent_logs = list(cached.get("agent_logs") or [])
    agent_logs.append({
        "agent": "Query Cache",
        "status": "hit",
        "detail": {"message": "Returned cached result"},
        "timestamp_ms": 0,
    })
    cached["agent_logs"] = agent_logs
    return cached


def set(
    query: str,
    model: str | None,
    fast_mode: bool,
    skip_insight: bool,
    response: dict[str, Any],
    table_name: str | None = None,
) -> None:
    """Store a successful pipeline response."""
    if not response.get("success"):
        return

    _evict_expired()
    _evict_oldest()
    key = _cache_key(query, model, fast_mode, skip_insight, table_name)

    stored = dict(response)
    metadata = dict(stored.get("metadata") or {})
    metadata["cache_hit"] = False
    stored["metadata"] = metadata

    _cache[key] = (time.time(), stored)
    logger.info("[QueryCache] STORED query: %s (entries=%d)", query[:80], len(_cache))


def invalidate() -> None:
    """Clear all cached query results (e.g. after dataset upload)."""
    count = len(_cache)
    _cache.clear()
    logger.info("[QueryCache] Invalidated %d entries", count)


def stats() -> dict[str, int]:
    """Return basic cache statistics."""
    _evict_expired()
    return {"entries": len(_cache), "max_entries": CACHE_MAX_ENTRIES}
