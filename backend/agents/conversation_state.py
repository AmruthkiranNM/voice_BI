"""
Structured conversational state for predictions.

A follow-up like "Will it remain the leader next year?" contains no measure, no
dimension and no entity — every one of those has to come from the turn before
it. Reconstructing them from the previous *answer text*, or from a SQL result's
column aliases, is what made these questions fail: `total_revenue` and `GEO` are
names the answer invented, not columns the table has.

This module builds a ``PredictionConfig`` seed from whatever the previous turn
was, mapping it back onto real schema columns:

  * a previous **prediction** already carries its config, so it is inherited whole;
  * a previous **BI/SQL answer** is mapped back — its measure column to a real
    measure, its grouping column to a real dimension — and the entities it
    returned are carried as context.

Nothing here matches question text. It reads the shape of the previous result
and resolves each piece against the live schema.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from prediction.config import PredictionConfig

logger = logging.getLogger(__name__)


def _tokens(text: Any) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", str(text).lower()) if t}


def _numeric_share(rows: list[dict], column: str) -> float:
    """Fraction of a result column's values that are numbers."""
    if not rows:
        return 0.0
    numeric = 0
    for row in rows[:200]:
        value = row.get(column)
        if value is None:
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            numeric += 1
        else:
            try:
                float(str(value).replace(",", "").replace("$", ""))
                numeric += 1
            except (TypeError, ValueError):
                pass
    return numeric / max(1, min(len(rows), 200))


def _match_column(alias: str, candidates: list[str]) -> str | None:
    """
    Map a result column alias onto a real schema column.

    A SQL answer names its columns whatever the query aliased them
    ("total_revenue", "highest_boxes", "GEO"), so matching is on tokens rather
    than on equality.
    """
    if not alias or not candidates:
        return None

    alias_norm = re.sub(r"[^a-z0-9]", "", alias.lower())
    for candidate in candidates:
        if re.sub(r"[^a-z0-9]", "", candidate.lower()) == alias_norm:
            return candidate

    alias_tokens = _tokens(alias)
    best, best_score = None, 0
    for candidate in candidates:
        overlap = len(alias_tokens & _tokens(candidate))
        if overlap > best_score:
            best, best_score = candidate, overlap
    return best


def _resolve_measure(text: str, table: str, measure_names: list[str]) -> str | None:
    """
    Map a SQL alias or a phrase onto a real measure column.

    A result column called ``total_revenue`` has no token in common with a
    column called ``amount``, so plain overlap cannot connect them. This
    delegates to the same semantic target resolution the rest of the system
    uses, which knows — from the schema and from value profiles, not from a
    per-question rule — that those are the same quantity.
    """
    if not text or not measure_names:
        return None

    direct = _match_column(text, measure_names)
    if direct:
        return direct

    try:
        from prediction import detector
        from prediction.service import _load_table

        detection = detector.detect(
            _load_table(table), table,
            target_hint=str(text), problem_type_hint="forecasting",
        )
        if detection.is_suitable and detection.target_column in measure_names:
            return detection.target_column
    except Exception as exc:
        logger.debug("[ConversationState] Semantic measure match failed for %r: %s", text, exc)
    return None


def _resolve_dimensions(aliases: list[str], table: str, known: list[str]) -> list[str]:
    """Map result column aliases onto grouping dimensions the engine can use."""
    resolved: list[str] = []
    unmatched: list[str] = []

    for alias in aliases:
        direct = _match_column(alias, known)
        if direct and direct not in resolved:
            resolved.append(direct)
        elif not direct:
            unmatched.append(alias)

    if unmatched:
        try:
            from prediction.dimensions import resolve_dimensions

            resolution = resolve_dimensions(unmatched, table)
            for dimension in resolution.resolved:
                # Keep the user-facing word ("country"); the engine re-resolves
                # it to the physical column when it builds the forecast.
                if dimension.hint not in resolved:
                    resolved.append(dimension.hint)
        except Exception as exc:
            logger.debug("[ConversationState] Dimension resolution failed: %s", exc)

    return resolved


def seed_from_prediction(stored_config: dict) -> PredictionConfig | None:
    """Inherit a previous prediction's configuration verbatim."""
    if not stored_config:
        return None
    known = set(PredictionConfig.__dataclass_fields__)
    payload = {k: v for k, v in stored_config.items() if k in known}
    payload.pop("filters", None)
    payload.pop("status", None)
    payload.pop("errors", None)
    payload.pop("clarification", None)
    try:
        return PredictionConfig(**payload)
    except TypeError as exc:
        logger.warning("[ConversationState] Could not rebuild config: %s", exc)
        return None


