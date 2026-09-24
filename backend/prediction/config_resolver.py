"""
Prediction Package — Configuration Resolver

Converts a question (plus any inherited conversational context) into a fully
resolved ``PredictionConfig``.

This is the only place where natural language touches the prediction system.
A language model is used for *interpretation* — which of this dataset's
measures does "revenue" mean, is this asking about the future, does it want a
ranking — and every answer it gives is then re-resolved against the live
schema. A target it names must resolve to a real column via the target
profiler; dimensions must resolve through join-verified dimension resolution;
the horizon is parsed deterministically. Anything the model asserts that the
schema does not support is discarded, not trusted.

There are no question templates here and no phrase tables. The same code path
handles "Which country will lead next month?", "Who is expected to have the
highest revenue next month?" and a question about a dataset this system has
never seen, because all three are resolved against a profile of whatever data
is actually present.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from prediction import config as cfg
from prediction.config import Filter, PredictionConfig, validate_config
from prediction.profiler import DatasetProfile, build_profile, choose_dataset_table
from prediction.target_resolution import resolve_prediction_type, resolve_target
from prediction.time_resolution import resolve_frequency, resolve_horizon, select_time_column

logger = logging.getLogger(__name__)


INTERPRETATION_PROMPT = """You are interpreting an analytics question against a specific dataset.

Your job is ONLY to map the question onto this dataset's columns. You are not
computing anything, and you must not invent column names.

{profile}

{context_block}
QUESTION: "{question}"

Return ONLY a JSON object:
{{
  "asks_about_future": true/false,
  "target": "<the measure or label column being asked about, exactly as named above, or null>",
  "target_phrase": "<the words in the question that refer to it, or null>",
  "group_dimensions": ["<dimension columns to break the result down by, exactly as named above>"],
  "keeps_previous_dimensions": true/false,
  "filters": [{{"column": "<dimension column>", "values": ["<value>"]}}],
  "horizon_count": <number or null>,
  "horizon_unit": "days|weeks|months|quarters|years|null",
  "time_column": "<which time column to use, if the question implies one, else null>",
  "wants_ranking": true/false,
  "wants_growth": true/false,
  "wants_comparison_with_present": true/false,
  "top_n": <number or null>,
  "wants_final_period_only": true/false,
  "ambiguous_target": true/false,
  "candidate_targets": ["<columns that could plausibly be meant, if ambiguous>"]
}}

GUIDANCE:
- "asks_about_future" is true for anything about what will, is expected to, is
  likely to, or is projected to happen, in any phrasing.
- "wants_ranking" is true when the question asks which one is highest/lowest/
  best/first, or asks for a top/bottom list.
- "wants_growth" is true only when the question is about change, growth,
  decline, increase or improvement — not merely about a future level.
- "wants_comparison_with_present" is true when the question asks whether the
  current situation will persist or change (leaders staying, entering, falling).
- "ambiguous_target" is true when several listed measures fit the words used
  equally well and picking the wrong one would change the answer.
- "keeps_previous_dimensions" is true when the question refers back to the
  entities of the previous result ("their ...", "each of them", "within those",
  "for these") and is asking to break those entities down further. In that case
  list ONLY the new inner dimension in "group_dimensions"; the previous ones
  are added automatically. It is false when the question replaces the grouping
  ("what about by region instead").
