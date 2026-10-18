"""
Prediction Agent — the adapter between a conversation and the prediction engine.

This module is deliberately thin. It resolves a question into a
``PredictionConfig``, hands that to the engine, and shapes the structured
result for the API. It contains no phrase matching, no keyword tables and no
per-question branches: everything specific to a question lives in the config,
and everything specific to the data lives in the resolvers.

The old path did the opposite — twelve regular expressions in the agent chose
the table, target, task type, horizon, frequency and dimensions from the
question's wording, so any phrasing the patterns missed produced either the
wrong prediction or none. Those functions are kept for backward compatibility
but are no longer on this path.
"""

from __future__ import annotations

import dataclasses
import re
import logging

import pandas as pd
from typing import Any

from prediction import config as cfg
from prediction import engine
from prediction.config import PredictionConfig
from prediction.config_resolver import resolve_config

logger = logging.getLogger(__name__)


def run(
    query: str,
    *,
    table_names: list[str] | None = None,
    inherited_config: dict | None = None,
    task_decision: Any = None,
) -> dict[str, Any]:
    """
    Answer a prediction question.

    Args:
        query: the question, in any phrasing.
        table_names: the active data source's tables, so the prediction stays
            inside the dataset the user is looking at.
        inherited_config: the previous turn's config, for follow-ups.
        task_decision: the task router's verdict. When supplied, its engine
            constrains the prediction type, so routing and execution cannot
            disagree about what kind of prediction this is.

    Returns:
        ``{"result": ..., "insight": ...}`` in the shape the orchestrator and
        the frontend already expect.
    """
    logger.info("[PredictionAgent] %s", query[:120])

    forced_type = None
    if task_decision is not None:
        from agents import task_router
        forced_type = {
            task_router.ENGINE_FORECAST: cfg.FORECASTING,
            task_router.ENGINE_CLASSIFICATION: cfg.CLASSIFICATION,
            task_router.ENGINE_REGRESSION: cfg.REGRESSION,
        }.get(task_decision.engine)

    config = resolve_config(
        query,
        table=(table_names[0] if table_names and len(table_names) == 1 else None),
        scope_tables=table_names,
        inherited=inherited_config,
        force_prediction_type=forced_type,
    )
    if task_decision is not None:
        config.resolved_by["task"] = task_decision.task

    if config.status == cfg.STATUS_NEEDS_CLARIFICATION:
        return _clarification_response(config)

    if not config.is_executable:
        return _error_response(config, "; ".join(config.errors))

    result = engine.execute(config)

    if not result.ok:
        return _error_response(config, "; ".join(result.errors) or result.status,
                               status=result.status, result_obj=result)

    return _success_response(config, result, query)


# ──────────────────────────────────────────────────────────
# Response shaping
# ──────────────────────────────────────────────────────────

