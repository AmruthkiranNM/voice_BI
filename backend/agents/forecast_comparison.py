"""
Deterministic ranking comparison for forecast follow-ups.

"Will the top 3 countries remain the same next year?" is a set comparison
between two rankings, and it is arithmetic — no language model is involved in
deciding who is in the top 3 or whether the set changed.

One module so that every agent that answers a future-ranking question gets the
same answer. Previously the comparison was reimplemented in two agents against
two different field names, and both read a field the result does not have.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class RankedEntry:
    """One group's position and value in a ranking."""
    rank: int
    group: str
    value: float | None
    group_dict: dict[str, str] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class RankingComparison:
    """Outcome of comparing a current top-N against a forecast top-N."""
    top_n: int
    current_top: list[RankedEntry] = dataclasses.field(default_factory=list)
    future_top: list[RankedEntry] = dataclasses.field(default_factory=list)
    unchanged_set: bool = False          # same members, any order
    unchanged_order: bool = False        # same members, same order
    held: list[str] = dataclasses.field(default_factory=list)
    entered: list[str] = dataclasses.field(default_factory=list)
    left: list[str] = dataclasses.field(default_factory=list)
    rank_changes: dict[str, tuple[int | None, int | None]] = dataclasses.field(default_factory=dict)
    n_ranked: int = 0                    # how many groups were forecast in total
    n_excluded: int = 0


def extract_forecast_ranking(prediction: Any) -> list[RankedEntry]:
    """
    Read the ranked groups out of a prediction result.

    Accepts either a UniversalPredictionResult or its ``asdict`` form, and
    reads ``raw_forecast_results`` — the field that actually holds grouped
    forecasts. Groups without a forecast value are skipped rather than ranked
    as zero.
    """
    entries = _get(prediction, "raw_forecast_results") or _get(prediction, "forecast_ranking") or []

    ranked: list[RankedEntry] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        value = item.get("final_value")
        if value is None:
            continue
        ranked.append(RankedEntry(
            rank=0,
            group=str(item.get("group", "")),
            value=float(value),
            group_dict=dict(item.get("group_dict") or {}),
        ))

    ranked.sort(key=lambda e: e.value, reverse=True)
    for i, entry in enumerate(ranked, start=1):
        entry.rank = i
    return ranked


def rank_historical_rows(
    rows: list[dict],
    dimension: str,
    target: str,
) -> list[RankedEntry]:
    """
    Aggregate already-returned BI rows into a ranking over one dimension.

    Used to establish "the current top 3" from the historical result the user
    is looking at, without re-querying the database.
    """
    totals: dict[str, float] = {}
    for row in rows or []:
        key = row.get(dimension)
        if key is None:
            # Column names round-trip through SQL in varying case.
            for candidate, value in row.items():
                if candidate.lower() == str(dimension).lower():
                    key = value
                    break
        if key is None:
            continue
        raw = row.get(target)
        if raw is None:
            for candidate, value in row.items():
                if candidate.lower() == str(target).lower():
                    raw = value
                    break
        try:
            amount = float(raw)
        except (TypeError, ValueError):
            continue
        totals[str(key)] = totals.get(str(key), 0.0) + amount

    ranked = [RankedEntry(rank=0, group=g, value=v, group_dict={dimension: g})
              for g, v in totals.items()]
    ranked.sort(key=lambda e: e.value, reverse=True)
    for i, entry in enumerate(ranked, start=1):
        entry.rank = i
    return ranked


def compare_rankings(
    current: list[RankedEntry],
    future: list[RankedEntry],
    top_n: int = 3,
    n_excluded: int = 0,
) -> RankingComparison:
    """
    Compare the current top-N against the forecast top-N.

    Both rankings are computed over *every* eligible group, then sliced. That
    ordering matters: forecasting only the current leaders and re-ranking them
    can never surface a group that overtakes from below.
    """
    current_top = current[:top_n]
    future_top = future[:top_n]

    current_names = [e.group for e in current_top]
    future_names = [e.group for e in future_top]
    current_set, future_set = set(current_names), set(future_names)

    current_rank = {e.group: e.rank for e in current}
    future_rank = {e.group: e.rank for e in future}

    comparison = RankingComparison(
        top_n=top_n,
        current_top=current_top,
        future_top=future_top,
        unchanged_set=current_set == future_set,
        unchanged_order=current_names == future_names,
        held=[g for g in current_names if g in future_set],
        entered=[g for g in future_names if g not in current_set],
        left=[g for g in current_names if g not in future_set],
        n_ranked=len(future),
        n_excluded=n_excluded,
    )
    for group in current_set | future_set:
        comparison.rank_changes[group] = (current_rank.get(group), future_rank.get(group))
    return comparison


