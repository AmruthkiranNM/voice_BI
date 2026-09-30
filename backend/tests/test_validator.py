"""
Tests for the SQL validator agent.

These assertions previously targeted an API the validator no longer has: a
``ValidationError`` exception and an ``is_valid`` key. Because the import
failed, the whole module was skipped by collection and none of the security
checks below were actually running. They are rewritten against the contract
the orchestrator really uses — ``run()`` returns a report rather than raising —
with the same coverage, plus the specific reason each query is refused.
"""

import sqlite3

import pytest

import config
from agents.validator import run as validate


@pytest.fixture
def sales_table(temp_database):
    """Create a minimal 'sales' table so schema validation has something to check."""
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.execute("CREATE TABLE sales (name TEXT, amount REAL)")
    conn.execute("INSERT INTO sales VALUES ('Widget', 100)")
    conn.commit()
    conn.close()
    return "sales"


def reasons(result) -> str:
    return " ".join(result["errors"]).lower()


class TestAllowed:
    def test_allows_simple_select(self, sales_table):
        result = validate("SELECT name, amount FROM sales;")
        assert result["valid"] is True
        assert result["security_valid"] is True

    def test_allows_cte(self, sales_table):
        result = validate("WITH t AS (SELECT amount FROM sales) SELECT SUM(amount) FROM t;")
        assert result["valid"] is True

    def test_allows_updated_at_column_without_false_positive(self, sales_table):
        """A column containing the substring UPDATE must not trip the keyword check."""
        result = validate("SELECT name FROM sales WHERE amount > 0;")
        assert result["security_valid"] is True

        # The keyword matcher is the part under test: word boundaries mean
        # 'updated_at' is not the statement keyword 'UPDATE'.
        report = {"security_valid": True, "errors": []}
        from agents.validator import _check_security

        _check_security("SELECT updated_at FROM sales", report)
        assert report["security_valid"] is True
        assert report["errors"] == []


class TestBlocked:
    """Every destructive shape must be refused, and say why."""

    @pytest.mark.parametrize("sql,keyword", [
        ("DROP TABLE sales;", "drop"),
        ("DELETE FROM sales WHERE id = 1;", "delete"),
        ("INSERT INTO sales VALUES (1, 2);", "insert"),
        ("UPDATE sales SET amount = 0;", "update"),
        ("ALTER TABLE sales ADD COLUMN x INT;", "alter"),
        ("TRUNCATE TABLE sales;", "truncate"),
        ("CREATE TABLE evil (id INT);", "create"),
        ("GRANT ALL ON sales TO PUBLIC;", "grant"),
    ])
    def test_blocks_destructive_statement(self, sql, keyword):
        result = validate(sql)
        assert result["valid"] is False
        assert result["security_valid"] is False
        assert keyword in reasons(result)

    def test_blocks_multi_statement_injection(self, sales_table):
        result = validate("SELECT * FROM sales; DROP TABLE sales;")
        assert result["valid"] is False
        assert result["security_valid"] is False
        assert "multiple sql statements" in reasons(result) or "drop" in reasons(result)

    def test_rejects_statement_that_does_not_start_with_select(self, sales_table):
        result = validate("EXPLAIN SELECT * FROM sales;")
        assert result["valid"] is False
        assert "select or with" in reasons(result)


class TestSchemaScope:
    def test_unknown_table_is_refused(self, sales_table):
        result = validate("SELECT * FROM does_not_exist;")
        assert result["valid"] is False
        assert result["schema_valid"] is False
        assert "does not exist" in reasons(result)

    def test_table_outside_the_selected_source_is_refused(self, sales_table):
        conn = sqlite3.connect(config.DATABASE_PATH)
        conn.execute("CREATE TABLE other (x REAL)")
        conn.commit()
        conn.close()

        result = validate("SELECT * FROM other;", allowed_tables=["sales"])
        assert result["valid"] is False
        assert "outside the selected data source" in reasons(result)
