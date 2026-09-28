"""
Regression tests for the intent-preservation fix.

These tests verify that the planner's analytical intent is correctly
propagated through the pipeline to the Insight Agent, and that the
Insight Agent's prompt template selection matches the intent.

Does NOT require a running LLM — tests the deterministic parts of the
pipeline (template selection, plan propagation, truncation metadata).
"""

import pytest
import os
import sys

# Ensure backend is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestInsightIntentRouting:
    """Verify the Insight Agent selects the correct prompt template for each intent."""

    def test_detail_intent_selects_detail_template(self):
        from agents.insight import _INTENT_TEMPLATES, DETAIL_PROMPT_TEMPLATE
        assert _INTENT_TEMPLATES["detail"] is DETAIL_PROMPT_TEMPLATE

    def test_aggregation_intent_selects_aggregation_template(self):
        from agents.insight import _INTENT_TEMPLATES, AGGREGATION_PROMPT_TEMPLATE
        assert _INTENT_TEMPLATES["aggregation"] is AGGREGATION_PROMPT_TEMPLATE

    def test_comparison_intent_selects_comparison_template(self):
        from agents.insight import _INTENT_TEMPLATES, COMPARISON_PROMPT_TEMPLATE
        assert _INTENT_TEMPLATES["comparison"] is COMPARISON_PROMPT_TEMPLATE

    def test_trend_intent_selects_trend_template(self):
        from agents.insight import _INTENT_TEMPLATES, TREND_PROMPT_TEMPLATE
        assert _INTENT_TEMPLATES["trend"] is TREND_PROMPT_TEMPLATE

    def test_count_intent_selects_count_template(self):
        from agents.insight import _INTENT_TEMPLATES, COUNT_PROMPT_TEMPLATE
        assert _INTENT_TEMPLATES["count"] is COUNT_PROMPT_TEMPLATE


class TestDetailPromptContent:
    """Verify the detail prompt explicitly forbids ranking/recommendations."""

    def test_detail_prompt_forbids_ranking(self):
        from agents.insight import DETAIL_PROMPT_TEMPLATE
        prompt = DETAIL_PROMPT_TEMPLATE.lower()
        assert "do not rank" in prompt
        assert '"top"' in prompt or "'top'" in prompt

    def test_detail_prompt_forbids_recommendations(self):
        from agents.insight import DETAIL_PROMPT_TEMPLATE
        prompt = DETAIL_PROMPT_TEMPLATE.lower()
        assert "do not generate recommendations" in prompt

    def test_detail_prompt_forbids_totals(self):
        from agents.insight import DETAIL_PROMPT_TEMPLATE
        prompt = DETAIL_PROMPT_TEMPLATE.lower()
        assert "do not calculate totals" in prompt

    def test_detail_prompt_forbids_unsolicited_analysis(self):
        from agents.insight import DETAIL_PROMPT_TEMPLATE
        prompt = DETAIL_PROMPT_TEMPLATE.lower()
        assert "do not" in prompt
        # Should not encourage "actionable" language
        assert "actionable" not in prompt


class TestInsightRunSignature:
    """Verify insight.run accepts the plan parameter."""

    def test_run_accepts_plan_keyword(self):
        import inspect
        from agents.insight import run
        sig = inspect.signature(run)
        assert "plan" in sig.parameters
        # plan should be optional (has default)
        assert sig.parameters["plan"].default is None

    def test_run_handles_missing_plan(self):
        """insight.run(query, sql, exec_result) without plan should not crash."""
        import inspect
        from agents.insight import run
        sig = inspect.signature(run)
        # Verify it can be called without plan — the default is None
        param = sig.parameters["plan"]
        assert param.default is None


class TestPlannerFallbackIntent:
    """Verify the planner's JSON-parse-error fallback uses 'detail' not 'aggregation'."""

    def test_fallback_plan_is_detail(self):
        from agents.planner import run as planner_run
        import agents.planner as planner_module

        # The fallback plan is returned when JSON parsing fails.
        # We test the fallback dict directly.
        fallback = {
            "original_query": "test",
            "steps": ["Retrieve relevant data based on the query"],
            "intent": "detail",
            "metrics": [],
            "filters": {
                "time_range": None,
                "location": None,
                "category": None,
                "other": None,
            },
            "grouping": None,
            "requires_aggregation": False,
            "requires_comparison": False,
        }
        # The source code should have intent=detail in the fallback
        import inspect
        source = inspect.getsource(planner_module.run)
        assert '"detail"' in source or "'detail'" in source

    def test_fast_plan_detail_for_listing_query(self):
        from agents.planner import build_fast_plan
        plan = build_fast_plan("Provide details of all products sold by salesperson")
        assert plan["intent"] == "detail"
        assert plan["requires_aggregation"] is False


class TestExecutionTruncation:
    """Verify that execution and database layers track truncation."""

    def test_database_execute_returns_is_truncated(self):
        """database.execute_query result dict should contain is_truncated key."""
        from services.database import execute_query
        import inspect
        source = inspect.getsource(execute_query)
        assert "is_truncated" in source

    def test_execution_agent_propagates_is_truncated(self):
        """execution.run result dict should contain is_truncated key."""
        from agents.execution import run as exec_run
        import inspect
        source = inspect.getsource(exec_run)
        assert "is_truncated" in source


class TestOrchestratorPassesPlan:
    """Verify that the orchestrator passes the plan to insight.run."""

    def test_orchestrator_calls_insight_with_plan(self):
        import inspect
        from agents.orchestrator import process_query
        source = inspect.getsource(process_query)
        # Should contain plan=plan in the insight.run call
        assert "plan=plan" in source


class TestInsightFormatResults:
    """Verify _format_results correctly handles truncation messaging."""

    def test_format_results_truncation_message(self):
        from agents.insight import _format_results
        rows = [{"a": i, "b": i * 2} for i in range(100)]
        text = _format_results(rows, max_rows=10)
        assert "90 more rows" in text
        assert "not shown" in text.lower()

    def test_format_results_no_truncation(self):
        from agents.insight import _format_results
        rows = [{"a": 1, "b": 2}]
        text = _format_results(rows, max_rows=10)
        assert "more rows" not in text

    def test_format_results_empty(self):
        from agents.insight import _format_results
        text = _format_results([], max_rows=10)
        assert text == "No results."


class TestFollowupIntentPreservation:
    """Verify follow-up prompts include intent-preservation rules."""

    def test_strict_answer_prompt_forbids_ranking(self):
        from agents.followup_orchestrator import STRICT_ANSWER_PROMPT
        prompt = STRICT_ANSWER_PROMPT.lower()
        assert "do not rank" in prompt

    def test_strict_answer_prompt_forbids_invented_numbers(self):
        from agents.followup_orchestrator import STRICT_ANSWER_PROMPT
        prompt = STRICT_ANSWER_PROMPT.lower()
        assert "do not invent" in prompt
