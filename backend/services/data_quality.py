"""
Data Quality Checks

Computed directly from the uploaded DataFrame at upload time — pure
pandas, no LLM call — so they're instant and always accurate. Surfaced
to the user as warnings/info rather than blocking the upload, since
real-world business spreadsheets are rarely perfectly clean.
"""

from typing import Any

import pandas as pd


def assess(df: pd.DataFrame) -> dict[str, Any]:
    """Return a data-quality report for an uploaded DataFrame."""
    total_rows = len(df)
    issues: list[dict[str, Any]] = []

    # Missing values per column
    missing = df.isna().sum()
    for col, count in missing.items():
        if count == 0:
            continue
        pct = round(count / total_rows * 100, 1)
        severity = "high" if pct >= 30 else "medium" if pct >= 5 else "low"
        issues.append({
            "type": "missing_values",
            "column": col,
            "count": int(count),
            "pct": pct,
            "severity": severity,
            "message": f"'{col}' is missing {pct}% of values ({count} of {total_rows} rows).",
        })

    # Fully duplicate rows
    dup_count = int(df.duplicated().sum())
    if dup_count > 0:
        pct = round(dup_count / total_rows * 100, 1)
        issues.append({
            "type": "duplicate_rows",
            "column": None,
            "count": dup_count,
            "pct": pct,
            "severity": "high" if pct >= 10 else "medium",
            "message": f"{dup_count} duplicate rows found ({pct}% of the data).",
        })

    # Columns that look numeric but were parsed as text (mixed/dirty values)
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            continue
        non_null = df[col].dropna().astype(str)
        if non_null.empty:
            continue
        numeric_like = non_null.str.replace(r"[,$%\s]", "", regex=True).str.match(r"^-?\d+\.?\d*$")
        ratio = numeric_like.mean()
        if 0.5 <= ratio < 1.0:
            issues.append({
                "type": "inconsistent_type",
                "column": col,
                "count": int((~numeric_like).sum()),
                "pct": round((1 - ratio) * 100, 1),
                "severity": "medium",
                "message": f"'{col}' looks mostly numeric but has some non-numeric or inconsistently formatted values.",
            })

    # Single-value (constant) columns — rarely useful for analysis
    for col in df.columns:
        if df[col].nunique(dropna=True) == 1 and total_rows > 1:
            issues.append({
                "type": "constant_column",
                "column": col,
                "count": total_rows,
                "pct": 100.0,
                "severity": "low",
                "message": f"'{col}' has the same value in every row.",
            })

    score = _quality_score(issues, total_rows)

    return {
        "score": score,
        "issue_count": len(issues),
        "issues": sorted(issues, key=lambda i: {"high": 0, "medium": 1, "low": 2}[i["severity"]]),
    }


def _quality_score(issues: list[dict[str, Any]], total_rows: int) -> int:
    """A rough 0-100 score: starts at 100, deducts per issue by severity."""
    deductions = {"high": 15, "medium": 7, "low": 2}
    score = 100 - sum(deductions[i["severity"]] for i in issues)
    return max(0, min(100, score))
