"""Tests for business domain detection."""

from services.domain_detector import detect_domain


def test_detects_retail_sales():
    columns = ["order_id", "product_name", "customer_id", "total_price", "sale_date"]
    domain = detect_domain(columns)
    assert domain["id"] == "retail_sales"
    assert domain["confidence"] > 0


def test_detects_inventory():
    columns = ["sku", "stock_quantity", "warehouse", "reorder_level"]
    domain = detect_domain(columns)
    assert domain["id"] == "inventory"


def test_detects_finance():
    columns = ["expense_amount", "income", "budget", "invoice_date"]
    domain = detect_domain(columns)
    assert domain["id"] == "finance"


def test_falls_back_to_general():
    columns = ["field_a", "field_b", "note"]
    domain = detect_domain(columns)
    assert domain["id"] == "general"


def test_empty_columns():
    domain = detect_domain([])
    assert domain["id"] == "general"
    assert domain["confidence"] == 0.0