def _success_response(config: PredictionConfig, result, query: str) -> dict[str, Any]:
    evidence = build_evidence(config, result)

    from agents import explanation as explanation_layer
    insight = explanation_layer.explain(query, evidence, fallback=evidence)

    # The engine computed figures; an answer containing none is not describing
    # them. Rather than let the model report having nothing, fall back to the
    # deterministic evidence, which is always complete.
    # The evidence states plain numbers; a currency symbol on a count of boxes
    # or customers is the wording layer inventing a unit.
    if not _is_monetary(config.target):
        insight = re.sub(r"\$\s?(?=\d)", "", insight)

    if _has_digits(evidence) and not _has_digits(insight):
        logger.warning(
            "[PredictionAgent] Generated answer carried no figures; "
            "returning the deterministic evidence instead."
        )
        insight = evidence

    # Falling back to the evidence is safe but reads like a log. When it holds
    # computed answer lines, show those as sentences instead.
    if insight == evidence:
        insight = _readable(evidence) or evidence

    # The computed answer to "which month ...?" must lead the reply even when
    # the wording layer leaves it out.
    # "Which month/quarter ...?" is answered entirely by computed sentences.
    # The wording layer was seen re-deciding the answer ("Q1 2006 is the
    # lowest") against the engine's ranking (Q2 2005); a ranking question has
    # nothing for it to add that could not also contradict the result.
    if getattr(result, "period_ranking", None) and result.period_ranking.get("ranking"):
        insight = _readable(evidence) or insight

    # "Will the top 5 stay the same?" needs the *why* as well as the yes/no.
    # The reasons are computed, so they are attached as written rather than
    # left to the wording layer, which tends to drop them.
    if result.comparison and evidence != insight:
        why = _section(evidence, "WHY IT CHANGES")
        if why:
            insight = insight.rstrip() + "\n\n**Why the ranking changes:**\n" + "\n".join(
                f"- {line}" for line in why)

    prediction = dataclasses.asdict(result)
    # Keys the existing prediction UI reads directly. They are projections of
    # the structured result, not separate state — the frontend renders them,
    # it never recomputes them.
    prediction["target_column"] = config.target
    prediction["dimensions"] = list(config.group_dimensions)
    prediction["horizon"] = config.horizon
    prediction["table_name"] = config.table
    prediction["ranking_metric"] = config.ranking_metric
    prediction["model_accuracy"] = (result.model_metadata or {}).get("accuracy", 0.0)

    payload = {
        "pipeline_type": "PREDICTIVE",
        "prediction": prediction,
        "config": config.to_dict(),
        "visualization": _visualization_metadata(config, result),
        "columns": ["metric", "value"],
        "rows": _summary_rows(config, result),
        "row_count": 0,
        "status": result.status,
        "warnings": result.warnings,
        # Engine-computed facts, kept so follow-ups ("how reliable is this?")
        # are answered from them rather than from a fresh LLM guess.
        "evidence": evidence,
    }
    payload["row_count"] = len(payload["rows"])
    return {"result": payload, "insight": insight, "config": config.to_dict()}


def _clarification_response(config: PredictionConfig) -> dict[str, Any]:
    clarification = config.clarification or {}
    options = clarification.get("options", [])
    question = clarification.get("question", "Which measure would you like me to predict?")
    listed = ", ".join(options[:-1]) + (f", or {options[-1]}" if len(options) > 1 else "")
    return {
        "result": {
            "pipeline_type": "PREDICTIVE",
            "status": cfg.STATUS_NEEDS_CLARIFICATION,
            "clarification": clarification,
            "config": config.to_dict(),
            "columns": ["metric", "value"], "rows": [], "row_count": 0,
        },
        "insight": f"{question} This dataset has {listed}.",
        "config": config.to_dict(),
    }


def _error_response(config, message, status=cfg.STATUS_INVALID_CONFIG, result_obj=None):
    payload = {
        "pipeline_type": "PREDICTIVE",
        "status": status,
        "error": message,
        "config": config.to_dict() if config else {},
        "columns": ["metric", "value"], "rows": [], "row_count": 0,
    }
    if result_obj is not None:
        payload["prediction"] = dataclasses.asdict(result_obj)
        payload["warnings"] = result_obj.warnings
    return {
        "result": payload,
        "insight": f"I couldn't produce that prediction. {message}",
        "config": config.to_dict() if config else {},
    }


def _summary_rows(config: PredictionConfig, result) -> list[dict[str, str]]:
    """A small metric/value table, derived entirely from the structured result."""
    rows: list[dict[str, str]] = []
    if result.ranking_rows:
        metric = "Growth" if config.ranking_metric == "growth" else f"Predicted {config.target}"
        suffix = "%" if config.ranking_metric == "growth" else ""
        for row in result.ranking_rows[:10]:
            if row.get("value") is None:
                continue
            rows.append({"metric": str(row.get("group")), "value": f"{row['value']:,.2f}{suffix}"})
        if rows:
            rows.insert(0, {"metric": "Ranked by", "value": metric})
    elif result.forecast_rows:
        # Grouped rows need the group in the label, or "2022-04-30: 600,084"
        # appears once per country with no way to tell which is which.
        limit = 60 if config.is_grouped else 10
        for row in result.forecast_rows[:limit]:
            if row.get("value") is not None:
                period = str(row.get("period"))[:10]
                label = f"{row.get('group')} · {period}" if config.is_grouped and row.get("group") else period
                rows.append({"metric": label, "value": f"{row['value']:,.2f}"})
    elif result.row_predictions:
        for row in result.row_predictions[:10]:
            value = row.get("probability")
            prediction = row.get("prediction")
            if value is not None:
                shown = f"{value:.1%}"
            elif isinstance(prediction, (int, float)):
                shown = f"{prediction:,.2f}"
            else:
                shown = f"{prediction}"
            rows.append({"metric": str(row.get("customer_id")), "value": shown})
    return rows


