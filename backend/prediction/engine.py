"""
Prediction Package — Generic Execution Engine

Executes a ``PredictionConfig`` and returns a ``PredictionResult``. It has no
access to the user's wording: every decision it makes comes from the config,
so the same code answers a question about countries and revenue, salespeople
and units, or stores and footfall, without knowing which it is doing.

Structure:

    execute(config)
        ├─ forecasting  ─ ungrouped or per group
        ├─ regression   ─ per row
        └─ classification ─ per row
        then, as the config asks:
        ├─ rank()            ordering over the forecast, never over history
        ├─ growth()          forecast vs a like-for-like baseline
        ├─ compare()         current top-N vs forecast top-N
        └─ top_n()           a view, taken after everything was forecast

Ranking is applied *after* every eligible entity has been forecast, never
before. Ranking first and assuming the order persists cannot surface an entity
that overtakes from below, which is usually the point of the question.
"""

from __future__ import annotations

import dataclasses
import logging
import time
from typing import Any

import pandas as pd

from prediction import config as cfg
from prediction.config import PredictionConfig

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────
# Result
# ──────────────────────────────────────────────────────────

@dataclasses.dataclass
class PredictionResult:
    """
    Everything a caller needs to answer, chart, follow up on, or audit a
    prediction. Derived views (ranking, growth, comparison) are computed from
    ``forecast_rows``, which stays the source of truth.
    """
    config: dict[str, Any] = dataclasses.field(default_factory=dict)
    status: str = cfg.STATUS_OK

    dataset_context: dict[str, Any] = dataclasses.field(default_factory=dict)
    historical_rows: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    forecast_rows: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    aggregated_rows: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    ranking_rows: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    #: A view over `ranking_rows` when a top-N was requested. The full ranking
    #: is always retained above it.
    top_rows: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    growth_rows: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    comparison: dict[str, Any] | None = None
    row_predictions: list[dict[str, Any]] = dataclasses.field(default_factory=list)

    model_metadata: dict[str, Any] = dataclasses.field(default_factory=dict)
    validation_metrics: dict[str, Any] = dataclasses.field(default_factory=dict)
    series_diagnostics: dict[str, Any] = dataclasses.field(default_factory=dict)
    excluded_groups: list[dict[str, Any]] = dataclasses.field(default_factory=list)

    #: The level these rows are reported at, e.g. "country". Carried on the
    #: result so a caller can assert it matches what was asked rather than
    #: inferring it from whatever columns happen to be in the rows.
    result_granularity: str = "total"

    visualization: dict[str, Any] = dataclasses.field(default_factory=dict)
    warnings: list[str] = dataclasses.field(default_factory=list)
    errors: list[str] = dataclasses.field(default_factory=list)
    clarification: dict[str, Any] | None = None
    elapsed_ms: float = 0.0

    @property
    def ok(self) -> bool:
        return self.status == cfg.STATUS_OK

    @property
    def top(self) -> dict[str, Any] | None:
        """Convenience view — always derived, never stored independently."""
        return self.ranking_rows[0] if self.ranking_rows else None


# Simple in-process cache keyed by full config identity, so a country forecast
# can never be served for a country-and-product question.
_CACHE: dict[str, tuple[float, PredictionResult]] = {}
_CACHE_TTL_SECONDS = 900
_CACHE_MAX = 64


def clear_cache() -> None:
    _CACHE.clear()


def _cache_key(config: PredictionConfig) -> str:
    from services.auth import current_user_id
    return f"{current_user_id.get()}|{config.identity()}"


# ──────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────

