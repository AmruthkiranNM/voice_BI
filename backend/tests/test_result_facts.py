from services.result_facts import answer_extremum, facts_block
from services.time_context import TimeCoverage, years_outside


def test_years_outside_coverage():
    cov = TimeCoverage(min_date="2021-01-01", max_date="2022-03-31")
    assert years_outside("compare 2022 with 2023", cov) == [2023]
    assert years_outside("revenue in 2021", cov) == []
    assert years_outside("compare 2022 with 2023", TimeCoverage()) == []

# Alphabetical row order, so the first row is NOT the highest.
ROWS = [
    {"geo": "Australia", "total_revenue": 7263151},
    {"geo": "Canada", "total_revenue": 7350091},
    {"geo": "India", "total_revenue": 7310254},
    {"geo": "New Zealand", "total_revenue": 7435918},
    {"geo": "UK", "total_revenue": 7189609},
    {"geo": "USA", "total_revenue": 7012523},
]


def test_lowest_follow_up_answered_from_rows():
    answer = answer_extremum("which one is the lowest", ROWS)
    assert answer.startswith("USA")
    assert "$7,012,523" in answer


def test_highest_ignores_row_order():
    assert answer_extremum("Which is the highest?", ROWS).startswith("New Zealand")


def test_column_words_allowed():
    assert answer_extremum("which geo has the lowest revenue", ROWS).startswith("USA")


def test_new_scope_falls_back_to_query():
    assert answer_extremum("which product is the lowest in 2023", ROWS) is None
    assert answer_extremum("show revenue by month", ROWS) is None


def test_ties_name_all():
    rows = [{"k": "a", "v": 1}, {"k": "b", "v": 1}, {"k": "c", "v": 5}]
    assert answer_extremum("which one is the lowest", rows).startswith("a and b")


def test_missing_value_not_treated_as_zero():
    rows = [{"k": "a", "v": None}, {"k": "b", "v": 3}, {"k": "c", "v": 5}]
    assert answer_extremum("which one is the lowest", rows).startswith("b")


def test_period_changes_are_computed_not_guessed():
    rows = [{"month": "2022-01", "revenue": 262052},
            {"month": "2021-12", "revenue": 126959},
            {"month": "2022-02", "revenue": 107541}]
    facts = facts_block(rows)
    # Chronological even though the rows are not.
    assert "2022-01 vs 2021-12: +$135,093 (+106.4%)" in facts
    assert "2022-02 vs 2022-01: -$154,511 (-59.0%)" in facts


def test_period_changes_skip_missing():
    rows = [{"m": "2021-01", "v": 10}, {"m": "2021-02", "v": None}, {"m": "2021-03", "v": 12}]
    assert "n/a (missing data)" in facts_block(rows)


def test_same_month_comparison_across_years():
    rows = [{"month": "2021-02", "revenue": 3036726}, {"month": "2021-04", "revenue": 2885253},
            {"month": "2022-02", "revenue": 2001643}]
    facts = facts_block(rows)
    assert "month 02: 2022 vs 2021 -$1,035,083 (-34.1%)" in facts
    assert "month 04: no data for 2022" in facts


def test_long_format_comparison():
    rows = [{"year": "2021", "month": "02", "revenue": 300}, {"year": "2022", "month": "02", "revenue": 200},
            {"year": "2021", "month": "05", "revenue": 100}]
    facts = facts_block(rows)
    assert "02: 2022 vs 2021 -$100 (-33.3%)" in facts
    assert "05: no data for 2022" in facts


def test_wide_comparison():
    rows = [{"month": "01", "rev_2021": 10, "rev_2022": 15}, {"month": "02", "rev_2021": 10, "rev_2022": None}]
    facts = facts_block(rows)
    assert "01: rev_2022 vs rev_2021 +5 (+50.0%)" in facts
    assert "02: no data for rev_2022" in facts


def test_integer_division_made_real():
    from agents.sql_agent import _fix_integer_division
    assert _fix_integer_division("SELECT g, SUM(exited) / COUNT(*) AS r FROM t") == \
        "SELECT g, 1.0 * SUM(exited) / COUNT(*) AS r FROM t"
    kept = "SELECT ROUND(100.0 * SUM(a) / NULLIF(SUM(b), 0), 2) FROM t"
    assert _fix_integer_division(kept) == kept
    assert _fix_integer_division("SELECT SUM(a) FROM t") == "SELECT SUM(a) FROM t"


def test_modify_requests_refused_but_questions_pass():
    from agents.orchestrator import _MODIFY_REQUEST
    assert _MODIFY_REQUEST.match("Delete all sales from India")
    assert _MODIFY_REQUEST.match("please update the price of After Nines")
    assert not _MODIFY_REQUEST.match("Change in revenue by month")
    assert not _MODIFY_REQUEST.match("Which product has the highest revenue?")


def test_facts_block_states_true_order():
    facts = facts_block(ROWS)
    assert "Highest total_revenue: New Zealand" in facts
    assert "Lowest total_revenue: USA" in facts