def _series_validation(result, group) -> dict[str, Any]:
    """
    How one series' model was chosen, for display beside that series.

    A grouped chart draws many point forecasts side by side. Each came from its
    own backtest, and several are flat because a flat model won it; without its
    validation result next to it, a flat line reads as a claim of certainty.
    """
    per_group = (result.model_metadata or {}).get("per_group") or {}
    entry = per_group.get(group) or per_group.get(str(group)) or {}
    score = entry.get("selected_score")
    beats = entry.get("beats_naive")
    status, sentence = reliability_status(score, beats)
    return {
        "model": entry.get("selected_model_label"),
        "mase": round(float(score), 3) if score is not None else None,
        "beats_naive": beats,
        "reliability": status,
        "reliability_note": sentence,
        "reliable": status == "validated",
        # Why this series' forecast line is flat / sloped / seasonal.
        "shape": entry.get("shape"),
        "explanation": entry.get("shape_explanation") or [],
        "holdout": entry.get("holdout") or [],
    }


def _visualization_metadata(config: PredictionConfig, result) -> dict[str, Any]:
    """
    Translate the engine's semantic view list into renderable chart specs.

    The engine says *what the data is*; this maps that onto the chart types the
    frontend already implements. No chart is tied to a question — only to the
    shape of the result.
    """
    views = result.visualization.get("views", [])
    charts: list[dict[str, Any]] = []
    label = " and ".join(config.group_dimensions) if config.group_dimensions else "total"

    if "time_series" in views:
        meta = result.model_metadata or {}
        status, sentence = reliability_status(meta.get("selected_score"), meta.get("beats_naive"))
        charts.append({
            "type": "time_series_forecast",
            "title": f"Forecast: {config.target}",
            "model": meta.get("selected_model_label"),
            "mase": meta.get("selected_score"),
            "reliability": status,
            "reliability_note": sentence,
            "shape": meta.get("shape"),
            "explanation": meta.get("shape_explanation") or [],
            "holdout": meta.get("holdout") or [],
            "data": {
                "historical": [{"date": r["period"], "value": r["value"]}
                               for r in result.historical_rows],
                "forecast": [{"date": r["period"], "value": r["value"],
                              "lower": r.get("lower"), "upper": r.get("upper")}
                             for r in result.forecast_rows],
            },
        })

    if "grouped_time_series" in views:
        by_group: dict[Any, dict[str, list]] = {}
        for row in result.historical_rows:
            by_group.setdefault(row["group"], {"historical": [], "forecast": [],
                                               "group_values": row.get("group_values", {})})
            by_group[row["group"]]["historical"].append(
                {"date": row["period"], "value": row["value"]})
        for row in result.forecast_rows:
            by_group.setdefault(row["group"], {"historical": [], "forecast": [],
                                               "group_values": row.get("group_values", {})})
            by_group[row["group"]]["forecast"].append(
                {"date": row["period"], "value": row["value"],
                 "lower": row.get("lower"), "upper": row.get("upper")})

        order = [r["group"] for r in result.ranking_rows] or list(by_group)
        ordered = [g for g in order if g in by_group] + \
                  [g for g in by_group if g not in order]
        # Every forecast series is sent; the chart decides how many to draw.
        shown = [g for g in ordered if by_group[g]["forecast"]]

        # The series the question is about: for "will the top 5 stay the
        # same", the current top 5 plus anything entering the forecast top 5;
        # for a plain "top 5", the forecast top 5. The chart draws these by
        # default and keeps the rest one click away.
        focus_groups: list[str] = []
        if result.comparison:
            comp = result.comparison
            focus_groups = list(dict.fromkeys(
                [e["group"] for e in comp["current_top"]] + [e["group"] for e in comp["future_top"]]))
        elif config.top_n:
            focus_groups = [str(r["group"]) for r in result.ranking_rows[: config.top_n]]

        charts.append({
            "type": "grouped_time_series_forecast",
            "title": f"Forecast {config.target} by {label}",
            "focus_groups": focus_groups,
            # "comparison": current top N + entrants; "top": forecast top N only.
            "focus_kind": "comparison" if result.comparison else ("top" if focus_groups else None),
            "top_n": config.top_n,
            "dimension": "group",
            "dimensions": list(config.group_dimensions),
            "data": [{"group": str(g), "group_dict": by_group[g]["group_values"],
                      "historical": by_group[g]["historical"][-50:],
                      "forecast": by_group[g]["forecast"],
                      **_series_validation(result, g)} for g in shown],
            "shown": len(shown),
            "total": len([g for g in by_group if by_group[g]["forecast"]]),
            "truncated": len([g for g in by_group if by_group[g]["forecast"]]) > len(shown),
            "note": (
                f"Showing the top {len(shown)} of "
                f"{len([g for g in by_group if by_group[g]['forecast']])} {label} "
                "combinations; all of them were forecast and ranked."
                if len([g for g in by_group if by_group[g]["forecast"]]) > len(shown) else ""
            ),
        })

    if "value_ranking" in views or "growth_ranking" in views:
        is_growth = "growth_ranking" in views
        data = [{"group": str(r["group"]), "group_dict": r.get("group_values", {}),
                 "value": round(float(r["value"]), 2), "color": "#6366f1"}
                for r in result.ranking_rows if r.get("value") is not None]
        notes = []
        if len(data) > 20:
            notes.append(f"Top 20 of {len(data)} ranked combinations.")
        if result.excluded_groups:
            notes.append(f"{len(result.excluded_groups)} group(s) had too little history.")
        charts.append({
            "type": "value_ranking",
            "title": (f"Expected growth % by {label}" if is_growth
                      else f"Predicted {config.target} by {label}"),
            "dimension": "group",
            "dimensions": list(config.group_dimensions),
            "metric": "growth_pct" if is_growth else config.target,
            "sort": "descending",
            "data": data[:20],
            "shown": min(20, len(data)), "total": len(data),
            "excluded": len(result.excluded_groups),
            "truncated": len(data) > 20,
            "note": " ".join(notes),
        })

    return {
        "mode": "forecast" if config.prediction_type == cfg.FORECASTING else "batch",
        "problem_type": config.prediction_type,
        "semantics": result.visualization,
        "charts": charts,
    }