def execute(config: PredictionConfig, use_cache: bool = True) -> PredictionResult:
    """Run a resolved configuration and return a structured result."""
    started = time.time()

    if config.status == cfg.STATUS_NEEDS_CLARIFICATION:
        return PredictionResult(
            config=config.to_dict(), status=config.status,
            clarification=config.clarification, warnings=list(config.warnings),
        )
    if not config.is_executable:
        return PredictionResult(
            config=config.to_dict(),
            status=config.status if config.status != cfg.STATUS_OK else cfg.STATUS_INVALID_CONFIG,
            errors=list(config.errors), warnings=list(config.warnings),
        )

    key = _cache_key(config)
    if use_cache and key in _CACHE:
        cached_at, cached = _CACHE[key]
        if time.time() - cached_at < _CACHE_TTL_SECONDS:
            logger.info("[Engine] Cache hit for %s", config.identity())
            return cached
        _CACHE.pop(key, None)

    logger.info("[Engine] Executing %s", config.describe())

    try:
        if config.prediction_type == cfg.FORECASTING:
            result = _run_forecasting(config)
        elif config.prediction_type == cfg.REGRESSION:
            result = _run_supervised(config, cfg.REGRESSION)
        else:
            result = _run_supervised(config, cfg.CLASSIFICATION)
    except Exception as exc:
        logger.exception("[Engine] Execution failed")
        return PredictionResult(
            config=config.to_dict(), status=cfg.STATUS_ERROR,
            errors=[str(exc)], warnings=list(config.warnings),
            elapsed_ms=round((time.time() - started) * 1000, 1),
        )

    result.elapsed_ms = round((time.time() - started) * 1000, 1)
    result.warnings = list(config.warnings) + result.warnings
    _enforce_granularity(config, result)

    if use_cache and result.ok:
        if len(_CACHE) >= _CACHE_MAX:
            _CACHE.pop(next(iter(_CACHE)), None)
        _CACHE[key] = (time.time(), result)

    logger.info(
        "[Engine] %s -> status=%s forecast_rows=%d ranked=%d excluded=%d in %.0fms",
        config.identity(), result.status, len(result.forecast_rows),
        len(result.ranking_rows), len(result.excluded_groups), result.elapsed_ms,
    )
    return result


def _enforce_granularity(config: PredictionConfig, result: PredictionResult) -> None:
    """
    Check the rows are reported at the level the config asked for.

    Every derived view is built from rows keyed by ``group_values``, so the
    level actually answered is observable. If it carries dimensions the config
    does not, the rows are rolled back up to the requested level; answering a
    country question with country-and-product rows is wrong even when each
    individual number is right. A level that is *missing* cannot be recovered
    by aggregation, so that is reported as an error instead of being papered
    over.
    """
    result.result_granularity = config.result_granularity
    expected = list(config.group_dimensions)

    observed: set[str] = set()
    for row in result.forecast_rows + result.ranking_rows:
        observed |= set((row.get("group_values") or {}).keys())
    if not observed:
        return

    extra = [d for d in observed if d not in expected]
    missing = [d for d in expected if d not in observed]

    if missing:
        result.status = cfg.STATUS_INVALID_CONFIG
        result.errors.append(
            f"Result is missing the requested grouping ({', '.join(missing)}); "
            f"it cannot be reported at '{config.result_granularity}'."
        )
        return

    if extra:
        logger.warning(
            "[Engine] Rolling result back up from %s to %s",
            "_".join(sorted(observed)), config.result_granularity,
        )
        result.warnings.append(
            f"Rolled the result back up to {config.result_granularity}; the "
            f"question did not ask to break it down by {', '.join(extra)}."
        )
        _rollup(result, expected)


def _rollup(result: PredictionResult, dimensions: list[str]) -> None:
    """Sum rows that differ only by dimensions outside ``dimensions``."""
    def collapse(rows: list[dict[str, Any]], keep_period: bool) -> list[dict[str, Any]]:
        merged: dict[tuple, dict[str, Any]] = {}
        for row in rows:
            values = {d: (row.get("group_values") or {}).get(d) for d in dimensions}
            period = row.get("period") if keep_period else None
            key = (tuple(values.items()), period)
            entry = merged.get(key)
            if entry is None:
                entry = {k: v for k, v in row.items()
                         if k not in ("value", "group", "group_values",
                                      "lower", "upper", "rank")}
                entry["group_values"] = values
                entry["group"] = " - ".join(str(v) for v in values.values()) or None
                entry["value"] = 0.0
                merged[key] = entry
            # Bounds are summed alongside the value so an interval stays an
            # interval; a rolled-up point estimate with the original group's
            # bounds would understate the spread.
            for field in ("value", "lower", "upper"):
                if row.get(field) is not None:
                    entry[field] = (entry.get(field) or 0.0) + float(row[field])
        return list(merged.values())

    result.forecast_rows = collapse(result.forecast_rows, keep_period=True)
    result.historical_rows = collapse(result.historical_rows, keep_period=True)
    result.aggregated_rows = collapse(result.aggregated_rows, keep_period=False)

    ranked = sorted(collapse(result.ranking_rows, keep_period=False),
                    key=lambda r: r.get("value") or 0.0, reverse=True)
    for i, row in enumerate(ranked, start=1):
        row["rank"] = i
    result.ranking_rows = ranked
    result.top_rows = ranked[:len(result.top_rows)] if result.top_rows else []
    # Growth and comparison were derived from the finer rows and no longer
    # describe these; recomputing them belongs to the operations layer.
    result.growth_rows = []


