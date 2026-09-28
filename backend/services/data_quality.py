"""
Data Quality Checks

Computed directly from the uploaded DataFrame at upload time — pure
pandas, no LLM call — so they're instant and always accurate. Surfaced
to the user as warnings/info rather than blocking the upload, since
real-world business spreadsheets are rarely perfectly clean.

Each finding says, in plain language, what is wrong, what it means for the
answers the user will get, and what they could do about it. Findings are
grouped by impact:

  "answers" — could change the numbers in an answer
  "info"    — worth knowing, but won't make answers wrong

The original fields (type/column/count/pct/severity/message, score,
issue_count) are kept so existing callers keep working.
"""

import re
from typing import Any

import pandas as pd

# Columns that hold codes or identifiers rather than quantities. A ticket
# number like "A/5 21171" or a postal code is not a badly formatted number.
_ID_LIKE = re.compile(
    r"(^|_)(id|ids|code|codes|zip|zipcode|postal|postcode|ticket|phone|mobile|sku|"
    r"number|no|num|ref|reference|account|iban|isbn|serial)($|_)",
    re.IGNORECASE,
)


def _label(col: str) -> str:
    return str(col).replace("_", " ")


def _is_blank(series: pd.Series) -> pd.Series:
    """True for NaN and for strings that are empty or whitespace only."""
    blank_str = series.astype(str).str.strip().eq("") & series.notna()
    return series.isna() | blank_str


def assess(df: pd.DataFrame) -> dict[str, Any]:
    """Return a data-quality report for an uploaded DataFrame."""
    total_rows = len(df)
    issues: list[dict[str, Any]] = []
    if total_rows == 0:
        return {"score": 100, "issue_count": 0, "issues": [], "columns": [],
                "verdict": {"level": "ready", "label": "No rows to check", "summary": ""}}

    # ── Missing values (NaN or blank text) per column ──
    for col in df.columns:
        count = int(_is_blank(df[col]).sum())
        if count == 0:
            continue
        pct = round(count / total_rows * 100, 1)
        filled = total_rows - count
        name = _label(col)
        if pct >= 60:
            issues.append(_issue(
                "missing_values", col, count, pct, "low", "info",
                title=f"{name.capitalize()} is mostly empty ({pct}% missing)",
                impact=f"Only {filled:,} of {total_rows:,} rows have a {name}, so questions about "
                       f"{name} won't be reliable. Everything else is unaffected.",
                tip=f"Best not to ask about {name} with this data.",
            ))
        elif pct >= 5:
            issues.append(_issue(
                "missing_values", col, count, pct, "medium", "answers",
                title=f"{name.capitalize()} is missing in {count:,} rows ({pct}%)",
                impact=f"Answers that use {name} (averages, breakdowns, filters) are based only on "
                       f"the {filled:,} rows where it's filled in.",
                tip=f"Fine for most questions — just keep it in mind for anything about {name}. "
                    f"Filling in the missing values before uploading would make those answers complete.",
            ))
        else:
            issues.append(_issue(
                "missing_values", col, count, pct, "low", "info",
                title=f"{name.capitalize()} is missing in {count:,} rows ({pct}%)",
                impact="Too few to noticeably change any answer.",
                tip="Nothing to do.",
            ))

    # ── Fully duplicate rows ──
    dup_count = int(df.duplicated().sum())
    if dup_count > 0:
        pct = round(dup_count / total_rows * 100, 1)
        issues.append(_issue(
            "duplicate_rows", None, dup_count, pct, "high" if pct >= 10 else "medium", "answers",
            title=f"{dup_count:,} rows appear more than once ({pct}%)",
            impact="If these are accidental copies, totals and counts will be too high, because "
                   "each copy is counted.",
            tip="Check whether they're genuine repeat transactions; if not, remove the copies and re-upload.",
        ))

    # ── Numbers stored as text (mostly numeric, some values not) ──
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]) or _ID_LIKE.search(str(col)):
            continue
        # Blanks are already reported as missing values; don't count them twice.
        values = df[col].dropna().astype(str)
        values = values[values.str.strip() != ""]
        if values.empty:
            continue
        numeric_like = values.str.replace(r"[,$%\s]", "", regex=True).str.match(r"^-?\d+\.?\d*$")
        ratio = float(numeric_like.mean())
        if not 0.5 <= ratio < 1.0:
            continue
        bad = values[~numeric_like]
        bad_count = int(len(bad))
        pct = round(bad_count / total_rows * 100, 1)
        examples = [str(v) for v in bad.unique()[:3]]
        name = _label(col)
        shown = ", ".join(f'"{e}"' for e in examples)
        issues.append(_issue(
            "inconsistent_type", col, bad_count, pct, "high" if pct >= 5 else "medium", "answers",
            title=f"{name.capitalize()} has {bad_count:,} values that aren't numbers",
            impact=f"{name.capitalize()} is otherwise numeric, but values such as {shown} are not. "
                   f"Totals and averages of {name} may skip or miscount those rows.",
            tip="Replace them with a number (or leave the cell empty) and re-upload.",
            examples=examples,
        ))

    # ── Single-value (constant) columns ──
    for col in df.columns:
        if total_rows > 1 and df[col].nunique(dropna=True) == 1:
            value = str(df[col].dropna().iloc[0])
            name = _label(col)
            issues.append(_issue(
                "constant_column", col, total_rows, 100.0, "low", "info",
                title=f"Every row has the same {name} (\"{value}\")",
                impact=f"Comparing or grouping by {name} won't tell you anything.",
                tip="Nothing to fix — just not a useful thing to ask about.",
                examples=[value],
            ))

    order = {"answers": 0, "info": 1}
    sev = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda i: (order[i["group"]], sev[i["severity"]], -i["pct"]))

    return {
        "score": _quality_score(issues),
        "issue_count": len(issues),
        "issues": issues,
        "verdict": _verdict(issues),
        "columns": _column_completeness(df),
    }