# ──────────────────────────────────────────────────────────
# Evidence for the explanation layer
# ──────────────────────────────────────────────────────────

#: Evidence lines that are already complete sentences for a reader.
_READABLE_KEYS = ("ANSWER", "RUNNER-UP", "CERTAINTY", "RELIABILITY")


def _readable(evidence: str) -> str:
    """The sentence-like evidence lines, without their labels; '' if none."""
    out = []
    for line in evidence.splitlines():
        key, _, rest = line.partition(": ")
        if key in _READABLE_KEYS and rest:
            text = rest[:1].upper() + rest[1:]
            if key == "ANSWER":
                text = f"**{text}**"
            elif key == "RUNNER-UP":
                text = f"Runner-up: {rest}"
            out.append(text)
        elif key == "MODEL" and rest:
            out.append("Model: " + re.sub(r";\s*beats the naive baseline: \w+\.?", ".", rest))
    return "\n\n".join(out) if any(l for l in out) and evidence.count("ANSWER: ") else ""


def _period_label(period: str, frequency: str) -> str:
    """'2019-12-31 00:00:00' -> 'December 2019' / 'Q4 2019' / 'week of 2019-12-23'."""
    try:
        ts = pd.Timestamp(period)
    except Exception:
        return str(period)
    f = (frequency or "").rstrip("s")
    if f == "month":
        return ts.strftime("%B %Y")
    if f == "quarter":
        return f"Q{ts.quarter} {ts.year}"
    if f == "year":
        return str(ts.year)
    if f == "week":
        return f"week ending {ts.date()}"
    return str(ts.date())


