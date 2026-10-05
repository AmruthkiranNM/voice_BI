"""
Deterministic facts about a query result.

The LLM must never compute numbers or decide an ordering: it misreads row
order (rows sorted by name are not sorted by value) and gets "highest" and
"lowest" wrong. Rankings are computed here and handed to it as facts, and
simple extremum follow-ups ("which one is the lowest?") are answered without
an LLM at all.
"""
from __future__ import annotations

import re

_MAX_WORDS = ("highest", "most", "largest", "biggest", "maximum", "max", "top",
              "best", "greatest", "leading", "first")
_MIN_WORDS = ("lowest", "least", "smallest", "minimum", "min", "bottom",
              "worst", "fewest", "last", "weakest")

# Words that may appear in a follow-up that only points back at the shown
# result. Anything else (a new dimension, a filter, a year) means the
# question needs a fresh query, so it is not answered here.
_REFERENCE_WORDS = {
    "which", "what", "who", "where", "one", "ones", "is", "was", "are", "were",
    "the", "a", "an", "of", "them", "these", "those", "among", "in", "has",
    "had", "have", "with", "and", "value", "item", "entry", "row", "please",
    "tell", "me", "show", "out", "it", "that", "this", "by", "for",
}

_MONETARY = ("amount", "revenue", "sales", "price", "cost", "salary",
             "balance", "income", "profit", "spend", "value")


def _is_number(v) -> bool:
    if isinstance(v, bool) or v is None:
        return False
    if isinstance(v, (int, float)):
        return True
    try:
        float(str(v).replace(",", ""))
        return True
    except ValueError:
        return False


def _num(v) -> float:
    return float(v) if isinstance(v, (int, float)) else float(str(v).replace(",", ""))


def split_columns(rows: list[dict]) -> tuple[str | None, list[str]]:
    """(label column, numeric columns) of a result, judged on every row."""
    if not rows:
        return None, []
    cols = list(rows[0].keys())
    numeric = [c for c in cols
               if all(r.get(c) is None or _is_number(r.get(c)) for r in rows)
               and any(r.get(c) is not None for r in rows)]
    labels = [c for c in cols if c not in numeric]
    return (labels[0] if labels else None), numeric


def format_value(value: float, column: str) -> str:
    text = f"{value:,.2f}".rstrip("0").rstrip(".") if value != int(value) else f"{int(value):,}"
    return f"${text}" if any(w in column.lower() for w in _MONETARY) else text


def ranked(rows: list[dict], label: str, metric: str) -> list[tuple[str, float]]:
    """Rows with a value for `metric`, highest first. Missing values are skipped, not zero."""
    pairs = [(str(r.get(label)), _num(r[metric])) for r in rows if r.get(metric) is not None]
    return sorted(pairs, key=lambda p: p[1], reverse=True)


_PERIOD = re.compile(r"^\d{4}(-\d{2}(-\d{2})?|-?Q[1-4]|-W\d{2})?$")


def period_changes(rows: list[dict], label: str, metric: str, max_items: int = 40) -> str:
    """
    Period-over-period changes when the label is a time period (2021, 2021-03,
    2021-03-15, 2021-Q1), in chronological order. A missing value breaks the
    chain rather than counting as zero.
    """
    keys = [str(r.get(label) or "") for r in rows]
    if len(keys) < 2 or not all(_PERIOD.match(k) for k in keys):
        return ""
    series = sorted((k, r.get(metric)) for k, r in zip(keys, rows))
    parts = []
    for (k0, v0), (k1, v1) in zip(series, series[1:]):
        if v0 is None or v1 is None:
            parts.append(f"{k1}: n/a (missing data)")
            continue
        a, b = _num(v0), _num(v1)
        diff = b - a
        pct = f"{diff / abs(a) * 100:+.1f}%" if a else "n/a (previous is 0)"
        sign = "+" if diff >= 0 else "-"
        parts.append(f"{k1} vs {k0}: {sign}{format_value(abs(diff), metric)} ({pct})")
    (kf, vf), (kl, vl) = series[0], series[-1]
    if vf is not None and vl is not None and _num(vf):
        a, b = _num(vf), _num(vl)
        sign = "+" if b >= a else "-"
        parts.append(f"OVERALL {kl} vs {kf}: {sign}{format_value(abs(b - a), metric)} "
                     f"({(b - a) / abs(a) * 100:+.1f}%)")
    return "; ".join(parts[-max_items:])


def facts_block(rows: list[dict], max_items: int = 30) -> str:
    """Pre-computed ranking text for an LLM prompt; '' when not applicable."""
    label, metrics = split_columns(rows)
    if not label or not metrics or len(rows) < 2:
        return ""
    lines = ["COMPUTED FACTS (calculated by code; authoritative. Use these for any "
             "highest/lowest/ranking statement - do NOT infer order from row order. "
             "Do NOT state any difference, percentage, total or average that is not "
             "listed here or in the rows):"]
    for metric in metrics:
        order = ranked(rows, label, metric)
        if len(order) < 2:
            continue
        shown = ", ".join(f"{i}. {n} = {format_value(v, metric)}"
                          for i, (n, v) in enumerate(order[:max_items], 1))
        lines.append(f"- {metric}, highest to lowest: {shown}")
        lines.append(f"  Highest {metric}: {order[0][0]}. Lowest {metric}: {order[-1][0]}.")
        changes = period_changes(rows, label, metric)
        if changes:
            lines.append(f"- {metric}, change from the previous period (use these exact "
                         f"percentages; do not calculate your own): {changes}")
    return "\n".join(lines) if len(lines) > 1 else ""


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def answer_extremum(message: str, rows: list[dict]) -> str | None:
    """
    Answer "which one is the lowest/highest?" over the shown result.

    Returns None whenever the question asks for anything beyond the visible
    rows, so the caller falls back to a real query.
    """
    label, metrics = split_columns(rows)
    if not label or not metrics or len(rows) < 2:
        return None
    words = _tokens(message)
    want_max = any(w in _MAX_WORDS for w in words)
    want_min = any(w in _MIN_WORDS for w in words)
    if want_max == want_min:          # neither, or both: not a simple extremum
        return None

    # Column names (e.g. "geo", "total_revenue") may be mentioned freely.
    known = set(_REFERENCE_WORDS) | set(_MAX_WORDS) | set(_MIN_WORDS)
    for col in [label, *metrics]:
        known.update(_tokens(col.replace("_", " ")))
    mentioned = [m for m in metrics if any(t in words for t in _tokens(m.replace("_", " "))
                                           if t not in ("total", "sum", "avg", "count"))]
    def _known(w: str) -> bool:
        return (w in known or (w.endswith("s") and w[:-1] in known)
                or (w.endswith("ies") and w[:-3] + "y" in known))

    if not all(_known(w) for w in words):
        return None

    metric = mentioned[0] if len(mentioned) == 1 else metrics[0]
    order = ranked(rows, label, metric)
    if len(order) < 2:
        return None
    target = order[0][1] if want_max else order[-1][1]
    winners = [n for n, v in order if v == target]
    word = "highest" if want_max else "lowest"
    names = " and ".join(winners)
    return (f"{names} has the {word} {metric.replace('_', ' ')}, at "
            f"{format_value(target, metric)} (out of {len(order)}).")
