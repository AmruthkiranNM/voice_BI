"""A measure the data does not record is reported as missing, never as 0."""
from types import SimpleNamespace

import pandas as pd

from agents.orchestrator import _constant_measures
from prediction.engine import EMPTY_FILTER_PREFIX, _note_empty_filter


def test_constant_measure_is_detected():
    sql = "SELECT geo.geo AS country, 0.0 AS churn_rate FROM sales JOIN geo ON 1 GROUP BY country"
    assert _constant_measures(sql) == ["churn_rate"]


def test_null_measure_is_detected():
    assert _constant_measures("SELECT region, NULL AS churn FROM geo") == ["churn"]


def test_real_aggregates_pass():
    sql = ("SELECT strftime('%Y-%m', saledate) AS month, SUM(amount) AS revenue, "
           "ROUND(100.0 * SUM(a) / NULLIF(SUM(b), 0), 2) AS pct FROM sales GROUP BY month")
    assert _constant_measures(sql) == []


def test_inner_constants_ignored():
    sql = "WITH t AS (SELECT 0 AS z FROM sales) SELECT geo, COUNT(*) AS n FROM t GROUP BY geo"
    assert _constant_measures(sql) == []


def test_union_padding_allowed():
    sql = "SELECT 'a' AS k, SUM(x) AS v FROM t UNION ALL SELECT 'b' AS k, NULL AS v FROM t"
    assert _constant_measures(sql) == []


def test_empty_filter_names_missing_value():
    cfg = SimpleNamespace(warnings=[])
    before = pd.DataFrame({"geo": ["India", "UK", "USA"]})
    _note_empty_filter(before, before.iloc[0:0], "geo", {"Germany"}, cfg)
    assert cfg.warnings[0].startswith(EMPTY_FILTER_PREFIX + "geo = Germany")
    assert "India, UK, USA" in cfg.warnings[0]