def _period_ranking_evidence(pr: dict, config: PredictionConfig) -> list[str]:
    """'Which month will be highest?' - the answer first, then the full ranking."""
    rows, unit = pr["ranking"], (config.time_frequency or "period").rstrip("s")
    top = rows[0]
    label = _period_label(top["period"], config.time_frequency)
    what = f"total {config.target}" if pr.get("grouped") else config.target
    lines = [f"ANSWER: The {pr['direction']} forecast {unit} is {label}, with {what} of "
             f"{top['value']:,.2f}"
             + (f" (95% range {top['lower']:,.2f} to {top['upper']:,.2f})."
                if top.get("lower") is not None else ".")]
    if len(rows) >= 2:
        runner = rows[1]
        lines.append(f"RUNNER-UP: {_period_label(runner['period'], config.time_frequency)} "
                     f"at {runner['value']:,.2f}.")
        if pr.get("lead_within_uncertainty"):
            lines.append(
                f"CERTAINTY: {label}'s lead over the runner-up ({pr['lead']:,.2f}) is smaller "
                f"than its own forecast uncertainty, so the top two could swap; treat the "
                f"order as likely, not certain.")
        elif "lead" in pr:
            lines.append(
                f"CERTAINTY: {label}'s lead over the runner-up ({pr['lead']:,.2f}) is larger "
                f"than its forecast uncertainty, so it is a clear {pr['direction']}.")
    lines.append(f"ALL FORECAST {unit.upper()}S, {pr['direction']} first:")
    for r in rows:
        lines.append(f"  {r['rank']}. {_period_label(r['period'], config.time_frequency)}: "
                     f"{r['value']:,.2f}")
    return lines


def _section(evidence: str, header: str) -> list[str]:
    """The indented lines under one evidence header."""
    lines, inside = [], False
    for line in evidence.splitlines():
        if line.startswith(header):
            inside = True
            continue
        if inside:
            if line.startswith("  "):
                lines.append(line.strip())
            else:
                break
    return lines


def _comparison_evidence(comparison: dict, config: PredictionConfig) -> list[str]:
    """
    Current top-N vs forecast top-N: the answer, the like-for-like numbers,
    and a measured reason for each entity that moves.

    The current ranking is over the whole history and the forecast over the
    horizon, so their totals are never compared directly; the recent window of
    the same length is the like-for-like baseline.
    """
    n = comparison["top_n"]
    unit = (config.time_frequency or "period").rstrip("s")
    h = config.horizon or 0
    details = comparison.get("details") or {}
    cur = {e["group"]: e["rank"] for e in comparison["current_top"]}
    fut = {e["group"]: e["rank"] for e in comparison["future_top"]}
    lines: list[str] = []

    if comparison["unchanged_order"]:
        lines.append(f"ANSWER: Yes - the same {n} stay on top, in the same order.")
    elif comparison["unchanged_set"]:
        lines.append(f"ANSWER: Mostly - the same {n} stay on top, but their order changes.")
    else:
        lines.append(
            f"ANSWER: No - the top {n} changes. "
            + (f"Leaving: {', '.join(comparison['left'])}. " if comparison["left"] else "")
            + (f"Entering: {', '.join(comparison['entered'])}." if comparison["entered"] else ""))

    any_detail = next(iter(details.values()), None)
    span = f"all {any_detail['periods_all']} {unit}s" if any_detail else "the whole history"
    lines.append(f"CURRENT TOP {n} (total over {span}, observed):")
    for e in comparison["current_top"]:
        lines.append(f"  {e['rank']}. {e['group']}: {e['value']:,.2f}")
    lines.append(f"FORECAST TOP {n} (total over the next {h} {unit}s):")
    for e in comparison["future_top"]:
        lines.append(f"  {e['rank']}. {e['group']}: {e['value']:,.2f}")

    if details:
        lines.append(
            f"LIKE-FOR-LIKE (the totals above cover different lengths of time, so compare "
            f"the last {h} {unit}s actual with the next {h} {unit}s forecast):")
        order = [e["group"] for e in comparison["future_top"]] + \
                [g for g in (e["group"] for e in comparison["current_top"]) if g not in fut]
        for g in order:
            d = details.get(g)
            if not d or d["forecast_total"] is None:
                continue
            lines.append(f"  {g}: last {d['recent_periods']} {unit}s actual {d['recent_total']:,.0f} "
                         f"-> next {h} forecast {d['forecast_total']:,.0f}")

        lines.append(
            f"WHY IT CHANGES (the current ranking sums every {unit}; the forecast is built "
            f"from each one's own history, weighted toward its latest {unit}s):")
        for g in order:
            d = details.get(g)
            before, after = cur.get(g), fut.get(g)
            if not d or before == after or d["avg_forecast"] is None:
                continue
            pos = (f"rank {before} -> {after}" if before and after
                   else f"rank {before} -> outside top {n}" if before
                   else f"outside top {n} -> rank {after}")
            lines.append(f"  {g} ({pos}): {_why_moved(d, unit)}")
    return lines


