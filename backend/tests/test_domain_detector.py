"""Tests for dynamic dataset profiling."""

from services.domain_detector import (
    analyze_dataset,
    classify_column,
    _infer_business_type,
    _score_themes,
)


def test_profile_detects_business_type():
    columns = ["product_name", "sales_amount", "region"]
    profile = analyze_dataset(columns)

    assert profile["business_type"] in (
        "Retail & E-Commerce", "Sales & Revenue", "Sales & Product Data",
    )
    assert "sales_amount" in profile["numeric_columns"]
    assert "region" in profile["category_columns"]
    assert profile["roles"]["money"] == "sales_amount"


def test_different_csvs_get_different_business_types():
    sales = analyze_dataset(["revenue", "product", "customer_city"])
    hr = analyze_dataset(["employee_id", "salary", "department"])

    assert sales["business_type"] != hr["business_type"]
    assert "salary" in hr["numeric_columns"]


def test_restaurant_columns_detected_with_strong_signals():
    columns = ["menu_item", "tip_amount", "dish_name", "order_date"]
    profile = analyze_dataset(columns)
    assert profile["id"] == "restaurant"
    assert "Restaurant" in profile["business_type"]


def test_generic_order_columns_are_not_restaurant():
    columns = ["ORDERNUMBER", "QUANTITYORDERED", "SALES", "ORDERDATE", "CUSTOMERNAME", "PRODUCTLINE"]
    profile = analyze_dataset(columns)

    assert profile["id"] != "restaurant"
    assert "Restaurant" not in profile["business_type"]


def test_sales_sample_columns_classified_as_sales():
    columns = [
        "ORDERNUMBER", "QUANTITYORDERED", "PRICEEACH", "SALES", "ORDERDATE",
        "PRODUCTLINE", "CUSTOMERNAME", "COUNTRY", "TERRITORY",
    ]
    profile = analyze_dataset(columns)
    assert profile["id"] in ("sales", "retail", "general")
    assert "Restaurant" not in profile["business_type"]


def test_empty_columns():
    profile = analyze_dataset([])
    assert profile["confidence"] == 0.0


def test_classify_numeric_by_sqlite_type():
    assert classify_column("col_a", "REAL") == "numeric"
    assert classify_column("col_b", "INTEGER") == "numeric"


def test_classify_date_column():
    assert classify_column("order_date", "TEXT") == "date"


def test_restaurant_scores_higher_than_sales_for_menu_data():
    restaurant_cols = ["menu_item", "tip_amount", "dish_name"]
    scores = _score_themes(restaurant_cols)
    assert scores["restaurant"] > scores["sales"]
