"""Tests for natural-language suggestion generation."""

import sqlite3

import config
from services.suggestions import generate_suggestions_for_table, generate_all_dataset_suggestions


def _create_table(name: str, columns_sql: str, rows: list[tuple]):
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.execute(f"DROP TABLE IF EXISTS [{name}]")
    conn.execute(f"CREATE TABLE [{name}] ({columns_sql})")
    conn.executemany(
        f"INSERT INTO [{name}] VALUES ({','.join('?' * len(rows[0]))})",
        rows,
    )
    conn.commit()
    conn.close()


def test_suggestions_are_natural_language_not_column_names(temp_database):
    _create_table(
        "sales_data",
        "product_name TEXT, sales_amount REAL, region TEXT",
        [("Widget", 100.0, "North"), ("Gadget", 200.0, "South")],
    )
    bundle = generate_suggestions_for_table("sales_data")

    joined = " ".join(bundle["suggestions"]).lower()
    assert "sales amount" not in joined
    assert "product_name" not in joined
    assert any(word in joined for word in ("sales", "revenue", "products", "overview"))


def test_each_dataset_gets_unique_suggestions(temp_database):
    _create_table(
        "sales_data",
        "product_name TEXT, revenue REAL",
        [("A", 10.0)],
    )
    _create_table(
        "payroll",
        "employee TEXT, salary REAL, department TEXT",
        [("Alice", 5000.0, "HR")],
    )

    all_bundles = generate_all_dataset_suggestions()
    by_name = {b["table_name"]: b for b in all_bundles}

    sales_text = " ".join(by_name["sales_data"]["suggestions"]).lower()
    payroll_text = " ".join(by_name["payroll"]["suggestions"]).lower()

    assert "salary" in payroll_text or "team" in payroll_text
    assert sales_text != payroll_text


def test_domain_has_business_type_label(temp_database):
    _create_table(
        "my_custom_data",
        "widget_count INTEGER, factory_code TEXT",
        [("10", "F1")],
    )
    bundle = generate_suggestions_for_table("my_custom_data")

    assert "business_type" in bundle["domain"]
    assert bundle["domain"]["label"] == bundle["domain"]["business_type"]