#: What each model does with the history, in words that are always true of it.
_MODEL_RULE = {
    "moving_average": "the average of its last 3 {unit}s",
    "naive": "a repeat of its last {unit}",
    "simple_exp_smoothing": "a weighted average of all its {unit}s, weighted toward the recent ones",
    "seasonal_naive": "a repeat of the same {unit}s one cycle earlier",
    "drift": "its last {unit} plus its average change per {unit}",
    "holt_linear": "its recent level continued along its recent trend",
    "damped_holt": "its recent level continued along a flattening trend",
    "level_combination": "the average of its long-run mean, SES, its last 3 {unit}s' "
                         "average and its last {unit}",
}


def _why_moved(d: dict, unit: str) -> str:
    """
    One factual sentence: where the forecast sits against the usual level,
    the latest actual values, and what the chosen model does with them.

    It describes the computation rather than characterising the months, so it
    can never claim "its latest months were low" when one of them was not.
    """
    usual, fc = d["avg_all"], d["avg_forecast"]
    latest = ", ".join(f"{p} {v:,.0f}" for p, v in d.get("last_periods", []))
    if usual and fc < usual * 0.95:
        level = f"forecast at {fc:,.0f} per {unit}, below its usual {usual:,.0f}"
    elif usual and fc > usual * 1.05:
        level = f"forecast at {fc:,.0f} per {unit}, above its usual {usual:,.0f}"
    else:
        level = (f"forecast at about its usual level ({fc:,.0f} per {unit}), so it moves "
                 f"only because others rose or fell around it")
    rule = _MODEL_RULE.get(d.get("model_key") or "")
    how = (f"; its model ({d.get('model')}) forecasts {rule.format(unit=unit)}"
           if rule else (f"; model: {d.get('model')}" if d.get("model") else ""))
    note = (f" ({', '.join(p[:7] for p in d['spikes_adjusted'])} treated as a one-off spike)"
            if d.get("spikes_adjusted") else "")
    return f"{level}. Latest {unit}s: {latest}{how}{note}."


#: How many series the evidence lists individually before summarising the rest.
MAX_GROUPS_IN_EVIDENCE = 10


def _totals_by_group(result) -> list[tuple[str, float]]:
    """
    Each series' forecast total over the horizon, largest first.

    Computed from ``forecast_rows`` rather than the aggregated view, because
    that view holds whatever the ranking metric was — a growth percentage when
    growth was requested — and this block is labelled as totals.
    """
    totals: dict[str, float] = {}
    for row in result.forecast_rows:
        if row.get("value") is None:
            continue
        group = str(row.get("group"))
        totals[group] = totals.get(group, 0.0) + float(row["value"])
    return sorted(totals.items(), key=lambda kv: -kv[1])


#: Name fragments that mark a column as money. Same rule the chart uses to
#: decide whether to prefix a currency symbol.
_MONETARY_WORDS = ("amount", "revenue", "sales", "price", "cost", "salary",
                   "balance", "income", "profit", "spend", "value")


def _is_monetary(column: str | None) -> bool:
    name = (column or "").lower()
    return any(w in name for w in _MONETARY_WORDS)


def _has_digits(text: str) -> bool:
    """Whether a piece of text states any figure at all."""
    return bool(re.search(r"\d", text or ""))