- "wants_final_period_only" is true when the question asks about the LAST
  period of the horizon specifically ("in the final month", "by the end of the
  year", "in the last quarter") rather than about the horizon as a whole.
- Use only column names that appear above. If nothing fits, use null.
"""


def _call_interpreter(prompt: str) -> dict[str, Any]:
    """Ask the model to map the question onto the dataset. Never fatal."""
    from services.llm_service import call_llm

    try:
        raw = call_llm(prompt, expect_json=True)
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        return parsed if isinstance(parsed, dict) else {}
    except Exception as exc:
        logger.warning("[ConfigResolver] Interpretation unavailable (%s); "
                       "falling back to deterministic resolution.", exc)
        return {}


# ──────────────────────────────────────────────────────────
# Deterministic fallbacks — used when interpretation is
# unavailable, and always used to verify what it returned.
# ──────────────────────────────────────────────────────────

_FUTURE_MARKERS = re.compile(
    r"\b(will|expected|expect|likely|forecast|predict|projection|projected|"
    r"future|next|upcoming|going to|anticipat\w*|outlook|remain|stay)\b",
    re.IGNORECASE,
)
_RANK_MARKERS = re.compile(
    r"\b(highest|lowest|most|least|best|worst|top|bottom|rank|ranking|leader|"
    r"lead|leading|first|#1|number one|greatest|largest|smallest)\b",
    re.IGNORECASE,
)
_GROWTH_MARKERS = re.compile(
    r"\b(grow|growth|growing|increase|increasing|decline|declining|decrease|"
    r"fastest|improve|improving|change|shrink|rise|rising|fall|falling)\b",
    re.IGNORECASE,
)
_FINAL_PERIOD_MARKERS = re.compile(
    r"(final|last)\s+(month|quarter|week|year|period|day)|"
    r"by the end of|at the end of|end of the (?:horizon|period|forecast)",
    re.IGNORECASE,
)
_COMPARE_MARKERS = re.compile(
    r"\b(remain|stay|still|same|keep|hold|retain|enter|entering|overtake|"
    r"replace|fall out|drop out|change places)\b",
    re.IGNORECASE,
)


def _asks_about_future(question: str) -> bool:
    return bool(_FUTURE_MARKERS.search(question or ""))


def _match_by_words(phrase: str | None, candidates: list[str]) -> str | None:
    """Lexical fallback for mapping a phrase onto a column name."""
    if not phrase or not candidates:
        return None
    norm = lambda s: re.sub(r"[^a-z0-9]", "", str(s).lower())
    target = norm(phrase)
    for candidate in candidates:
        if norm(candidate) == target:
            return candidate
    phrase_tokens = set(re.findall(r"[a-z0-9]+", str(phrase).lower()))
    best, best_overlap = None, 0
    for candidate in candidates:
        tokens = set(re.findall(r"[a-z0-9]+", candidate.lower()))
        overlap = len(tokens & phrase_tokens)
        if overlap > best_overlap:
            best, best_overlap = candidate, overlap
    return best


def _resolve_target_column(
    interpretation: dict,
    question: str,
    profile: DatasetProfile,
    df,
    inherited_target: str | None,
) -> tuple[str | None, str, list[str]]:
    """
    Settle the target column. Returns (column, how_it_was_resolved, candidates).

    Order of authority: an explicit column the interpreter named and the schema
    confirms, then a lexical match against this dataset's own measures and
    labels, then semantic matching through the dimension resolver's embedding
    layer, then whatever the conversation was already about.
    """
    all_targets = profile.measure_names + profile.label_names
    if not all_targets:
        return None, "none_available", []

    named = interpretation.get("target")
    if named and named in all_targets:
        return named, "interpreter", all_targets
    if named:
        matched = _match_by_words(named, all_targets)
        if matched:
            return matched, "interpreter_matched", all_targets

    phrase = interpretation.get("target_phrase")
    for text in (phrase, question):
        matched = _match_by_words(text, all_targets)
        if matched and text:
            # Require the match to be a real word of the text, not a coincidence.
            tokens = set(re.findall(r"[a-z0-9]+", str(text).lower()))
            if set(re.findall(r"[a-z0-9]+", matched.lower())) & tokens:
                return matched, "lexical", all_targets

    # Alias/synonym fallback, through the same resolution the detector uses.
    # A question about "revenue" names no column in a schema whose measure is
    # `amount`; token overlap cannot bridge that, but the target resolver can.
    for text in (phrase, question):
        aliased = _alias_target_match(text, profile.table, all_targets)
        if aliased:
            return aliased, "alias", all_targets

    # Semantic fallback: the word may not appear in any column name at all
    # (a question about "revenue" against a column called `turnover`).
    semantic = _semantic_target_match(phrase or question, profile, df)
    if semantic:
        return semantic, "semantic", all_targets

    if inherited_target and inherited_target in all_targets:
        return inherited_target, "inherited", all_targets

    return None, "unresolved", all_targets


def _alias_target_match(text: str | None, table: str, candidates: list[str]) -> str | None:
    """Resolve a measure word through the detector's schema-aware scoring."""
    if not text:
        return None
    try:
        from prediction import detector
        from prediction.service import _load_table

        detection = detector.detect(
            _load_table(table), table,
            target_hint=str(text), problem_type_hint="forecasting",
        )
        if detection.is_suitable and detection.target_column in candidates:
            return detection.target_column
    except Exception as exc:
        logger.debug("[ConfigResolver] Alias target match failed for %r: %s", text, exc)
    return None


def _semantic_target_match(text: str, profile: DatasetProfile, df) -> str | None:
    """Embedding similarity between the question and each measure's profile."""
    candidates = profile.measures + profile.labels
    if not candidates or not text:
        return None
    try:
        import numpy as np
        from services.embeddings import generate_embedding, generate_embeddings_batch

        docs = []
        for spec in candidates:
            sample = ", ".join(str(v) for v in spec.sample_values[:5])
            docs.append(f"{spec.column.replace('_', ' ')}. Values: {sample}")
        matrix = np.asarray(generate_embeddings_batch(docs))
        query = np.asarray(generate_embedding(text))
        scores = matrix @ query
        best = int(np.argmax(scores))
        if float(scores[best]) >= 0.25:
            return candidates[best].column
    except Exception as exc:
        logger.debug("[ConfigResolver] Semantic target match unavailable: %s", exc)
    return None


def _resolve_dimensions(
    requested: list[str],
    table: str,
    exclude: set[str],
) -> tuple[list[str], list[dict], list[str]]:
    """Resolve dimension names through the join-verified dimension resolver."""
    if not requested:
        return [], [], []

    from prediction.dimensions import resolve_dimensions

    resolution = resolve_dimensions(requested, table, exclude_columns=exclude)
    names = [d.hint for d in resolution.resolved]
    specs = [d.to_dim_info() for d in resolution.resolved]
    problems = [u["reason"] for u in resolution.unresolved]
    return names, specs, problems


# ──────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────

def resolve_config(
    question: str,
    *,
    table: str | None = None,
    scope_tables: list[str] | None = None,
    inherited: PredictionConfig | dict | None = None,
    allow_clarification: bool = True,
    force_prediction_type: str | None = None,
) -> PredictionConfig:
    """
    Build an executable PredictionConfig for a question.

    Args:
        question: the user's question, in any phrasing.
        table: the fact table, when the caller already knows it.
        scope_tables: the active data source's tables, used to pick one.
        inherited: the previous turn's config, whose slots are carried forward
            and overridden only where this question changes them.
        allow_clarification: when the target is genuinely ambiguous, return a
            clarification request instead of guessing.
        force_prediction_type: set by the task router. The router has already
            decided what kind of analysis this is, using signals and dataset
            capabilities; re-deciding here could contradict it.

    Returns:
        A PredictionConfig. Check ``status`` and ``is_executable`` before use.
    """
    inherited_cfg = _as_config(inherited)

    config = PredictionConfig(question=question)
    if inherited_cfg:
        config = _inherit(config, inherited_cfg)

    # ── 1. Dataset ──
    resolved_table = table or config.table
    if not resolved_table:
        resolved_table, _ = choose_dataset_table(scope_tables)
    if not resolved_table:
        config.status = cfg.STATUS_INVALID_CONFIG
        config.errors.append("No table in this data source contains a predictable measure.")
        return config
    config.table = resolved_table
    config.dataset_tables = scope_tables or [resolved_table]

    from prediction.service import _load_table
    df = _load_table(resolved_table)
    if df.empty:
        config.status = cfg.STATUS_INSUFFICIENT_DATA
        config.errors.append(f"Table '{resolved_table}' has no rows.")
        return config

    profile = build_profile(resolved_table, df)

    # ── 2. Interpret the question against this dataset ──
    context_block = ""
    if inherited_cfg:
        context_block = (
            "CONVERSATION CONTEXT — the previous prediction in this thread:\n"
            f"  target={inherited_cfg.target}, dimensions={inherited_cfg.group_dimensions}, "
            f"horizon={inherited_cfg.horizon} {inherited_cfg.time_frequency}\n"
            "Carry these forward unless the question changes them.\n\n"
        )
    interpretation = _call_interpreter(INTERPRETATION_PROMPT.format(
        profile=profile.summary_for_prompt(),
        context_block=context_block,
        question=question,
    ))

    # ── 3. Target ──
    target, how, candidates = _resolve_target_column(
        interpretation, question, profile, df, config.target or None,
    )
    if not target:
        # A question that names no measure is ambiguous, not invalid — asking
        # beats silently predicting whichever measure happens to be first.
        if allow_clarification and len(candidates) > 1:
            config.status = cfg.STATUS_NEEDS_CLARIFICATION
            config.clarification = {
                "question": "Which measure would you like me to predict?",
                "options": candidates,
                "reason": "The question does not say which quantity to predict.",
            }
            return config
        if len(candidates) == 1:
            target, how = candidates[0], "only_measure"
        else:
            config.status = cfg.STATUS_INVALID_CONFIG
            config.errors.append(
                "Could not tell which quantity to predict, and this dataset "
                "offers none that can be."
            )
            return config

    config.target = target
    config.target_request = interpretation.get("target_phrase") or question
    config.resolved_by["target"] = how

    # Ambiguity is only worth raising when the alternatives are real and the
    # question gave no strong signal.
    if allow_clarification and interpretation.get("ambiguous_target"):
        options = [c for c in (interpretation.get("candidate_targets") or []) if c in candidates]
        if len(options) > 1 and how not in ("interpreter", "lexical", "inherited"):
            config.status = cfg.STATUS_NEEDS_CLARIFICATION
            config.clarification = {
                "question": "Which measure would you like me to predict?",
                "options": options,
                "reason": "Several measures in this dataset match the words used.",
            }
            return config

    target_spec = resolve_target(target, df, has_time_axis=profile.has_time_axis)
    config.target_semantics = {
        "dtype": target_spec.dtype,
        "semantic_role": target_spec.semantic_role,
        "n_distinct": target_spec.n_distinct,
        "is_binary": target_spec.is_binary,
        "is_continuous": target_spec.is_continuous,
        "supported": list(target_spec.supported_prediction_types),
        "reason": target_spec.reason,
    }

    # ── 4. Prediction type ──
    wants_future = bool(interpretation.get("asks_about_future", _asks_about_future(question)))
    prediction_type, type_reason = resolve_prediction_type(
        target_spec, wants_future=wants_future, requested=force_prediction_type,
    )
    if force_prediction_type and prediction_type != force_prediction_type:
        config.warnings.append(
            f"The task router asked for {force_prediction_type}, but "
            f"'{target}' supports {', '.join(target_spec.supported_prediction_types) or 'nothing'}; "
            f"using {prediction_type}."
        )
    if prediction_type is None:
        config.status = cfg.STATUS_INVALID_CONFIG
        config.errors.append(f"'{target}' cannot be predicted. {target_spec.reason}")
        return config
    config.prediction_type = prediction_type
    config.resolved_by["prediction_type"] = type_reason

    # ── 5. Time axis, frequency, horizon (forecasting only) ──
    if prediction_type == cfg.FORECASTING:
        selected, all_times = select_time_column(
            df, question=question, preferred=interpretation.get("time_column"),
        )
        if selected is None:
            config.status = cfg.STATUS_INVALID_CONFIG
            config.errors.append("Forecasting needs a time column and none was found.")
            return config

        config.time_column = selected.column
        config.history_start, config.history_end = selected.min_date, selected.max_date
        config.resolved_by["time_column"] = (
            f"{selected.column} (span {selected.span_days:.0f} days, "
            f"~{selected.inferred_frequency})"
        )
        if len(all_times) > 1:
            config.warnings.append(
                f"{len(all_times)} time columns available "
                f"({', '.join(t.column for t in all_times[:4])}); using {selected.column}."
            )

        requested_unit = interpretation.get("horizon_unit")
        frequency, freq_notes = resolve_frequency(
            requested_unit if requested_unit in (
                "days", "weeks", "months", "quarters", "years") else None,
            selected.inferred_frequency,
            span_days=selected.span_days,
        )
        # A coarse unit ("next year") states a span, not a bucket size; the
        # bucket stays at the data's own resolution.
        if requested_unit in ("years", "quarters") and frequency == selected.inferred_frequency:
            freq_notes = [n for n in freq_notes if "requested" not in n]
        config.time_frequency = frequency
        config.warnings.extend(freq_notes)

        stated_count = interpretation.get("horizon_count")
        stated_phrase = None
        from prediction.time_resolution import parse_horizon_phrase
        if stated_count is None and not requested_unit:
            stated_phrase = parse_horizon_phrase(question)

        inherited_horizon = (
            inherited_cfg.horizon
            if inherited_cfg and inherited_cfg.horizon
            and inherited_cfg.time_frequency == frequency
            else None
        )
        horizon = resolve_horizon(
            question, frequency, selected.max_date,
            requested_periods=stated_count,
            requested_unit=requested_unit,
            # A follow-up that says nothing about timing is still asking about
            # the same period as the question before it.
            default_periods=inherited_horizon or 6,
        )
        if (inherited_horizon and stated_count is None and not requested_unit
                and not (stated_phrase and stated_phrase[0])):
            horizon.periods = inherited_horizon
            horizon.source = "inherited"
        config.horizon = horizon.periods
        config.forecast_start, config.forecast_end = horizon.forecast_start, horizon.forecast_end
        config.resolved_by["horizon"] = horizon.source
        config.warnings.extend(horizon.warnings)

    # ── 6. Dimensions ──
    requested_dims = [d for d in (interpretation.get("group_dimensions") or []) if d]
    if inherited_cfg:
        requested_dims, config.dimension_origin, dim_note = _resolve_dimension_change(
            question, requested_dims, inherited_cfg, interpretation,
        )
        if dim_note:
            config.warnings.append(dim_note)
        config.resolved_by["dimensions"] = config.dimension_origin

    exclude = {config.target}
    if config.time_column:
        exclude.add(config.time_column)

    if not requested_dims:
        # Interpretation named no grouping. Infer one from the question itself
        # before giving up — a question that says "by country" is asking to be
        # grouped whether or not the interpreter reported it.
        from prediction.dimensions import infer_dimensions

        # The words that named the measure are not candidates for grouping.
        # Only the words that actually *named* the measure — the column and any
        # phrase the interpreter identified. `target_request` falls back to the
        # whole question when interpretation returns nothing, and excluding
        # every word of the question left no candidates at all, which is how
        # "Which country ... ?" lost its grouping and fell back to a single
        # ungrouped series.
        target_words = set(re.findall(r"[a-z0-9]+", (config.target or "").lower()))
        target_words |= set(re.findall(
            r"[a-z0-9]+", (interpretation.get("target_phrase") or "").lower()))

        inferred = infer_dimensions(
            question, config.table, exclude_columns=exclude,
            exclude_words=target_words,
        )
        if inferred:
            config.group_dimensions = [d.hint for d in inferred]
            config.dimension_specs = [d.to_dim_info() for d in inferred]
            config.resolved_by["dimensions"] = "inferred_from_question"

    names, specs, problems = _resolve_dimensions(requested_dims, config.table, exclude)
    if not requested_dims and config.dimension_specs:
        names, specs = config.group_dimensions, config.dimension_specs
    config.group_dimensions, config.dimension_specs = names, specs
    for problem in problems:
        config.warnings.append(f"Dimension not resolved: {problem}")
    if requested_dims and not names:
        config.status = cfg.STATUS_INVALID_CONFIG
        config.errors.append(
            f"None of the requested groupings ({', '.join(requested_dims)}) could be "
            f"matched to a column joinable to '{config.table}'."
        )
        return config

    # ── 7. Filters ──
    for raw in interpretation.get("filters") or []:
        column, values = raw.get("column"), raw.get("values")
        if column and values:
            config.filters.append(Filter(column=column, operator="in",
                                         values=list(values), dimension=column))

    # ── 8. Operations ──
    operations: list[str] = []
    if interpretation.get("wants_ranking", bool(_RANK_MARKERS.search(question))):
        operations.append(cfg.OP_RANK)
    growth_in_words = bool(_GROWTH_MARKERS.search(question))
    comparison_in_words = bool(_COMPARE_MARKERS.search(question))
    wants_growth = interpretation.get("wants_growth", growth_in_words)

    # Persistence and growth are different questions, and interpretation
    # sometimes conflates them: "will they remain the same" is about whether
    # the ranking holds, not about growth rates. When the wording carries no
    # growth vocabulary but does ask about persistence, the persistence
    # reading wins — otherwise the answer silently changes metric.
    if wants_growth and not growth_in_words and comparison_in_words:
        wants_growth = False
        config.warnings.append(
            "Read as a question about whether the ranking persists, not about "
            "growth rates."
        )

    if wants_growth:
        operations.append(cfg.OP_GROWTH)
        config.ranking_metric = "growth"
        if cfg.OP_RANK not in operations:
            operations.append(cfg.OP_RANK)
    if interpretation.get("wants_comparison_with_present",
                          bool(_COMPARE_MARKERS.search(question))):
        if config.ranking_metric == "growth":
            # "Current top 3 by revenue" versus "top 3 by growth rate" are not
            # the same list measured twice; comparing them would imply a
            # change of position that was never measured.
            config.warnings.append(
                "A current-versus-future comparison was not included: the ranking "
                "is by growth rate, which is not comparable with historical levels."
            )
        else:
            operations.append(cfg.OP_COMPARE)
            config.compare_against = "history"
            if cfg.OP_RANK not in operations:
                operations.append(cfg.OP_RANK)

    if interpretation.get("wants_final_period_only",
                          bool(_FINAL_PERIOD_MARKERS.search(question))):
        operations.append(cfg.OP_FINAL_PERIOD)
        if cfg.OP_RANK not in operations:
            operations.append(cfg.OP_RANK)

    top_n = interpretation.get("top_n")
    if top_n is None:
        match = re.search(r"\btop\s+(\d+)\b", question, re.IGNORECASE)
        top_n = int(match.group(1)) if match else None
    if top_n:
        config.top_n = int(top_n)
        if cfg.OP_TOP_N not in operations:
            operations.append(cfg.OP_TOP_N)

    config.operations = operations
    config.growth_baseline_periods = config.horizon or None

    # ── 9. Structural quality gate ──
    config.errors.extend(validate_config(config))
    if config.errors:
        config.status = cfg.STATUS_INVALID_CONFIG

    logger.info("[ConfigResolver] %s", config.describe())
    return config


#: Wording that asks for a *different* grouping: "by region", "per team",
#: "instead", "split/broken down by". These replace the previous grouping.
_REGROUP_SIGNAL = re.compile(
    r"\b(?:by|per|across|for\s+each|for\s+every|group(?:ed)?\s+by|split\s+by|"
    r"broken\s+down\s+by|break\s+(?:it\s+)?down\s+by|instead|rather\s+than|"
    r"switch\s+to|change\s+to)\b",
    re.I,
)

#: Wording that asks to expand *within* the current grouping: "their products",
#: "each of them", "within those". These add a level, keeping the outer one.
_DRILLDOWN_SIGNAL = re.compile(
    r"\b(?:their|its|each\s+of\s+(?:them|those|these)|within|inside|"
    r"drill\s*(?:down)?|broken\s+down|breakdown)\b",
    re.I,
)


def _mentions_dimension(question: str, dimension: str) -> bool:
    """
    Whether the question actually names ``dimension``.

    Matching is on word stems so "products" satisfies a "product" hint and a
    qualified hint like "geo.country" is matched on its parts. This is the
    check that stops a grouping the user never uttered from being added.
    """
    stems: set[str] = set()
    for word in re.findall(r"[a-z0-9]+", question.lower()):
        if len(word) > 2:
            stems |= _stems(word)
    for part in re.split(r"[^a-z0-9]+", dimension.lower()):
        if len(part) > 2 and _stems(part) & stems:
            return True
    return False


def _stems(word: str) -> set[str]:
    """
    Plural/singular variants of a word, so "categories" meets "category".

    Only the English noun endings that appear in column names are handled;
    anything subtler belongs to the embedding-based resolver, not here.
    """
    forms = {word}
    if word.endswith("ies") and len(word) > 4:
        forms.add(word[:-3] + "y")
    if word.endswith("es") and len(word) > 3:
        forms.add(word[:-2])
    if word.endswith("s") and len(word) > 2:
        forms.add(word[:-1])
    if word.endswith("y") and len(word) > 2:
        forms.add(word[:-1] + "ies")
    return forms


def _resolve_dimension_change(
    question: str,
    requested_dims: list[str],
    inherited_cfg: PredictionConfig,
    interpretation: dict,
) -> tuple[list[str], str, str]:
    """
    Decide the grouping of a follow-up, and say how it was decided.

    A follow-up inherits the previous granularity unless the *question* asks to
    change it. The interpreter's opinion alone is not enough: an LLM reading a
    country-level result will readily propose grouping by product because
    products appeared in the source rows, which silently answers a different
    question than the one asked. So a proposed dimension is honoured only when
    the question names it, or when the question carries wording that asks for a
    re-grouping at all.

    Returns ``(dimensions, origin, note)`` where origin is one of
    ``inherited`` / ``replaced`` / ``drilldown``.
    """
    previous = list(inherited_cfg.group_dimensions)

    if not requested_dims:
        # Nothing proposed: the question is continuing at the current level.
        return previous, "inherited", ""

    regroup = bool(_REGROUP_SIGNAL.search(question))
    drilldown = bool(_DRILLDOWN_SIGNAL.search(question))

    # Keep only what the user can be shown to have asked for. When the question
    # carries an explicit grouping phrase we trust the interpreter's naming
    # (it may have mapped "nation" onto a `country` column); without one, the
    # dimension has to appear in the question itself.
    if regroup or drilldown:
        asked = list(requested_dims)
    else:
        asked = [d for d in requested_dims if _mentions_dimension(question, d)]

    unasked = [d for d in requested_dims if d not in asked]
    note = ""
    if unasked:
        note = (
            f"Ignored grouping the question did not ask for ({', '.join(unasked)}); "
            f"kept the previous granularity ({inherited_cfg.result_granularity})."
        )

    if not asked:
        return previous, "inherited", note

    if drilldown and previous:
        # Expansion under the existing grouping: the outer level stays.
        merged = previous + [d for d in asked if d not in previous]
        return merged, "drilldown", note

    return asked, "replaced", note


def _inherit(config: PredictionConfig, previous: PredictionConfig) -> PredictionConfig:
    """Carry forward every slot a follow-up might not restate."""
    config.table = previous.table
    config.dataset_tables = list(previous.dataset_tables)
    config.target = previous.target
    config.aggregation = previous.aggregation
    config.time_column = previous.time_column
    config.time_frequency = previous.time_frequency
    config.horizon = previous.horizon
    config.group_dimensions = list(previous.group_dimensions)
    config.dimension_specs = [dict(s) for s in previous.dimension_specs]
    config.filters = list(previous.filters)
    config.model_strategy = previous.model_strategy
    config.confidence_level = previous.confidence_level
    config.source_entities = list(previous.source_entities)
    config.source_leader = previous.source_leader
    return config


def _as_config(value: PredictionConfig | dict | None) -> PredictionConfig | None:
    if value is None:
        return None
    if isinstance(value, PredictionConfig):
        return value
    if isinstance(value, dict):
        known = {f.name for f in PredictionConfig.__dataclass_fields__.values()}
        payload = {k: v for k, v in value.items() if k in known}
        payload.pop("filters", None)   # rebuilt from scratch each turn
        try:
            return PredictionConfig(**payload)
        except TypeError:
            return None
    return None
