"""Tests for the SQL validator agent."""

import pytest

from agents.validator import ValidationError, run as validate


def test_allows_simple_select():
    result = validate("SELECT name, amount FROM sales;")
    assert result["is_valid"] is True


def test_blocks_drop_statement():
    with pytest.raises(ValidationError) as exc:
        validate("DROP TABLE sales;")
    assert exc.value.violation_type == "security"


def test_blocks_delete_statement():
    with pytest.raises(ValidationError) as exc:
        validate("DELETE FROM sales WHERE id = 1;")
    assert exc.value.violation_type == "security"


def test_blocks_multi_statement_injection():
    with pytest.raises(ValidationError) as exc:
        validate("SELECT * FROM sales; DROP TABLE sales;")
    assert exc.value.violation_type == "security"


def test_rejects_non_select():
    with pytest.raises(ValidationError) as exc:
        validate("INSERT INTO sales VALUES (1, 2);")
    assert exc.value.violation_type == "security"


def test_allows_updated_at_column_without_false_positive():
    """Column names containing UPDATE substring should not trigger security block."""
    from agents.validator import _check_security, _check_select_only
    sql = "SELECT updated_at FROM sales;"
    _check_security(sql)
    _check_select_only(sql)