def reliability_status(score: float | None, beats_naive: bool | None) -> tuple[str, str]:
    """
    Classify a forecast's validation result, because "best available" is not
    "reliable".

    Selection always returns the lowest validation error among the candidates,
    even when every candidate is poor. Four outcomes are distinguishable and
    each gets a statement that is literally true of it:

    - ``not_validated``: no backtest was possible; a labelled fallback.
    - ``baseline``: no candidate beat repeating the last value on held-out
      periods (this includes the naive model winning outright).
    - ``validated``: beat the naive baseline, and MASE is below 1.
    - ``weak``: beat the naive baseline, but MASE is 1 or more, so it is still
      less accurate than a one-step naive forecast measured in-sample.

    Returns (status, sentence).
    """
    if score is None:
        return ("not_validated",
                "not validated — no chronological backtest was possible, so this "
                "is a fallback rather than a tested forecast.")
    if beats_naive is False:
        return ("baseline",
                f"baseline only — no model beat simply repeating the last observed "
                f"value on held-out periods (MASE {score:.2f}), so the forecast "
                f"carries no information beyond that.")
    if score < 1:
        return ("validated",
                f"validated — MASE {score:.2f} is below 1 and the model beat the "
                f"naive baseline on held-out periods.")
    return ("weak",
            f"NOT reliable — the model beat the naive baseline, but MASE "
            f"{score:.2f} is at or above 1, so its error is still larger than a "
            f"one-step naive forecast's. Treat the figures as indicative only.")


def _reliability_line(model: dict) -> str:
    """The reliability statement for a single-series forecast's evidence."""
    _, sentence = reliability_status(model.get("selected_score"), model.get("beats_naive"))
    return f"RELIABILITY: {sentence}"


