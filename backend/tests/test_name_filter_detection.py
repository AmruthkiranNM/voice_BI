"""Names from columns too large for the schema context still become filters."""
from unittest.mock import patch

from agents.sql_agent import _detect_categorical_filters

PRODUCTS = [f"Product {i}" for i in range(20)] + ["After Nines", "Milk Bars", "Milk"]


def _values(table, schema=None, max_distinct=12):
    cols = {"category": ["Bars", "Bites", "Other"], "product": PRODUCTS}
    return {c: v for c, v in cols.items() if len(v) <= max_distinct}


def _detect(q):
    with patch("services.database.get_low_cardinality_values", side_effect=_values), \
         patch("services.database.get_table_schema", return_value=[]):
        return _detect_categorical_filters(q, {"pinned_tables": ["products"]})


def test_product_name_beyond_low_cardinality_is_detected():
    assert ("products", "product", "After Nines") in _detect("Revenue for After Nines by month")


def test_partial_name_is_not_a_filter():
    assert not any(c == "product" for _, c, _ in _detect("revenue after the nine months"))


def test_longest_name_wins():
    found = [v for _, c, v in _detect("sales of milk bars") if c == "product"]
    assert found == ["Milk Bars"]


def test_word_inside_product_name_is_not_a_category_filter():
    found = _detect("Compare After Nines and Milk Bars by month")
    assert ("products", "category", "Bars") not in found
    assert {v for _, c, v in found if c == "product"} == {"After Nines", "Milk Bars"}


def test_category_still_detected_on_its_own():
    assert ("products", "category", "Bars") in _detect("revenue of bars vs bites")


def test_no_names_no_filters():
    assert _detect("total revenue by country") == []
