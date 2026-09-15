"""
Semantic Task Router
====================

Decides *what the user is asking for* before anything decides *how to compute
it*. Every question passes through here, and the answer is a task plus an
engine — descriptive BI, classification, regression, or time-series forecast.

Two principles drive it.

**Deterministic BI has priority.** A question that can be answered by counting,
averaging, grouping, filtering or ranking the data already recorded is a BI
question. It stays a BI question even when the dataset happens to contain a
column a model *could* be trained on. "What is the churn rate by country?" is
an aggregation over a column named churn; it is not a churn model. The presence
of a predictable target is not a request to predict.

**Capability is checked against the data, not assumed.** A forecast needs a
temporal column with real history; a classifier needs a categorical target. When
the question asks for something the dataset cannot support, the router says so
and names what the dataset *can* do, rather than fabricating a result of the
wrong shape.

Nothing here is specific to a dataset or a question. The markers are linguistic;
the capabilities come from profiling whatever table is in scope.
"""

from __future__ import annotations

import dataclasses
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# ── Execution engines ──
ENGINE_BI = "bi"
ENGINE_CLASSIFICATION = "classification"
ENGINE_REGRESSION = "regression"
ENGINE_FORECAST = "forecast"

# ── Task taxonomy ──
HISTORICAL_AGGREGATION = "historical_aggregation"
HISTORICAL_COMPARISON = "historical_comparison"
HISTORICAL_RANKING = "historical_ranking"
HISTORICAL_DISTRIBUTION = "historical_distribution"
HISTORICAL_FILTERED_ANALYSIS = "historical_filtered_analysis"
CORRELATION = "correlation"
CLASSIFICATION = "classification"
REGRESSION = "regression"
TIME_SERIES_FORECAST = "time_series_forecast"
GROUPED_TIME_SERIES_FORECAST = "grouped_time_series_forecast"
FUTURE_RANKING = "future_ranking"
FUTURE_GROWTH = "future_growth"
FUTURE_COMPARISON = "future_comparison"

BI_TASKS = {
    HISTORICAL_AGGREGATION, HISTORICAL_COMPARISON, HISTORICAL_RANKING,
    HISTORICAL_DISTRIBUTION, HISTORICAL_FILTERED_ANALYSIS, CORRELATION,
}
FORECAST_TASKS = {
    TIME_SERIES_FORECAST, GROUPED_TIME_SERIES_FORECAST,
    FUTURE_RANKING, FUTURE_GROWTH, FUTURE_COMPARISON,
}


# ══════════════════════════════════════════════════════════
# Linguistic markers. Purely about *how a question is asked* —
# no column names, no domain vocabulary, no question templates.
# ══════════════════════════════════════════════════════════

#: An explicit instruction to build or run a model.
_PREDICT_VERB = re.compile(
    r"\b(predict\w*|forecast\w*|project(?:ed|ion|ions)?|extrapolat\w*|"
    r"model\s+(?:the|a|whether|if)|simulat\w*)\b", re.IGNORECASE)

#: Reference to a period that has not happened yet.
_FUTURE_TIME = re.compile(
    r"\b(next\s+(?:\d+\s+)?(?:day|days|week|weeks|month|months|quarter|quarters|year|years|period|periods)|"
    r"future|upcoming|coming\s+(?:day|week|month|quarter|year|half|period)|"
    r"ahead|going forward|from now|onwards?)\b", re.IGNORECASE)

#: Statements about what *will* happen. "Could you"/"would you" are politeness,
#: not prediction — a request to show data is not a request to model it.
_FUTURE_MODALITY = re.compile(
    # "soon" belongs here rather than with the named periods: it says something
    # has not happened yet without saying over which periods to project, so it
    # signals prediction without implying a time series.
    r"\b(will|won't|shall|going to|about to|soon|(?:might|could|would)(?!\s+you\b)|"
    r"likely to|unlikely to|expected to|"
    r"expect\w*\s+to|anticipat\w*|set to|on track to|poised to|"
    r"remain\s+(?:the|a|in|on)|stay\s+(?:the|a|in|on))\b", re.IGNORECASE)

#: Per-entity probability language — the hallmark of a scoring request.
_PROPENSITY = re.compile(
    r"\b(probability|propensity|likelihood|odds of|chance(?:s)? of|"
    r"(?:most |more |least )?likely to\s+\w+|at\s+risk|risk of\s+\w+|"
    r"(?:high|low|elevated)[- ]risk|score\w*\s+(?:for|by)\s+risk|"
    r"which\s+\w+\s+(?:are|is)\s+(?:most\s+)?likely)\b", re.IGNORECASE)

