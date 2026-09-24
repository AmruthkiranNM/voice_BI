"""
Prediction Package — Canonical Prediction Configuration

Every prediction request becomes a ``PredictionConfig`` before any data is
touched. The config is the contract between interpretation and computation:
a language model may help *fill it in*, but from that point on the numerical
engine sees only this structure and never the original sentence.

That boundary is what makes the engine general. Nothing downstream can branch
on how a question was worded, because nothing downstream has access to the
wording — only to a target, a time axis, a frequency, a horizon, dimensions,
filters, and the operations requested.

The config is also the cache identity. Two requests share a result only when
every field that could change a number matches, so a country forecast can
never be served for a country-and-product question, nor a revenue forecast for
a boxes question.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import Any


# ── Prediction problem types ──
FORECASTING = "forecasting"
REGRESSION = "regression"
CLASSIFICATION = "classification"

PREDICTION_TYPES = (FORECASTING, REGRESSION, CLASSIFICATION)

# ── Post-prediction operations. These are composable and independent of the
#    prediction type: a forecast may be ranked, growth-scored, compared with
#    history, or simply returned. ──
OP_RANK = "rank"
OP_GROWTH = "growth"
OP_COMPARE = "compare"
OP_TOP_N = "top_n"
OP_AGGREGATE = "aggregate"
#: Rank on the LAST forecast period rather than on the horizon total. "In the
#: final month" is a different question from "over the next six months".
OP_FINAL_PERIOD = "final_period"

# ── Result statuses ──
STATUS_OK = "ok"
STATUS_NEEDS_CLARIFICATION = "needs_clarification"
STATUS_INSUFFICIENT_DATA = "insufficient_data"
STATUS_INVALID_CONFIG = "invalid_config"
STATUS_ERROR = "error"


@dataclasses.dataclass
class Filter:
    """One equality/membership restriction on the source rows."""
    column: str
    operator: str = "in"          # in | eq | gte | lte | between
    values: list[Any] = dataclasses.field(default_factory=list)
    dimension: str | None = None  # the semantic name the user used


@dataclasses.dataclass
class PredictionConfig:
    """
    A fully-resolved, executable description of one prediction request.

    Every field is resolved against the live schema before execution; nothing
    here is a guess carried forward from the question text.
    """

    # ── What kind of prediction ──
    prediction_type: str = FORECASTING

    # ── Dataset ──
    table: str = ""
    dataset_tables: list[str] = dataclasses.field(default_factory=list)

    # ── Target ──
    target: str = ""                       # resolved physical column
    target_request: str | None = None      # the word the user used
    target_semantics: dict[str, Any] = dataclasses.field(default_factory=dict)
    aggregation: str = "sum"               # how rows combine into a period

    # ── Time ──
    time_column: str | None = None
    time_frequency: str = "months"
    horizon: int = 0
    forecast_start: str | None = None
    forecast_end: str | None = None
    history_start: str | None = None
    history_end: str | None = None

    # ── Grouping ──
    group_dimensions: list[str] = dataclasses.field(default_factory=list)
    dimension_specs: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    #: How the dimensions were arrived at: "inherited" when carried from the
    #: previous turn untouched, "replaced"/"drilldown" when the question asked
    #: to change them, "new" on a first turn. A follow-up that changes
    #: granularity without asking is a bug, and this records which happened.
    dimension_origin: str = "new"

    # ── Restrictions ──
    filters: list[Filter] = dataclasses.field(default_factory=list)

    # ── Operations requested on top of the prediction ──
    operations: list[str] = dataclasses.field(default_factory=list)
    top_n: int | None = None
    ranking_metric: str = "sum"            # sum | growth
    growth_baseline_periods: int | None = None   # defaults to the horizon
    compare_against: str | None = None     # "history" for current-vs-future

    # ── Modelling ──
    model_strategy: str = "auto"           # auto | naive | <explicit model key>
    confidence_level: float = 0.95
    feature_columns: list[str] = dataclasses.field(default_factory=list)

    # ── Provenance ──
    question: str = ""
    #: Entities the previous turn returned, and which of them led. These let a
    #: follow-up say "it" or "them" without restating anything.
    source_entities: list[str] = dataclasses.field(default_factory=list)
    source_leader: str | None = None
    resolved_by: dict[str, str] = dataclasses.field(default_factory=dict)
    warnings: list[str] = dataclasses.field(default_factory=list)
    clarification: dict[str, Any] | None = None

    # ── Validity ──
    status: str = STATUS_OK
    errors: list[str] = dataclasses.field(default_factory=list)

    # ------------------------------------------------------------------
    @property
    def is_grouped(self) -> bool:
        return bool(self.group_dimensions)

    @property
    def result_granularity(self) -> str:
        """
        The level a result is reported at, e.g. "country" or "country_product".

        Follow-ups inherit this unless the question asks to change it. Naming
        it explicitly makes an accidental change detectable instead of silent.
        """
        return "_".join(self.group_dimensions) if self.group_dimensions else "total"

    @property
    def is_executable(self) -> bool:
        return self.status == STATUS_OK and not self.errors

    def wants(self, operation: str) -> bool:
        return operation in self.operations

    def identity(self) -> str:
        """
        Stable hash over every field that can change a number.

        Deliberately excludes the question text, warnings and provenance: two
        differently-worded questions that resolve to the same configuration
        *should* share a result. It includes everything else, so no
        incompatible prediction can ever be served from cache.
        """
        payload = {
            "prediction_type": self.prediction_type,
            "table": self.table,
            "target": self.target,
            "aggregation": self.aggregation,
            "time_column": self.time_column,
            "time_frequency": self.time_frequency,
            "horizon": self.horizon,
            "group_dimensions": list(self.group_dimensions),
            "result_granularity": self.result_granularity,
            "dimension_columns": sorted(
                f"{s.get('target_table')}.{s.get('group_column')}"
                for s in self.dimension_specs
            ),
            "filters": sorted(
                f"{f.column}:{f.operator}:{sorted(map(str, f.values))}"
                for f in self.filters
            ),
            "ranking_metric": self.ranking_metric,
            "growth_baseline_periods": self.growth_baseline_periods,
            "model_strategy": self.model_strategy,
            "confidence_level": self.confidence_level,
            "feature_columns": sorted(self.feature_columns),
            # Operations change the derived views, so they belong in the key.
            "operations": sorted(self.operations),
            "top_n": self.top_n,
            "compare_against": self.compare_against,
            "final_period": OP_FINAL_PERIOD in self.operations,
        }
        blob = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()[:24]

    def describe(self) -> str:
        """One-line summary for logs — the observability requirement."""
        parts = [
            f"type={self.prediction_type}",
            f"table={self.table}",
            f"target={self.target}",
        ]
        if self.prediction_type == FORECASTING:
            parts += [
                f"time={self.time_column}",
                f"freq={self.time_frequency}",
                f"horizon={self.horizon}",
            ]
        if self.group_dimensions:
            parts.append(f"dims={self.group_dimensions}({self.dimension_origin})")
        if self.filters:
            parts.append(f"filters={[f.column for f in self.filters]}")
        if self.operations:
            parts.append(f"ops={self.operations}")
        parts.append(f"id={self.identity()}")
        return " ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        payload = dataclasses.asdict(self)
        # Derived, but carried explicitly so a consumer never has to re-derive
        # it — and so a follow-up can compare against it.
        payload["result_granularity"] = self.result_granularity
        return payload


def validate_config(config: PredictionConfig) -> list[str]:
    """
    Structural quality gate, run before any data is loaded.

    Catches configurations that cannot produce a meaningful result — a forecast
    with no time axis, a horizon of zero, a grouped request whose dimensions
    were never resolved. Failing here is much cheaper, and much clearer, than
    failing somewhere inside a model fit.
    """
    errors: list[str] = []

    if config.prediction_type not in PREDICTION_TYPES:
        errors.append(
            f"Unknown prediction type '{config.prediction_type}'. "
            f"Expected one of {', '.join(PREDICTION_TYPES)}."
        )
    if not config.table:
        errors.append("No dataset table was resolved for this prediction.")
    if not config.target:
        errors.append("No target column was resolved for this prediction.")

    if config.prediction_type == FORECASTING:
        if not config.time_column:
            errors.append(
                "Forecasting needs a time column, and none was found in this dataset."
            )
        if config.horizon <= 0:
            errors.append(f"Forecast horizon must be positive, got {config.horizon}.")

    if config.group_dimensions and len(config.dimension_specs) != len(config.group_dimensions):
        errors.append(
            f"{len(config.group_dimensions)} dimension(s) were requested but "
            f"{len(config.dimension_specs)} were resolved to real columns."
        )

    if config.wants(OP_GROWTH) and config.prediction_type != FORECASTING:
        errors.append("Growth is derived from a forecast, so it needs a forecasting request.")

    if config.top_n is not None and config.top_n <= 0:
        errors.append(f"top_n must be positive, got {config.top_n}.")

    return errors
