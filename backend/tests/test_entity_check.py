from unittest.mock import patch

from services.entity_check import unknown_names

VALUES = {"geo": ["Australia", "Canada", "India", "New Zealand", "UK", "USA"],
          "product": ["After Nines", "Milk Bars"]}


def _run(q):
    with patch("services.database.get_table_schema",
               return_value=[{"column_name": "geo"}, {"column_name": "amount"}]), \
         patch("services.database.get_low_cardinality_values", return_value=VALUES):
        return unknown_names(q, ["sales"])


def test_missing_country_reported():
    assert _run("Predict revenue for Germany next quarter") == ["Germany"]


def test_known_names_pass():
    assert _run("Predict revenue for New Zealand and After Nines next year") == []


def test_months_and_sentence_start_ignored():
    assert _run("Forecast revenue from March for the UK") == []


def test_multiword_unknown_name_kept_together():
    assert _run("forecast sales for South Africa next year") == ["South Africa"]


def test_title_case_question_not_judged():
    assert _run("Forecast Revenue By Region Next Year") == []
