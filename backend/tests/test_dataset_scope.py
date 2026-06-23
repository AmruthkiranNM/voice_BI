"""Tests that upload replaces prior datasets and queries stay scoped."""

import io

import pandas as pd
import sqlite3
from fastapi.testclient import TestClient

import config
from main import app
from services.database import get_all_table_names


def test_upload_replaces_previous_tables(temp_database):
    client = TestClient(app)

    sales = pd.DataFrame({"product": ["A"], "revenue": [100]})
    buf1 = io.StringIO()
    sales.to_csv(buf1, index=False)
    r1 = client.post(
        "/api/upload",
        files={"file": ("sales.csv", buf1.getvalue(), "text/csv")},
    )
    assert r1.status_code == 200
    assert "sales" in r1.json()["table_name"]

    restaurant = pd.DataFrame({"menu_item": ["Pasta"], "orders": [50]})
    buf2 = io.StringIO()
    restaurant.to_csv(buf2, index=False)
    r2 = client.post(
        "/api/upload",
        files={"file": ("restaurant.csv", buf2.getvalue(), "text/csv")},
    )
    assert r2.status_code == 200
    assert r2.json()["table_name"] == "restaurant"

    tables = get_all_table_names()
    assert tables == ["restaurant"]


def test_rag_pins_to_active_table(temp_database):
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.execute("CREATE TABLE sales (product TEXT, revenue REAL)")
    conn.execute("INSERT INTO sales VALUES ('Widget', 999)")
    conn.execute("CREATE TABLE restaurant (menu_item TEXT, orders INTEGER)")
    conn.execute("INSERT INTO restaurant VALUES ('Burger', 10)")
    conn.commit()
    conn.close()

    from agents.rag_agent import run

    ctx = run("What are the most popular items?", {}, table_name="restaurant")

    assert ctx["retrieved_tables"] == ["restaurant"]
    assert ctx["pinned_table"] == "restaurant"
    assert "menu_item" in ctx["schema_context"]
    assert "Widget" not in ctx["schema_context"]
