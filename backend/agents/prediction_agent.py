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
        charts.append({
            "type": "time_series_forecast",
            "title": f"Forecast: {config.target}",
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

        charts.append({
            "type": "grouped_time_series_forecast",
            "title": f"Forecast {config.target} by {label}",
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

    if result.ranking_rows:
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
        comparison = result.comparison
        lines.append(f"CURRENT TOP {comparison['top_n']} (observed):")
        for entry in comparison["current_top"]:
            lines.append(f"  {entry['rank']}. {entry['group']}: {entry['value']:,.2f}")
        lines.append(f"FORECAST TOP {comparison['top_n']}:")
        for entry in comparison["future_top"]:
            lines.append(f"  {entry['rank']}. {entry['group']}: {entry['value']:,.2f}")
        if comparison["unchanged_order"]:
            lines.append("COMPARISON: the same entities, in the same order.")
        elif comparison["unchanged_set"]:
            lines.append("COMPARISON: the same entities, in a different order.")
        else:
            if comparison["left"]:
                lines.append(f"COMPARISON: leaving the top {comparison['top_n']}: "
                             f"{', '.join(comparison['left'])}.")
            if comparison["entered"]:
                lines.append(f"COMPARISON: entering the top {comparison['top_n']}: "
                             f"{', '.join(comparison['entered'])}.")

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