def format_comparison(
    comparison: RankingComparison,
    target: str,
    dimension_label: str,
    horizon_label: str = "the forecast horizon",
) -> str:
    """
    Render the comparison as deterministic evidence text.

    Every number here comes from the arithmetic above. This text is what the
    explanation layer is allowed to paraphrase — and what it falls back to if
    the generated wording cannot be verified.
    """
    lines: list[str] = []

    # "Will it stay on top?" is answerable from the two rankings alone, so the
    # answer is stated first and derived here rather than left for the wording
    # layer to infer from the lists below.
    current_leader = comparison.current_top[0] if comparison.current_top else None
    future_leader = comparison.future_top[0] if comparison.future_top else None
    if current_leader and future_leader:
        retained = current_leader.group == future_leader.group
        lines.append(
            f"ANSWER: {'Yes' if retained else 'No'} — the leading {dimension_label} "
            f"by {target} is forecast to "
            + (f"remain {current_leader.group}." if retained
               else f"change from {current_leader.group} to {future_leader.group}.")
        )
        lines.append(f"CURRENT LEADER: {current_leader.group} ({current_leader.value:,.2f}, observed)")
        lines.append(f"FORECAST LEADER: {future_leader.group} ({future_leader.value:,.2f}, {horizon_label})")
        lines.append(f"REPORTED AT: {dimension_label} level")
        lines.append("")

    lines.append(f"CURRENT TOP {comparison.top_n} {dimension_label.upper()} BY {target.upper()} (observed):")
    for e in comparison.current_top:
        lines.append(f"  {e.rank}. {e.group}: {e.value:,.2f}")

    lines.append("")
    lines.append(f"FORECAST TOP {comparison.top_n} FOR {horizon_label.upper()} (model output):")
    for e in comparison.future_top:
        lines.append(f"  {e.rank}. {e.group}: {e.value:,.2f}")

    lines.append("")
    lines.append(
        f"COMPARISON (all {comparison.n_ranked} eligible {dimension_label} were forecast "
        f"and ranked before this top {comparison.top_n} was taken"
        + (f"; {comparison.n_excluded} had too little history to forecast" if comparison.n_excluded else "")
        + "):"
    )
    if comparison.unchanged_order:
        lines.append(f"  The same {dimension_label} hold the top {comparison.top_n}, in the same order.")
    elif comparison.unchanged_set:
        lines.append(
            f"  The same {dimension_label} remain in the top {comparison.top_n}, but their order changes."
        )
    else:
        if comparison.left:
            lines.append(f"  Leaves the top {comparison.top_n}: {', '.join(comparison.left)}.")
        if comparison.entered:
            lines.append(f"  Enters the top {comparison.top_n}: {', '.join(comparison.entered)}.")
        if comparison.held:
            lines.append(f"  Remains in the top {comparison.top_n}: {', '.join(comparison.held)}.")

    for group, (before, after) in sorted(comparison.rank_changes.items()):
        if before is not None and after is not None and before != after:
            lines.append(f"  {group}: rank {before} -> {after}.")
        elif before is None and after is not None:
            lines.append(f"  {group}: not previously ranked -> rank {after}.")
        elif before is not None and after is None:
            lines.append(f"  {group}: rank {before} -> not in the forecast ranking.")

    return "\n".join(lines)


def compute_growth(
    historical: list[dict],
    forecast: list[dict],
    horizon: int,
) -> dict[str, Any]:
    """
    Growth of a forecast against a like-for-like historical baseline.

    Returns the parts as well as the percentage, so an explanation can state
    the baseline and the forecast it came from rather than only the ratio.
    ``growth_pct`` is None when the baseline is absent or non-positive — an
    undefined percentage is reported as undefined, never as zero or infinity.
    """
    observed = [r for r in (historical or []) if r.get("value") is not None]
    forecast_values = [r["value"] for r in (forecast or []) if r.get("value") is not None]

    baseline_rows = observed[-min(len(observed), horizon):] if observed else []
    baseline_total = sum(r["value"] for r in baseline_rows) if baseline_rows else None
    forecast_total = sum(forecast_values) if forecast_values else None

    result = {
        "baseline_total": baseline_total,
        "baseline_periods": len(baseline_rows),
        "forecast_total": forecast_total,
        "forecast_periods": len(forecast_values),
        "absolute_change": None,
        "growth_pct": None,
        "reason": "",
    }

    if baseline_total is None or forecast_total is None:
        result["reason"] = "Not enough observed or forecast periods to compute growth."
        return result
    if baseline_total <= 0:
        result["reason"] = (
            f"The historical baseline is {baseline_total:,.2f}; a growth percentage "
            "against a non-positive baseline is undefined."
        )
        result["absolute_change"] = forecast_total - baseline_total
        return result

    result["absolute_change"] = forecast_total - baseline_total
    result["growth_pct"] = ((forecast_total - baseline_total) / baseline_total) * 100.0
    return result


def _get(obj: Any, name: str):
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)