#: Ordinary analytical verbs over data already recorded.
_DESCRIPTIVE = re.compile(
    r"\b(what\s+(?:is|are|was|were)|how\s+many|how\s+much|count|total|sum|"
    r"average|avg|mean|median|min|minimum|max|maximum|rate|ratio|percent\w*|"
    r"proportion|share|distribution|breakdown|break\s+down|spread|"
    r"list|show|display|give me|tell me|compare|comparison|versus|vs\b|"
    r"group(?:ed)?\s+by|by\s+\w+|per\s+\w+|highest|lowest|top|bottom|rank\w*|"
    r"most|least|best|worst|greatest|smallest|which\s+\w+\s+has)\b",
    re.IGNORECASE)

#: Explicitly historical framing.
_PAST = re.compile(
    r"\b(was|were|had|did|has\s+been|have\s+been|"
    r"last\s+(?:day|week|month|quarter|year)|previous|prior|earlier|"
    r"historical\w*|so far|to date|yesterday|already)\b", re.IGNORECASE)

#: Anaphora — a follow-up that carries no subject of its own.
_ANAPHORIC = re.compile(
    r"\b(it|its|it's|they|them|their|theirs|that one|this one|these|those|"
    r"the same|the top one|the highest one|the lowest one|the leader|"
    r"which one|what about|how about)\b", re.IGNORECASE)

_RANK_WORDS = re.compile(
    r"\b(highest|lowest|top|bottom|rank\w*|most|least|best|worst|leader|"
    r"leading|greatest|smallest|first|#1)\b", re.IGNORECASE)
_GROWTH_WORDS = re.compile(
    r"\b(grow\w*|increase\w*|decrease\w*|decline\w*|change\w*|rise|rising|"
    r"fall\w*|shrink\w*|improv\w*)\b", re.IGNORECASE)
_COMPARE_WORDS = re.compile(
    r"\b(remain|stay|still|same|keep|hold|retain|enter|overtake|replace|"
    r"fall out|drop out)\b", re.IGNORECASE)
_DISTRIBUTION_WORDS = re.compile(
    r"\b(distribution|histogram|spread|range|percentile|quartile|bucket\w*)\b",
    re.IGNORECASE)
_CORRELATION_WORDS = re.compile(
    r"\b(correlat\w*|relationship between|associat\w*|related to|"
    r"impact of|effect of|influence of|driver\w* of|depend\w* on)\b",
    re.IGNORECASE)


@dataclasses.dataclass
class TaskDecision:
    """What the user asked for, and which engine can answer it."""
    task: str = HISTORICAL_AGGREGATION
    engine: str = ENGINE_BI
    confidence: float = 0.0
    reasons: list[str] = dataclasses.field(default_factory=list)
    #: Capabilities the question asked for that the dataset cannot provide.
    blocked: list[str] = dataclasses.field(default_factory=list)
    #: What the dataset *can* do instead, offered rather than silently swapped.
    alternatives: list[str] = dataclasses.field(default_factory=list)
    inherited_from_context: bool = False
    signals: dict[str, bool] = dataclasses.field(default_factory=dict)

    @property
    def is_predictive(self) -> bool:
        return self.engine != ENGINE_BI

    def describe(self) -> str:
        return (
            f"task={self.task} engine={self.engine} confidence={self.confidence:.2f}"
            + (f" blocked={self.blocked}" if self.blocked else "")
            + (" (inherited)" if self.inherited_from_context else "")
        )


@dataclasses.dataclass
class DatasetCapabilities:
    """What a dataset can actually support, discovered by profiling it."""
    table: str = ""
    has_temporal_column: bool = False
    temporal_columns: list[str] = dataclasses.field(default_factory=list)
    temporal_observations: int = 0
    measures: list[str] = dataclasses.field(default_factory=list)
    classification_targets: list[str] = dataclasses.field(default_factory=list)
    dimensions: list[str] = dataclasses.field(default_factory=list)

    @property
    def supports_forecast(self) -> bool:
        return self.has_temporal_column and bool(self.measures)

    @property
    def supports_classification(self) -> bool:
        return bool(self.classification_targets)

    @property
    def supports_regression(self) -> bool:
        return bool(self.measures)


def inspect_capabilities(table: str) -> DatasetCapabilities:
    """
    Profile a table for what analytical tasks it can support.

    Everything here is read from the data: whether a usable time axis exists,
    which columns are measures, which are categorical targets. No column name
    is assumed.
    """
    from prediction.profiler import build_profile

    capabilities = DatasetCapabilities(table=table)
    try:
        profile = build_profile(table)
    except Exception as exc:
        logger.warning("[TaskRouter] Could not profile '%s': %s", table, exc)
        return capabilities

    capabilities.temporal_columns = [t.column for t in profile.time_columns]
    capabilities.has_temporal_column = bool(profile.time_columns)
    if profile.time_columns:
        capabilities.temporal_observations = profile.time_columns[0].n_distinct
    capabilities.measures = profile.measure_names
    capabilities.classification_targets = profile.label_names
    capabilities.dimensions = [d["column"] for d in profile.dimensions]
    return capabilities