def seed_from_bi_result(
    result: dict,
    table: str,
    question: str = "",
) -> PredictionConfig | None:
    """
    Build a prediction seed from a historical SQL answer.

    The previous result's shape tells us what the conversation is about: its
    numeric column is the measure being discussed, its categorical column is
    the dimension, and its rows are the entities. Each is mapped back onto a
    real schema column so a forecast can be built from the same thing the user
    was just looking at.
    """
    from prediction.profiler import build_profile

    rows = result.get("rows") or []
    columns = result.get("columns") or (list(rows[0]) if rows else [])
    if not columns:
        return None

    try:
        profile = build_profile(table)
    except Exception as exc:
        logger.warning("[ConversationState] Could not profile '%s': %s", table, exc)
        return None

    measure_names = profile.measure_names
    dimension_names = [d["column"] for d in profile.dimensions]

    # Classify the result's own columns by their values, not their names.
    numeric_cols = [c for c in columns if _numeric_share(rows, c) > 0.8]
    label_cols = [c for c in columns if c not in numeric_cols]

    target = None
    for alias in numeric_cols:
        target = _resolve_measure(alias, table, measure_names)
        if target:
            break
    if not target:
        # The answer may have aliased the measure past recognition; fall back
        # to the question's own words before giving up on it entirely.
        target = _resolve_measure(question, table, measure_names)

    dimensions: list[str] = []
    if label_cols:
        # Resolve through the same join-verified dimension resolver the engine
        # uses. A result column aliased "country" shares no token with the
        # column that holds countries, so token overlap alone cannot connect
        # them — the resolver can, from the column's values.
        dimensions = _resolve_dimensions(label_cols, table, dimension_names)

    if not target and not dimensions:
        return None

    seed = PredictionConfig(table=table)
    if target:
        seed.target = target
    if dimensions:
        seed.group_dimensions = dimensions

    # Entities and the current leader, so "will *it* remain the leader" has
    # something concrete to refer to.
    if label_cols and rows:
        entity_column = label_cols[0]
        seed.source_entities = [str(r.get(entity_column)) for r in rows[:25]
                                if r.get(entity_column) is not None]
        if numeric_cols:
            measure_column = numeric_cols[0]

            def _value(row):
                try:
                    return float(str(row.get(measure_column, 0)).replace(",", "").replace("$", ""))
                except (TypeError, ValueError):
                    return float("-inf")

            ranked = sorted(rows, key=_value, reverse=True)
            if ranked:
                seed.source_leader = str(ranked[0].get(entity_column))

    logger.info(
        "[ConversationState] Seed from BI result: target=%s dimensions=%s leader=%s",
        seed.target, seed.group_dimensions, seed.source_leader,
    )
    return seed


def build_seed(
    context: dict,
    table: str | None = None,
) -> PredictionConfig | None:
    """
    Build the inherited configuration for a follow-up, whatever came before it.

    Args:
        context: the chat context ({query, sql, result, table_name, table_names}).
        table: the fact table, when already known.

    Returns:
        A PredictionConfig seed, or None when the previous turn carried nothing
        a prediction could be built from.
    """
    result = context.get("result") or {}

    stored = result.get("config") or context.get("prediction_config")
    if stored:
        seed = seed_from_prediction(stored)
        if seed:
            return seed

    resolved_table = table or result.get("table_name") or context.get("table_name")
    if not resolved_table:
        resolved_table = _table_from_sql(context.get("sql"))
    if not resolved_table:
        scope = context.get("table_names") or []
        if scope:
            from prediction.profiler import choose_dataset_table
            resolved_table, _ = choose_dataset_table(scope)
    if not resolved_table:
        return None

    return seed_from_bi_result(result, resolved_table, context.get("query", ""))


def _table_from_sql(sql: str | None) -> str | None:
    """
    Recover the fact table from the SQL that produced the previous answer.

    The largest table referenced is the fact table: a star-schema query joins
    one fact table to several small lookups.
    """
    if not sql:
        return None
    referenced = set(re.findall(r"\b(?:FROM|JOIN)\s+\[?\"?([A-Za-z_][A-Za-z0-9_]*)", sql, re.IGNORECASE))
    if not referenced:
        return None

    try:
        from services.database import get_all_table_names, get_table_row_count
        real = {t.lower(): t for t in get_all_table_names()}
        sized = []
        for name in referenced:
            actual = real.get(name.lower())
            if actual:
                sized.append((get_table_row_count(actual), actual))
        if sized:
            return max(sized)[1]
    except Exception as exc:
        logger.debug("[ConversationState] Could not size SQL tables: %s", exc)
    return None