def build_evidence(config: PredictionConfig, result) -> str:
    """
    Deterministic evidence describing the result.

    This is everything the explanation layer is permitted to say. Every figure
    here was computed by the engine; the language model only phrases them, and
    the explanation layer rejects any number or cause it adds.
    """
    lines: list[str] = []
    label = " and ".join(config.group_dimensions) if config.group_dimensions else None

    if config.prediction_type == cfg.FORECASTING:
        lines.append(
            f"FORECAST: {config.target} for {config.horizon} {config.time_frequency} "
            f"after {str(config.history_end)[:10]}"
            + (f", by {label}." if label else ".")
        )
        if config.forecast_start and config.forecast_end:
            lines.append(
                f"PERIODS COVERED: {str(config.forecast_start)[:10]} to "
                f"{str(config.forecast_end)[:10]}."
            )

    period_rank = getattr(result, "period_ranking", None) or {}
    if period_rank.get("ranking"):
        lines.extend(_period_ranking_evidence(period_rank, config))

    # A ranking of *groups* only means something when there are groups; an
    # ungrouped forecast "ranked" itself as "None".
    if result.ranking_rows and (config.is_grouped or not period_rank):
        is_growth = config.ranking_metric == "growth"
        lines.append("RANKED GROWTH:" if is_growth else "RANKED FORECAST TOTALS:")
        for row in result.ranking_rows[:5]:
            if row.get("value") is None:
                continue
            lines.append(
                f"  {row.get('rank', '?')}. {row['group']}: {row['value']:,.2f}"
                + ("%" if is_growth else "")
            )
        ranked = len([r for r in result.ranking_rows if r.get("value") is not None])
        lines.append(f"({ranked} entities were forecast and ranked.)")
    elif result.forecast_rows:
        # A forecast that was not ranked still has to carry its numbers.
        # Without this, a grouped forecast with no ranking operation produced
        # evidence of headings alone, and the answer honestly reported having
        # no figures to share.
        if config.is_grouped:
            totals = _totals_by_group(result)
            lines.append(f"FORECAST TOTALS BY {(label or 'group').upper()} "
                         f"over the horizon:")
            for group, value in totals[:MAX_GROUPS_IN_EVIDENCE]:
                lines.append(f"  {group}: {value:,.2f}")
            if len(totals) > MAX_GROUPS_IN_EVIDENCE:
                lines.append(f"  (+{len(totals) - MAX_GROUPS_IN_EVIDENCE} more series)")
            combined = sum(v for _, v in totals)
            lines.append(
                f"({len(totals)} series forecast, largest first; combined total "
                f"{combined:,.2f}.)"
            )
        else:
            total = sum(r["value"] for r in result.forecast_rows
                        if r.get("value") is not None)
            lines.append(f"FORECAST TOTAL over the horizon: {total:,.2f}")
            first = next((r for r in result.forecast_rows
                          if r.get("value") is not None), None)
            last = next((r for r in reversed(result.forecast_rows)
                         if r.get("value") is not None), None)
            if first and last:
                lines.append(
                    f"FIRST PERIOD {str(first['period'])[:10]}: {first['value']:,.2f}")
                lines.append(
                    f"LAST PERIOD {str(last['period'])[:10]}: {last['value']:,.2f}")
    elif result.forecast_rows:
        # Grouped forecast with no ranking requested: without per-group totals
        # the explanation has no figures and can only say it has none.
        totals: dict[str, float] = {}
        for r in result.forecast_rows:
            if r.get("value") is not None:
                totals[r["group"]] = totals.get(r["group"], 0.0) + r["value"]
        lines.append(f"FORECAST TOTAL PER {(label or 'GROUP').upper()} over the horizon (highest first):")
        for group, total in sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:10]:
            lines.append(f"  {group}: {total:,.2f}")
        if len(totals) > 10:
            lines.append(f"({len(totals)} groups were forecast; the 10 largest are listed.)")

    if result.growth_rows:
        top = next((g for g in result.growth_rows if g["growth_pct"] is not None), None)
        if top:
            lines.append(
                f"GROWTH DETAIL for {top['group']}: baseline "
                f"{top['baseline_total']:,.2f} over {top['baseline_periods']} periods, "
                f"forecast {top['forecast_total']:,.2f}, change "
                f"{top['absolute_change']:,.2f} ({top['growth_pct']:,.2f}%)."
            )

    if result.comparison:
        lines.extend(_comparison_evidence(result.comparison, config))

    if result.row_predictions:
        lines.append(f"PREDICTED ROWS: {len(result.row_predictions)}.")
        for row in result.row_predictions[:10]:
            score = row.get("probability")
            pred = row.get("prediction")
            if score is not None:
                shown = f"{score * 100:.1f}% probability"
            elif isinstance(pred, (int, float)):
                shown = f"predicted {pred:,.2f}"
            else:
                shown = f"predicted {pred}"
            lines.append(f"  {row.get('customer_id')}: {shown}")
        accuracy = result.model_metadata.get("accuracy")
        if accuracy is not None:
            # For regression this value is R², not accuracy — label it as such
            # so the explanation doesn't call a goodness-of-fit score "accuracy".
            if result.model_metadata.get("problem_type") == "regression":
                lines.append(f"MODEL R² (share of variance explained) on held-out data: {accuracy}.")
            else:
                lines.append(f"MODEL ACCURACY on held-out data: {accuracy}.")

    model = result.model_metadata or {}
    if model.get("selected_model_label"):
        line = f"MODEL: {model['selected_model_label']}"
        if model.get("selection_method"):
            line += f" (chosen by {model['selection_method']})"
        if model.get("beats_naive") is not None:
            line += f"; beats the naive baseline: {model['beats_naive']}"
        lines.append(line + ".")
        # MASE and the naive baseline belong to time-series backtesting; a
        # regression or classification model is judged by its held-out
        # metrics, already stated above.
        if config.prediction_type == cfg.FORECASTING:
            lines.append(_reliability_line(model))
    elif model.get("per_group"):
        chosen = {m.get("selected_model_label") for m in model["per_group"].values()}
        lines.append(
            f"MODELS: selected per series by chronological validation "
            f"({', '.join(sorted(c for c in chosen if c))})."
        )

    if result.excluded_groups:
        lines.append(
            f"NOT FORECAST: {len(result.excluded_groups)} entit(ies) had too little "
            "history; they are excluded from the ranking rather than counted as zero."
        )

    for warning in (result.warnings or [])[:4]:
        lines.append(f"CAVEAT: {warning}")

    return "\n".join(lines)