# ──────────────────────────────────────────────────────────
# Forecasting
# ──────────────────────────────────────────────────────────

def _apply_filters(df: pd.DataFrame, config: PredictionConfig) -> pd.DataFrame:
    """
    Restrict the rows a prediction is built from.

    A filter may name a column that lives in a dimension table rather than in
    the fact table ("the Delish team", where `team` is in a people table). Such
    a column is joined in for the duration of the filter and then dropped, so
    filtering by a dimension does not require grouping by it.
    """
    from prediction.service import _load_table

    for f in config.filters:
        column = f.column
        wanted = {str(v) for v in f.values}

        if column in df.columns:
            df = df[df[column].astype(str).isin(wanted)]
            continue

        joined = _join_dimension_column(df, column, config)
        if joined is None:
            config.warnings.append(
                f"Filter column '{column}' could not be resolved to this dataset; ignored."
            )
            continue
        df, added = joined
        df = df[df[column].astype(str).isin(wanted)]
        df = df.drop(columns=[c for c in added if c in df.columns])

    return df


def _join_dimension_column(df: pd.DataFrame, column: str, config: PredictionConfig):
    """Bring one dimension column onto the fact rows. Returns (df, added columns)."""
    from prediction.dimensions import resolve_dimensions
    from prediction.service import _load_table

    try:
        resolution = resolve_dimensions([column], config.table)
    except Exception as exc:
        logger.warning("[Engine] Could not resolve filter column '%s': %s", column, exc)
        return None
    if not resolution.resolved:
        return None

    spec = resolution.resolved[0]
    if not spec.requires_join:
        return (df, []) if spec.column in df.columns else None

    dim_df = _load_table(spec.table)
    if spec.join_key_target not in dim_df.columns or spec.column not in dim_df.columns:
        return None
    if spec.join_key_base not in df.columns:
        return None

    projection = dim_df[[spec.join_key_target, spec.column]].drop_duplicates()
    merged = pd.merge(
        df, projection,
        left_on=spec.join_key_base, right_on=spec.join_key_target, how="inner",
    )
    added = [spec.column]
    if spec.join_key_target != spec.join_key_base and spec.join_key_target in merged.columns:
        added.append(spec.join_key_target)
    # The caller filters on `spec.column`; expose it under the requested name.
    if spec.column != column:
        merged[column] = merged[spec.column]
        added.append(column)
    return merged, added


def _run_forecasting(config: PredictionConfig) -> PredictionResult:
    from prediction import predictor
    from prediction.service import _load_table

    result = PredictionResult(config=config.to_dict())
    df = _apply_filters(_load_table(config.table), config)

    if df.empty:
        result.status = cfg.STATUS_INSUFFICIENT_DATA
        result.errors.append("No rows remain after applying the requested filters.")
        return result

    result.dataset_context = {
        "table": config.table,
        "rows": int(len(df)),
        "time_column": config.time_column,
        "history_start": config.history_start,
        "history_end": config.history_end,
        "frequency": config.time_frequency,
    }

    if config.is_grouped:
        dimensions = [dict(spec) for spec in config.dimension_specs]
        loaded: dict[str, pd.DataFrame] = {}
        for spec in dimensions:
            if not spec.get("requires_join", True):
                continue
            table = spec["target_table"]
            if table not in loaded:
                loaded[table] = _load_table(table)
            spec["dim_df"] = loaded[table]

        grouped = predictor.predict_grouped_forecast(
            df=df, dimensions=dimensions, target_col=config.target,
            steps=config.horizon, frequency=config.time_frequency,
            table_name=config.table, ranking_metric=config.ranking_metric,
        )
        _absorb_grouped(result, grouped, config)
    else:
        from prediction.preprocessing import aggregate_time_series

        series, info = aggregate_time_series(
            df, config.time_column, config.target, frequency=config.time_frequency,
        )
        diagnostics, meta, forecast_mean, ci = predictor.run_series_forecast(
            series, steps=config.horizon, frequency=config.time_frequency,
            inferred_frequency=info.get("inferred_frequency"),
            duplicate_timestamps=info.get("duplicate_timestamps", 0),
            n_trimmed_partial=info.get("n_trimmed_partial", 0),
        )
        result.series_diagnostics = dataclasses.asdict(diagnostics)
        result.model_metadata = dataclasses.asdict(meta)
        result.historical_rows = [
            {"period": str(d), "value": float(v) if pd.notna(v) else None}
            for d, v in series.items()
        ]
        for d, v in forecast_mean.items():
            row = {"period": str(d), "value": float(v) if pd.notna(v) else None}
            if ci is not None and d in ci.index:
                row["lower"] = float(ci.loc[d, "lower"])
                row["upper"] = float(ci.loc[d, "upper"])
            result.forecast_rows.append(row)

        if not result.forecast_rows:
            result.status = cfg.STATUS_INSUFFICIENT_DATA
            result.errors.append(diagnostics.reason or "The series could not be forecast.")
            return result

        total = _sum([r["value"] for r in result.forecast_rows])
        result.aggregated_rows = [{"group": None, "group_values": {}, "value": total}]

    _apply_operations(result, config)
    _attach_visualization(result, config)
    return result