# ══════════════════════════════════════════════════════════
# Routing
# ══════════════════════════════════════════════════════════

def _signals(question: str) -> dict[str, bool]:
    text = question or ""
    return {
        "predict_verb": bool(_PREDICT_VERB.search(text)),
        "future_time": bool(_FUTURE_TIME.search(text)),
        "future_modality": bool(_FUTURE_MODALITY.search(text)),
        "propensity": bool(_PROPENSITY.search(text)),
        "descriptive": bool(_DESCRIPTIVE.search(text)),
        "past": bool(_PAST.search(text)),
        "anaphoric": bool(_ANAPHORIC.search(text)),
        "rank": bool(_RANK_WORDS.search(text)),
        "growth": bool(_GROWTH_WORDS.search(text)),
        "compare": bool(_COMPARE_WORDS.search(text)),
        "distribution": bool(_DISTRIBUTION_WORDS.search(text)),
        "correlation": bool(_CORRELATION_WORDS.search(text)),
    }


def _bi_task(signals: dict[str, bool]) -> str:
    """Pick which flavour of descriptive analysis was asked for."""
    if signals["correlation"]:
        return CORRELATION
    if signals["distribution"]:
        return HISTORICAL_DISTRIBUTION
    if signals["rank"]:
        return HISTORICAL_RANKING
    if signals["compare"]:
        return HISTORICAL_COMPARISON
    return HISTORICAL_AGGREGATION


def _forecast_task(signals: dict[str, bool]) -> str:
    if signals["growth"]:
        return FUTURE_GROWTH
    if signals["compare"]:
        return FUTURE_COMPARISON
    if signals["rank"]:
        return FUTURE_RANKING
    return TIME_SERIES_FORECAST


def classify_task(
    question: str,
    *,
    table: str | None = None,
    capabilities: DatasetCapabilities | None = None,
    previous_task: str | None = None,
    previous_engine: str | None = None,
) -> TaskDecision:
    """
    Decide the analytical task for a question.

    Args:
        question: the user's words, any phrasing.
        table: the table in scope, used to check capabilities.
        capabilities: pre-computed capabilities, to avoid re-profiling.
        previous_task / previous_engine: the prior turn, used **only** to
            resolve a follow-up that carries no signal of its own.

    Returns:
        A TaskDecision. ``blocked`` lists capabilities the dataset lacks.
    """
    signals = _signals(question)
    decision = TaskDecision(signals=signals)

    if capabilities is None and table:
        capabilities = inspect_capabilities(table)
    capabilities = capabilities or DatasetCapabilities()

    # ── 1. Is there any predictive signal at all? ──
    # Naming a predictable column is not one. An instruction to predict, a
    # reference to a period that has not happened, a statement about what will
    # happen, or per-entity probability language — those are.
    predictive_signal = (
        signals["predict_verb"] or signals["future_time"]
        or signals["future_modality"] or signals["propensity"]
    )

    # ── 2. Descriptive priority ──
    # A question with analytical verbs and no predictive signal is BI, whatever
    # columns the dataset happens to contain.
    if not predictive_signal:
        if signals["anaphoric"] and not signals["descriptive"] and previous_engine:
            # A bare follow-up ("which one is highest?") continues whatever the
            # conversation was already doing.
            decision.engine = previous_engine
            decision.task = previous_task or (
                _bi_task(signals) if previous_engine == ENGINE_BI else TIME_SERIES_FORECAST
            )
            if previous_engine == ENGINE_BI and signals["rank"]:
                decision.task = HISTORICAL_RANKING
            decision.inherited_from_context = True
            decision.confidence = 0.6
            decision.reasons.append(
                "No task signal of its own; continuing the previous "
                f"{previous_engine} analysis."
            )
            return _apply_capability_gates(decision, capabilities)

        decision.engine = ENGINE_BI
        decision.task = _bi_task(signals)
        decision.confidence = 0.9 if signals["descriptive"] else 0.7
        decision.reasons.append(
            "No instruction to predict, no future period, and no probability "
            "language — this is a question about data already recorded."
        )
        if signals["past"]:
            decision.confidence = min(1.0, decision.confidence + 0.05)
            decision.reasons.append("Explicitly framed in the past tense.")
        return _apply_capability_gates(decision, capabilities)

    # ── 3. Predictive, but which kind? ──
    # Per-entity probability language means scoring rows, not projecting a
    # series forward.
    if signals["propensity"] and not signals["future_time"]:
        decision.engine = ENGINE_CLASSIFICATION
        decision.task = CLASSIFICATION
        decision.confidence = 0.85
        decision.reasons.append(
            "Asks how likely individual records are to fall into a category."
        )
        return _apply_capability_gates(decision, capabilities)

    if signals["future_time"] or signals["future_modality"] or signals["predict_verb"]:
        # A *named future period* is what makes something a time-series
        # forecast: it says which periods to project into. Without one, an
        # instruction to predict is about individual records — "predict
        # customer churn" asks for a classifier, not a projection.
        if signals["future_time"]:
            decision.engine = ENGINE_FORECAST
            decision.task = _forecast_task(signals)
            decision.confidence = 0.85
            decision.reasons.append(
                "Names a period that has not happened yet, so this projects a "
                "measure over time."
            )
            return _apply_capability_gates(decision, capabilities)

        if (capabilities.supports_classification or signals["propensity"]
                or re.search(r"\bwhether\b", question, re.IGNORECASE)):
            decision.engine = ENGINE_CLASSIFICATION
            decision.task = CLASSIFICATION
            decision.confidence = 0.8
            decision.reasons.append(
                "Asks what will happen to individual records, with no future "
                "period named — a per-record prediction rather than a forecast."
            )
            return _apply_capability_gates(decision, capabilities)

        decision.engine = ENGINE_FORECAST
        decision.task = _forecast_task(signals)
        decision.confidence = 0.7
        decision.reasons.append(
            "Instructs a prediction and the dataset has no categorical outcome, "
            "so the measure is projected forward."
        )
        return _apply_capability_gates(decision, capabilities)

    decision.engine = ENGINE_BI
    decision.task = _bi_task(signals)
    decision.confidence = 0.5
    decision.reasons.append("No decisive signal; defaulting to descriptive analysis.")
    return _apply_capability_gates(decision, capabilities)


