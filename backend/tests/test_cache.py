"""Tests for the query result cache."""

from services import query_cache


def test_cache_miss_returns_none():
    query_cache.invalidate()
    result = query_cache.get("unique query xyz", None, False, False)
    assert result is None


def test_cache_stores_and_retrieves():
    query_cache.invalidate()
    response = {
        "success": True,
        "query": "total sales",
        "sql": "SELECT 1;",
        "result": {"columns": ["x"], "rows": [{"x": 1}], "row_count": 1},
        "insight": "Test insight",
        "metadata": {},
        "agent_logs": [],
    }
    query_cache.set("total sales", None, False, False, response)
    cached = query_cache.get("total sales", None, False, False)
    assert cached is not None
    assert cached["metadata"]["cache_hit"] is True
    assert cached["query"] == "total sales"


def test_cache_invalidates():
    query_cache.set("q", None, False, False, {
        "success": True, "query": "q", "metadata": {},
    })
    query_cache.invalidate()
    assert query_cache.get("q", None, False, False) is None


def test_different_modes_have_separate_keys():
    query_cache.invalidate()
    query_cache.set("q", None, False, False, {"success": True, "query": "q", "metadata": {}})
    assert query_cache.get("q", None, True, False) is None
