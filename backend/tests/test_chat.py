"""Tests for the conversational follow-up chat agent."""

from agents import chat


def test_chat_run_includes_result_context_in_prompt(monkeypatch, temp_database):
    captured = {}

    def fake_call_llm(prompt, expect_json=False):
        captured["prompt"] = prompt
        return "You could promote your top product more aggressively."

    monkeypatch.setattr(chat, "call_llm", fake_call_llm)

    reply = chat.run(
        message="How can I improve my sales?",
        context={
            "query": "What were my top products?",
            "sql": "SELECT product, revenue FROM sales ORDER BY revenue DESC LIMIT 3;",
            "result": {
                "columns": ["product", "revenue"],
                "rows": [{"product": "Widget", "revenue": 500}, {"product": "Gadget", "revenue": 300}],
                "row_count": 2,
            },
            "insight": "Widget is your best seller.",
        },
        history=[],
    )

    assert reply == "You could promote your top product more aggressively."
    prompt = captured["prompt"]
    assert "What were my top products?" in prompt
    assert "Widget" in prompt
    assert "How can I improve my sales?" in prompt


def test_chat_run_includes_prior_history(monkeypatch, temp_database):
    captured = {}

    def fake_call_llm(prompt, expect_json=False):
        captured["prompt"] = prompt
        return "Sure, here's more detail."

    monkeypatch.setattr(chat, "call_llm", fake_call_llm)

    chat.run(
        message="Can you say more?",
        context={
            "query": "What were my top products?",
            "sql": None,
            "result": {"columns": ["product"], "rows": [{"product": "Widget"}], "row_count": 1},
            "insight": None,
        },
        history=[
            {"role": "user", "content": "How can I improve my sales?"},
            {"role": "assistant", "content": "Focus on your top seller."},
        ],
    )

    prompt = captured["prompt"]
    assert "How can I improve my sales?" in prompt
    assert "Focus on your top seller." in prompt


def test_chat_run_handles_empty_results(monkeypatch, temp_database):
    monkeypatch.setattr(chat, "call_llm", lambda prompt, expect_json=False: "No data to analyze yet.")

    reply = chat.run(
        message="What should I do?",
        context={"query": "show nothing", "sql": None, "result": {"columns": [], "rows": [], "row_count": 0}, "insight": None},
        history=[],
    )

    assert reply == "No data to analyze yet."