def _absorb_grouped(result: PredictionResult, grouped, config: PredictionConfig) -> None:
    """Flatten a grouped forecast into long-form rows, one per group × period."""
    result.excluded_groups = list(getattr(grouped, "excluded_groups", None) or [])

    for entry in grouped.raw_forecast_results:
        group_values = dict(entry.get("group_dict") or {})
        label = entry.get("group")

        for row in entry.get("historical") or []:
            result.historical_rows.append({
                "group": label, "group_values": group_values,
                "period": row.get("date"), "value": row.get("value"),
            })
        for row in entry.get("forecast") or []:
            result.forecast_rows.append({
                "group": label, "group_values": group_values,
                "period": row.get("date"), "value": row.get("value"),
                "lower": row.get("lower"), "upper": row.get("upper"),
            })

        result.aggregated_rows.append({
            "group": label, "group_values": group_values,
            "value": entry.get("final_value"),
            "status": entry.get("status"),
            "reason": entry.get("reason"),
            "is_fallback": entry.get("is_fallback", False),
        })
        if entry.get("model"):
            result.model_metadata.setdefault("per_group", {})[label] = entry["model"]
        if entry.get("diagnostics"):
            result.series_diagnostics.setdefault("per_group", {})[label] = entry["diagnostics"]

    if not result.forecast_rows:
        result.status = cfg.STATUS_INSUFFICIENT_DATA
        reasons = "; ".join(
            f"{e.get('group')}: {e.get('reason')}" for e in result.excluded_groups[:5]
        )
        result.errors.append(
            "No group had enough history to forecast." + (f" {reasons}" if reasons else "")
        )


# ──────────────────────────────────────────────────────────
# Regression / classification
# ──────────────────────────────────────────────────────────

def _run_supervised(config: PredictionConfig, kind: str) -> PredictionResult:
    from prediction import detector, predictor, trainer
    from prediction.service import _load_table

    result = PredictionResult(config=config.to_dict())
    df = _apply_filters(_load_table(config.table), config)

    detection = detector.detect(df, config.table, target_hint=config.target)
    if not detection.is_suitable:
        result.status = cfg.STATUS_INSUFFICIENT_DATA
        result.errors.append(detection.reason)
        return result
    if detection.problem_type != kind:
        result.status = cfg.STATUS_INVALID_CONFIG
        result.errors.append(
            f"'{config.target}' resolves to a {detection.problem_type} target, "
            f"not {kind}."
        )
        return result

    artifact = trainer.load_artifact(config.table, detection.target_column)
    if artifact is None or getattr(artifact, "problem_type", None) != kind:
        experiment = trainer.train_all(df, config.table, target_col=detection.target_column)
        if not experiment.models:
            result.status = cfg.STATUS_INSUFFICIENT_DATA
            result.errors.append(f"No {kind} model could be trained for '{config.target}'.")
            return result
        artifact = experiment.models[0]
        result.validation_metrics = {
            "selection_metric": experiment.selection_metric,
            "best_model": experiment.best_model_key,
            "candidates": experiment.training_results,
        }

    predictions = predictor.predict(df, artifact, rank_by_probability=True)
    result.row_predictions = [dataclasses.asdict(r) for r in predictions.row_predictions]
    result.model_metadata = {
        "selected_model_label": artifact.model_type,
        "problem_type": kind,
        "accuracy": predictions.model_accuracy,
    }
    result.dataset_context = {
        "table": config.table, "rows": int(len(df)),
        "target": detection.target_column,
        "features": detection.feature_columns,
    }
    _attach_visualization(result, config)
    return result


