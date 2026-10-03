from services.result_facts import answer_extremum, facts_block

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


def test_facts_block_states_true_order():
    facts = facts_block(ROWS)
    assert "Highest total_revenue: New Zealand" in facts
    assert "Lowest total_revenue: USA" in facts