def _apply_capability_gates(
    decision: TaskDecision,
    capabilities: DatasetCapabilities,
) -> TaskDecision:
    """
    Check the chosen engine against what the dataset can actually do.

    A request the data cannot support is *blocked and explained*, never
    quietly converted into a different computation. Producing a "forecast"
    from a table with no time axis, or a classifier from a table with no
    categorical target, answers a question nobody asked.
    """
    if decision.engine == ENGINE_FORECAST and not capabilities.supports_forecast:
        if not capabilities.has_temporal_column:
            decision.blocked.append(
                "This dataset has no date or time column, so there is no history "
                "to project forward — a time-series forecast is not possible."
            )
        elif not capabilities.measures:
            decision.blocked.append(
                "This dataset has no numeric measure to forecast."
            )
        if capabilities.supports_classification:
            decision.alternatives.append(
                "It does support per-record classification on "
                f"{', '.join(capabilities.classification_targets)}."
            )
        if capabilities.dimensions and capabilities.measures:
            decision.alternatives.append(
                "Descriptive breakdowns by "
                f"{', '.join(capabilities.dimensions[:4])} are available."
            )

    if decision.engine == ENGINE_CLASSIFICATION and not capabilities.supports_classification:
        decision.blocked.append(
            "This dataset has no categorical outcome column to classify."
        )
        if capabilities.supports_forecast:
            decision.alternatives.append(
                "It does support time-series forecasting of "
                f"{', '.join(capabilities.measures[:4])}."
            )

    if decision.engine == ENGINE_REGRESSION and not capabilities.supports_regression:
        decision.blocked.append("This dataset has no numeric target to regress.")

    if decision.blocked:
        logger.info(
            "[TaskRouter] %s blocked: %s", decision.engine, "; ".join(decision.blocked),
        )
    return decision


def route(
    question: str,
    *,
    table: str | None = None,
    scope_tables: list[str] | None = None,
    previous_task: str | None = None,
    previous_engine: str | None = None,
) -> TaskDecision:
    """
    Public entry point: classify a question and log the decision.

    ``scope_tables`` lets the router pick the table in scope when one was not
    named, so capabilities are checked against the data the user is looking at.
    """
    resolved_table = table
    if not resolved_table and scope_tables:
        from prediction.profiler import choose_dataset_table
        try:
            resolved_table, _ = choose_dataset_table(scope_tables, require_time_axis=False)
        except Exception:
            resolved_table = scope_tables[0] if scope_tables else None

    capabilities = inspect_capabilities(resolved_table) if resolved_table else None
    decision = classify_task(
        question, table=resolved_table, capabilities=capabilities,
        previous_task=previous_task, previous_engine=previous_engine,
    )

    logger.info(
        "[TaskRouter] %r -> %s | signals=%s | %s",
        (question or "")[:80], decision.describe(),
        {k: v for k, v in decision.signals.items() if v},
        "; ".join(decision.reasons),
    )
    return decision
