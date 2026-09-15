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
        for row in result.forecast_rows[:10]:
            if row.get("value") is not None:
                rows.append({"metric": str(row.get("period"))[:10],
                             "value": f"{row['value']:,.2f}"})
    elif result.row_predictions:
        for row in result.row_predictions[:10]:
            value = row.get("probability")
            rows.append({
                "metric": str(row.get("customer_id")),
                "value": f"{value:.1%}" if value is not None else f"{row.get('prediction')}",
            })
    return rows


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
        shown = [g for g in ordered if by_group[g]["forecast"]][:12]

        charts.append({
            "type": "grouped_time_series_forecast",
            "title": f"Forecast {config.target} by {label}",
            "dimension": "group",
            "dimensions": list(config.group_dimensions),
            "data": [{"group": str(g), "group_dict": by_group[g]["group_values"],
                      "historical": by_group[g]["historical"][-50:],
                      "forecast": by_group[g]["forecast"]} for g in shown],
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
    elif result.forecast_rows and not config.is_grouped:
        total = sum(r["value"] for r in result.forecast_rows if r.get("value") is not None)
        lines.append(f"FORECAST TOTAL over the horizon: {total:,.2f}")
        first = next((r for r in result.forecast_rows if r.get("value") is not None), None)
        last = next((r for r in reversed(result.forecast_rows)
                     if r.get("value") is not None), None)
        if first and last:
            lines.append(f"FIRST PERIOD {str(first['period'])[:10]}: {first['value']:,.2f}")
            lines.append(f"LAST PERIOD {str(last['period'])[:10]}: {last['value']:,.2f}")

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
        accuracy = result.model_metadata.get("accuracy")
        if accuracy is not None:
            lines.append(f"MODEL ACCURACY on held-out data: {accuracy}.")

    model = result.model_metadata or {}
    if model.get("selected_model_label"):
        line = f"MODEL: {model['selected_model_label']}"
        if model.get("selection_method"):
            line += f" (chosen by {model['selection_method']})"
        if model.get("beats_naive") is not None:
            line += f"; beats the naive baseline: {model['beats_naive']}"
        lines.append(line + ".")
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
