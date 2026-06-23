"""Tests for upload-time data quality checks."""

import pandas as pd

from services.data_quality import assess


def test_clean_data_scores_high():
    df = pd.DataFrame({
        "product": ["Widget", "Gadget", "Gizmo"],
        "revenue": [100, 200, 300],
    })
    report = assess(df)
    assert report["score"] == 100
    assert report["issue_count"] == 0


def test_flags_missing_values():
    df = pd.DataFrame({
        "product": ["Widget", "Gadget", None, "Gizmo"],
        "revenue": [100, 200, 300, 400],
    })
    report = assess(df)
    types = [i["type"] for i in report["issues"]]
    assert "missing_values" in types
    assert report["score"] < 100


def test_flags_duplicate_rows():
    df = pd.DataFrame({
        "product": ["Widget", "Widget", "Gadget"],
        "revenue": [100, 100, 200],
    })
    report = assess(df)
    types = [i["type"] for i in report["issues"]]
    assert "duplicate_rows" in types


def test_flags_constant_column():
    df = pd.DataFrame({
        "product": ["Widget", "Gadget", "Gizmo"],
        "currency": ["USD", "USD", "USD"],
    })
    report = assess(df)
    types = [i["type"] for i in report["issues"]]
    assert "constant_column" in types


def test_flags_inconsistent_numeric_column():
    df = pd.DataFrame({
        "amount": ["100", "200", "n/a", "300", "$400"],
    })
    report = assess(df)
    types = [i["type"] for i in report["issues"]]
    assert "inconsistent_type" in types
