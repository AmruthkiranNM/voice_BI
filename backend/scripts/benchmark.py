"""
SQL Generation Benchmark

Measures how often the agent pipeline produces SQL that returns the
*correct answer* (not necessarily identical SQL text) for a small set of
hand-labeled natural-language questions against a known dataset.

This requires a running local Ollama instance with the configured model
pulled (see backend/config.py / OLLAMA_MODEL) — it is NOT part of the
pytest suite because it depends on the LLM actually being available and
takes much longer than a unit test.

Usage (from backend/):
    python -m scripts.benchmark
"""

from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config

BENCH_DB = str(Path(config.DATA_DIR) / "_benchmark.db")
config.DATABASE_PATH = BENCH_DB

import services.database as database_module
database_module.DATABASE_PATH = BENCH_DB

from agents.orchestrator import process_query
from services.vector_store import build_index
from models.schema_loader import generate_schema_documents


def _seed_database() -> None:
    Path(BENCH_DB).unlink(missing_ok=True)
    conn = sqlite3.connect(BENCH_DB)
    conn.execute("""
        CREATE TABLE sales (
            id INTEGER PRIMARY KEY,
            product TEXT,
            region TEXT,
            amount REAL,
            sale_date TEXT
        )
    """)
    rows = [
        (1, "Widget", "North", 100.0, "2024-01-05"),
        (2, "Widget", "South", 150.0, "2024-01-12"),
        (3, "Gadget", "North", 300.0, "2024-02-02"),
        (4, "Gadget", "South", 50.0, "2024-02-15"),
        (5, "Gizmo", "North", 700.0, "2024-03-01"),
        (6, "Gizmo", "South", 220.0, "2024-03-20"),
        (7, "Widget", "North", 90.0, "2024-04-04"),
        (8, "Gadget", "North", 410.0, "2024-04-18"),
    ]
    conn.executemany("INSERT INTO sales VALUES (?, ?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()

    schema_docs = generate_schema_documents()
    if schema_docs:
        build_index(schema_docs)


# Each case: (question, expected_check) where expected_check(rows) -> bool
CASES = [
    (
        "What is the total revenue?",
        lambda rows: any(abs(float(list(r.values())[0]) - 2020.0) < 1 for r in rows),
    ),
    (
        "Which product had the highest total sales amount?",
        lambda rows: rows and "Gizmo" in str(list(rows[0].values())[0]),
    ),
    (
        "How many sales happened in the North region?",
        lambda rows: any(int(float(list(r.values())[0])) == 5 for r in rows),
    ),
    (
        "What is the average sale amount?",
        lambda rows: any(200 < float(list(r.values())[0]) < 300 for r in rows),
    ),
    (
        "Show total revenue by region",
        lambda rows: len(rows) == 2,
    ),
]


def run() -> None:
    print("Seeding benchmark database...")
    _seed_database()

    passed = 0
    total_time = 0.0

    for question, check in CASES:
        start = time.time()
        result = process_query(question, table_name="sales", cache_mode=False, fast_mode=True)
        elapsed = time.time() - start
        total_time += elapsed

        ok = False
        if result.get("success"):
            rows = result["result"]["rows"]
            try:
                ok = bool(check(rows))
            except Exception:
                ok = False

        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1

        print(f"[{status}] ({elapsed:.1f}s) {question}")
        if not ok:
            print(f"         SQL: {result.get('sql')}")
            print(f"         rows: {result.get('result', {}).get('rows')}")
            if result.get("error"):
                print(f"         error: {result['error']}")

    print()
    print(f"Accuracy: {passed}/{len(CASES)} ({passed / len(CASES) * 100:.0f}%)")
    print(f"Avg time per query: {total_time / len(CASES):.1f}s")

    Path(BENCH_DB).unlink(missing_ok=True)


if __name__ == "__main__":
    run()