# ──────────────────────────────────────────────────────────
# Generic operations — structured data in, structured data out
# ──────────────────────────────────────────────────────────

def _sum(values: list) -> float | None:
    """Sum, counting real zeros and skipping unknowns."""
    present = [v for v in values if v is not None]
    return float(sum(present)) if present else None


def rank_future(result: PredictionResult, descending: bool = True) -> list[dict]:
    """Order entities by their forecast value. Unforecastable entities sort last."""
    rows = [dict(r) for r in result.aggregated_rows]
    rows.sort(key=lambda r: (r.get("value") is None,
                             -(r["value"]) if r.get("value") is not None else 0.0))
    if not descending:
        ranked = [r for r in rows if r.get("value") is not None]
        ranked.reverse()
        rows = ranked + [r for r in rows if r.get("value") is None]
    for i, row in enumerate([r for r in rows if r.get("value") is not None], start=1):
        row["rank"] = i
    return rows


def calculate_growth(result: PredictionResult, config: PredictionConfig) -> list[dict]:
    """Growth of each entity's forecast against its own like-for-like baseline."""
    from agents.forecast_comparison import compute_growth

    horizon = config.growth_baseline_periods or config.horizon or 1
    by_group: dict[Any, dict[str, list]] = {}
    for row in result.historical_rows:
        by_group.setdefault(row.get("group"), {"hist": [], "fc": []})["hist"].append(
            {"value": row.get("value")})
    for row in result.forecast_rows:
        by_group.setdefault(row.get("group"), {"hist": [], "fc": []})["fc"].append(
            {"value": row.get("value")})

    rows = []
    for group, series in by_group.items():
        growth = compute_growth(series["hist"], series["fc"], horizon)
        aggregated = next(
            (a for a in result.aggregated_rows if a.get("group") == group), {})
        rows.append({
            "group": group,
            "group_values": aggregated.get("group_values", {}),
            "baseline_total": growth["baseline_total"],
            "baseline_periods": growth["baseline_periods"],
            "forecast_total": growth["forecast_total"],
            "absolute_change": growth["absolute_change"],
            "growth_pct": growth["growth_pct"],
            "reason": growth["reason"],
        })

    rows.sort(key=lambda r: (r["growth_pct"] is None,
                             -(r["growth_pct"]) if r["growth_pct"] is not None else 0.0))
    for i, row in enumerate([r for r in rows if r["growth_pct"] is not None], start=1):
        row["rank"] = i
    return rows


def compare_historical_future(result: PredictionResult, config: PredictionConfig) -> dict | None:
    """Current top-N versus forecast top-N, computed over every entity."""
    from agents.forecast_comparison import RankedEntry, compare_rankings

    if not result.aggregated_rows:
        return None

    historical_totals: dict[Any, float] = {}
    for row in result.historical_rows:
        if row.get("value") is None:
            continue
        historical_totals[row.get("group")] = (
            historical_totals.get(row.get("group"), 0.0) + row["value"]
        )
    if not historical_totals:
        return None

    current = [RankedEntry(0, str(g), v) for g, v in historical_totals.items()]
    current.sort(key=lambda e: e.value, reverse=True)
    for i, e in enumerate(current, start=1):
        e.rank = i

    future = [
        RankedEntry(r.get("rank", 0), str(r.get("group")), r["value"],
                    r.get("group_values", {}))
        for r in result.ranking_rows if r.get("value") is not None
    ]
    if not future:
        return None

    top_n = config.top_n or min(3, len(future))
    comparison = compare_rankings(current, future, top_n=top_n,
                                  n_excluded=len(result.excluded_groups))
    return dataclasses.asdict(comparison)