def _issue(type_, column, count, pct, severity, group, *, title, impact, tip, examples=None):
    return {
        "type": type_,
        "column": column,
        "count": int(count),
        "pct": pct,
        "severity": severity,
        "group": group,
        "title": title,
        "impact": impact,
        "tip": tip,
        "examples": examples or [],
        # Kept for older callers that only read `message`.
        "message": title + ". " + impact,
    }


def _verdict(issues: list[dict[str, Any]]) -> dict[str, str]:
    affecting = [i for i in issues if i["group"] == "answers"]
    info = len(issues) - len(affecting)
    if any(i["severity"] == "high" for i in affecting):
        return {
            "level": "attention",
            "label": "Needs attention",
            "summary": "Some answers could be wrong until the issues below are fixed.",
        }
    if affecting:
        n = len(affecting)
        return {
            "level": "care",
            "label": "Usable, with care",
            "summary": f"{n} thing{'s' if n > 1 else ''} could affect some answers — see below.",
        }
    return {
        "level": "ready",
        "label": "Ready to use",
        "summary": (f"Nothing that would change your answers. {info} minor note{'s' if info != 1 else ''} below."
                    if info else "No issues found."),
    }


def _column_completeness(df: pd.DataFrame) -> list[dict[str, Any]]:
    total = len(df)
    out = []
    for col in df.columns:
        filled = total - int(_is_blank(df[col]).sum())
        out.append({"name": str(col), "filled_pct": round(filled / total * 100, 1) if total else 100.0})
    return out


def _quality_score(issues: list[dict[str, Any]]) -> int:
    """A rough 0-100 score. Only issues that can change answers cost much;
    informational notes (a mostly-empty column, a constant column) cost little."""
    deductions = {("answers", "high"): 20, ("answers", "medium"): 8,
                  ("answers", "low"): 3, ("info", "high"): 2,
                  ("info", "medium"): 2, ("info", "low"): 1}
    score = 100 - sum(deductions[(i["group"], i["severity"])] for i in issues)
    return max(0, min(100, score))
