"""Tests for comparison-aware fast planning."""

from agents.planner import build_fast_plan


def test_detects_period_comparison():
    plan = build_fast_plan("Compare sales this month vs last month")
    assert plan["intent"] == "comparison"
    assert plan["requires_comparison"] is True
    assert plan["comparison_type"] == "period"


def test_detects_ranking_comparison():
    plan = build_fast_plan("Which product has the highest revenue?")
    assert plan["intent"] == "comparison"
    assert plan["comparison_type"] == "ranking"


def test_detects_growth_comparison():
    plan = build_fast_plan("What is the growth percentage of sales?")
    assert plan["intent"] == "comparison"
    assert plan["comparison_type"] == "growth"


def test_detects_aggregation():
    plan = build_fast_plan("What is the total revenue?")
    assert plan["intent"] == "aggregation"
    assert plan["requires_comparison"] is False
