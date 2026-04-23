"""
Test Script — Verify Different Queries Produce Different SQL

Tests that the mock LLM generates unique SQL for each query.
This was the critical bug: all queries returned the same SQL.

Usage:
    python test_queries.py
"""

import sys
import os
import logging

# Setup path
sys.path.insert(0, os.path.dirname(__file__))

# Force mock mode
os.environ["LLM_PROVIDER"] = "mock"

from services.database import initialize_database
from services.vector_store import load_index, build_index
from models.schema_loader import generate_schema_documents
from agents.orchestrator import process_query

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-8s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    print("\n" + "=" * 70)
    print("  TEST: Verify Different Queries → Different SQL")
    print("=" * 70)

    # Initialize database
    print("\n[Setup] Initializing database...")
    initialize_database()

    # Build vector store
    if not load_index():
        print("[Setup] Building FAISS index...")
        docs = generate_schema_documents()
        build_index(docs)
    print("[Setup] Ready!\n")

    # ── Test Cases ──
    test_queries = [
        "Show total sales",
        "Show sales by city",
        "Show customers",
        "Show sales last month",
        "Top 5 customers by revenue",
        "Best selling products",
        "Revenue by product category",
        "Monthly sales trend",
    ]

    results = []
    all_sql = set()
    passed = 0
    failed = 0

    for i, query in enumerate(test_queries, 1):
        print(f"\n{'─' * 60}")
        print(f"  TEST {i}: \"{query}\"")
        print(f"{'─' * 60}")

        try:
            result = process_query(query, llm_mode="mock")

            sql = result.get("sql", "NO SQL")
            success = result.get("success", False)
            row_count = result.get("result", {}).get("row_count", 0)
            intent = result.get("metadata", {}).get("plan", {}).get("intent", "?")
            insight = result.get("insight", "")[:80] if result.get("insight") else "None"

            print(f"  ✓ Success: {success}")
            print(f"  ✓ Intent:  {intent}")
            print(f"  ✓ SQL:     {sql}")
            print(f"  ✓ Rows:    {row_count}")
            print(f"  ✓ Insight: {insight}...")

            results.append({
                "query": query,
                "sql": sql,
                "success": success,
                "rows": row_count,
            })

            if sql in all_sql:
                print(f"  ✗ DUPLICATE SQL DETECTED!")
                failed += 1
            else:
                all_sql.add(sql)
                passed += 1

        except Exception as e:
            print(f"  ✗ ERROR: {e}")
            failed += 1
            results.append({"query": query, "sql": "ERROR", "success": False, "rows": 0})

    # ── Summary ──
    print(f"\n\n{'=' * 70}")
    print(f"  RESULTS SUMMARY")
    print(f"{'=' * 70}\n")

    for r in results:
        status = "✓" if r["success"] else "✗"
        print(f"  {status} [{r['rows']:>3} rows] {r['query']:<35} → {r['sql'][:60]}")

    print(f"\n  Unique SQL queries: {len(all_sql)} / {len(test_queries)}")
    print(f"  Passed: {passed}  |  Failed: {failed}")

    if failed == 0 and len(all_sql) == len(test_queries):
        print(f"\n  ✅ ALL TESTS PASSED — Every query produces unique SQL!")
    else:
        print(f"\n  ❌ SOME TESTS FAILED — Check duplicate SQL above")

    print(f"{'=' * 70}\n")
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
