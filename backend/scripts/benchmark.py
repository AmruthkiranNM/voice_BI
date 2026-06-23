"""
SQL Generation Benchmark

Measures how often the agent pipeline produces SQL that returns the
*correct answer* (not necessarily identical SQL text) for a set of
hand-labeled natural-language questions across several datasets.

Each question is tagged with a category (aggregation / filter / grouping /
ranking / trend) so the report shows where the pipeline is strong or weak,
and whether the SQL self-correction retry loop rescued any failures.

Requires a running local Ollama with the configured model pulled
(see backend/config.py / OLLAMA_MODEL). NOT part of the pytest suite —
it depends on the LLM being available and is much slower than a unit test.

Usage (from backend/):
    python -m scripts.benchmark
    python -m scripts.benchmark --no-fast   # full pipeline (planner on)
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config

BENCH_DB = str(Path(config.DATA_DIR) / "_benchmark.db")
config.DATABASE_PATH = BENCH_DB

import services.database as database_module
database_module.DATABASE_PATH = BENCH_DB

from agents.orchestrator import process_query
from services.database import drop_all_user_tables
from services.vector_store import build_index
from models.schema_loader import generate_schema_documents


# ── check helpers ─────────────────────────────────────────────

def _nums(rows):
    """All numeric values found across the result rows."""
    out = []
    for r in rows:
        for v in r.values():
            try:
                out.append(float(v))
            except (TypeError, ValueError):
                continue
    return out


def approx(rows, target, tol=1.0):
    return any(abs(n - target) <= tol for n in _nums(rows))


def has_label(rows, label):
    label = label.lower()
    return any(label in str(v).lower() for r in rows for v in r.values())


def top_is(rows, label):
    return bool(rows) and label.lower() in " ".join(str(v).lower() for v in rows[0].values())


def row_count_is(rows, n):
    return len(rows) == n


# ── datasets + labeled questions ──────────────────────────────

DATASETS = {
    "sales": {
        "create": """
            CREATE TABLE sales (
                id INTEGER PRIMARY KEY, product TEXT, region TEXT,
                amount REAL, sale_date TEXT
            )""",
        "rows": [
            (1, "Widget", "North", 100.0, "2024-01-05"),
            (2, "Widget", "South", 150.0, "2024-01-12"),
            (3, "Gadget", "North", 300.0, "2024-02-02"),
            (4, "Gadget", "South", 50.0, "2024-02-15"),
            (5, "Gizmo", "North", 700.0, "2024-03-01"),
            (6, "Gizmo", "South", 220.0, "2024-03-20"),
            (7, "Widget", "North", 90.0, "2024-04-04"),
            (8, "Gadget", "North", 410.0, "2024-04-18"),
        ],
        "cases": [
            ("aggregation", "What is the total revenue?", lambda r: approx(r, 2020.0, 1)),
            ("aggregation", "What is the average sale amount?", lambda r: any(200 < n < 300 for n in _nums(r))),
            ("aggregation", "How many sales are there in total?", lambda r: approx(r, 8, 0)),
            ("filter", "How many sales happened in the North region?", lambda r: approx(r, 5, 0)),
            ("filter", "What is the total revenue in the South region?", lambda r: approx(r, 420.0, 1)),
            ("grouping", "Show total revenue by region", lambda r: row_count_is(r, 2)),
            ("grouping", "What is the total amount for each product?", lambda r: row_count_is(r, 3)),
            ("ranking", "Which product had the highest total sales amount?", lambda r: top_is(r, "Gizmo")),
            ("ranking", "What are the top 3 sales by amount?", lambda r: row_count_is(r, 3)),
        ],
    },
    "employees": {
        "create": """
            CREATE TABLE employees (
                id INTEGER PRIMARY KEY, name TEXT, department TEXT,
                salary REAL, hire_date TEXT
            )""",
        "rows": [
            (1, "Alice", "Engineering", 90000, "2021-03-01"),
            (2, "Bob", "Engineering", 85000, "2020-06-15"),
            (3, "Carol", "Sales", 60000, "2022-01-10"),
            (4, "Dan", "Sales", 65000, "2019-11-20"),
            (5, "Eve", "HR", 70000, "2023-02-05"),
            (6, "Frank", "Engineering", 95000, "2018-07-30"),
        ],
        "cases": [
            ("aggregation", "What is the average salary?", lambda r: any(70000 < n < 80000 for n in _nums(r))),
            ("aggregation", "How many employees are there?", lambda r: approx(r, 6, 0)),
            ("aggregation", "What is the highest salary?", lambda r: approx(r, 95000, 1)),
            ("filter", "How many employees work in Engineering?", lambda r: approx(r, 3, 0)),
            ("grouping", "What is the average salary by department?", lambda r: row_count_is(r, 3)),
            ("grouping", "How many employees are in each department?", lambda r: row_count_is(r, 3)),
            ("ranking", "Who is the highest paid employee?", lambda r: top_is(r, "Frank")),
        ],
    },
    "restaurant": {
        "create": """
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY, item TEXT, category TEXT,
                price REAL, order_date TEXT
            )""",
        "rows": [
            (1, "Burger", "Main", 12.0, "2024-01-03"),
            (2, "Fries", "Side", 4.5, "2024-01-03"),
            (3, "Pizza", "Main", 15.0, "2024-01-10"),
            (4, "Coffee", "Beverage", 3.0, "2024-02-01"),
            (5, "Burger", "Main", 12.0, "2024-02-14"),
            (6, "Salad", "Main", 9.0, "2024-03-02"),
            (7, "Fries", "Side", 4.5, "2024-03-15"),
        ],
        "cases": [
            ("aggregation", "What is the total revenue from all orders?", lambda r: approx(r, 60.0, 1)),
            ("aggregation", "How many orders were placed?", lambda r: approx(r, 7, 0)),
            ("filter", "How many orders were for the Main category?", lambda r: approx(r, 4, 0)),
            ("grouping", "What is the total revenue by category?", lambda r: row_count_is(r, 3)),
            ("grouping", "How many orders for each item?", lambda r: row_count_is(r, 5)),
            ("ranking", "Which item was ordered most often?", lambda r: top_is(r, "Burger") or top_is(r, "Fries")),
        ],
    },
}


def _seed(name: str, spec: dict) -> str:
    drop_all_user_tables()
    conn = sqlite3.connect(BENCH_DB)
    conn.executescript(spec["create"])
    table = spec["create"].split("CREATE TABLE")[1].split("(")[0].strip()
    placeholders = ",".join("?" * len(spec["rows"][0]))
    conn.executemany(f"INSERT INTO {table} VALUES ({placeholders})", spec["rows"])
    conn.commit()
    conn.close()

    schema_docs = generate_schema_documents()
    if schema_docs:
        build_index(schema_docs)
    return table


def run(fast: bool = True) -> None:
    by_category = defaultdict(lambda: [0, 0])  # category -> [passed, total]
    total_pass = 0
    total = 0
    total_time = 0.0
    retry_rescues = 0

    for ds_name, spec in DATASETS.items():
        table = _seed(ds_name, spec)
        print(f"\n=== Dataset: {ds_name} (table '{table}') ===")

        for category, question, check in spec["cases"]:
            start = time.time()
            result = process_query(question, table_name=table, cache_mode=False, fast_mode=fast)
            elapsed = time.time() - start
            total_time += elapsed
            total += 1
            by_category[category][1] += 1

            ok = False
            if result.get("success"):
                rows = result["result"]["rows"]
                try:
                    ok = bool(check(rows))
                except Exception:
                    ok = False

            # Did the SQL retry loop kick in before succeeding?
            attempts = [
                l for l in result.get("agent_logs", [])
                if l.get("agent") == "SQL Generator Agent"
            ]
            if ok and len(attempts) > 1:
                retry_rescues += 1

            if ok:
                total_pass += 1
                by_category[category][0] += 1

            print(f"  [{'PASS' if ok else 'FAIL'}] ({elapsed:4.1f}s) [{category}] {question}")
            if not ok:
                print(f"          SQL: {result.get('sql')}")
                print(f"          rows: {result.get('result', {}).get('rows')}")
                if result.get("error"):
                    print(f"          error: {result['error']}")

    print("\n" + "=" * 50)
    print(f"Overall accuracy: {total_pass}/{total} ({total_pass / total * 100:.0f}%)")
    print(f"Avg time per query: {total_time / total:.1f}s")
    print(f"Queries rescued by SQL retry loop: {retry_rescues}")
    print("\nPer-category:")
    for cat in sorted(by_category):
        p, t = by_category[cat]
        print(f"  {cat:12s} {p}/{t} ({p / t * 100:.0f}%)")

    Path(BENCH_DB).unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-fast", action="store_true", help="Run full pipeline (planner enabled)")
    args = parser.parse_args()
    run(fast=not args.no_fast)