def rank_final_period(result: PredictionResult) -> list[dict]:
    """
    Rank entities by their value in the LAST forecast period.

    "Which country has the highest revenue in the final month?" is not the
    same question as "over the next six months": summing the horizon can crown
    a different entity than the one leading at the end of it. The full
    timeline is preserved, and only the closing period is ranked.
    """
    last_period = None
    for row in result.forecast_rows:
        period = row.get("period")
        if period and (last_period is None or str(period) > str(last_period)):
            last_period = period
    if last_period is None:
        return []

    rows = [
        {"group": r.get("group"), "group_values": r.get("group_values", {}),
         "value": r.get("value"), "period": r.get("period")}
        for r in result.forecast_rows if str(r.get("period")) == str(last_period)
    ]
    rows.sort(key=lambda r: (r.get("value") is None,
                             -(r["value"]) if r.get("value") is not None else 0.0))
    for i, row in enumerate([r for r in rows if r.get("value") is not None], start=1):
        row["rank"] = i
    return rows


def _apply_operations(result: PredictionResult, config: PredictionConfig) -> None:
    """Apply the derived views the config asked for, in dependency order."""
    if not result.ok:
        return

    # Ranking underpins top-N and comparison, so it runs whenever any of them
    # is requested — always over the complete set of forecast entities.
    if config.wants(cfg.OP_RANK) or config.wants(cfg.OP_TOP_N) or config.wants(cfg.OP_COMPARE):
        result.ranking_rows = rank_future(result)

    if config.wants(cfg.OP_GROWTH):
        result.growth_rows = calculate_growth(result, config)
        if config.ranking_metric == "growth":
            # Rank by growth rather than level when that is what was asked.
            result.ranking_rows = [
                {"group": r["group"], "group_values": r["group_values"],
                 "value": r["growth_pct"], "rank": r.get("rank"),
                 "metric": "growth_pct", "reason": r["reason"]}
                for r in result.growth_rows
            ]

    # A final-period question ranks the closing period instead of the total.
    if config.wants(cfg.OP_FINAL_PERIOD):
        final = rank_final_period(result)
        if final:
            result.ranking_rows = final
            result.visualization.setdefault("notes", []).append(
                f"Ranked on the final forecast period ({final[0].get('period')}), "
                "not on the horizon total."
            )

    if config.wants(cfg.OP_COMPARE):
        result.comparison = compare_historical_future(result, config)

    if config.wants(cfg.OP_TOP_N) and config.top_n:
        # A view over the full ranking. `ranking_rows` keeps every entity that
        # was forecast, because truncating the source of truth makes the
        # discarded entities unavailable to any follow-up.
        result.top_rows = result.ranking_rows[: config.top_n]


# ──────────────────────────────────────────────────────────
# Visualization metadata (semantic, not chart-specific)
# ──────────────────────────────────────────────────────────

def _attach_visualization(result: PredictionResult, config: PredictionConfig) -> None:
    """
    Describe the *shape* of the result so a renderer can pick a chart.

    The backend states what the data is — a time series, a ranking, a growth
    ranking, per-row predictions — and the frontend decides how to draw it.
    No chart type is tied to a question here.
    """
    spec: dict[str, Any] = {
        "prediction_type": config.prediction_type,
        "target": config.target,
        "dimensions": list(config.group_dimensions),
        "frequency": config.time_frequency,
        "horizon": config.horizon,
        "has_history": bool(result.historical_rows),
        "has_forecast": bool(result.forecast_rows),
        "has_ranking": bool(result.ranking_rows),
        "has_growth": bool(result.growth_rows),
        "has_comparison": result.comparison is not None,
        "n_groups": len({r.get("group") for r in result.forecast_rows}) if result.forecast_rows else 0,
    }

    views: list[str] = []
    if config.prediction_type == cfg.FORECASTING:
        views.append("grouped_time_series" if config.is_grouped else "time_series")
        if result.growth_rows and config.ranking_metric == "growth":
            views.append("growth_ranking")
        elif result.ranking_rows:
            views.append("value_ranking")
        if result.comparison is not None:
            views.append("rank_comparison")
    elif config.prediction_type == cfg.CLASSIFICATION:
        views += ["class_distribution", "probability_ranking", "feature_importance"]
    else:
        views += ["value_distribution", "value_ranking", "feature_importance"]

    spec["views"] = views
    result.visualization = spec
