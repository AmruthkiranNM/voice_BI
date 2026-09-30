"""
End-to-end acceptance run for the prediction audit.

Runs the required queries through the real application pipeline and captures,
for each prediction: detected frequency, observations, selected model, MASE,
whether it beat the naive baseline, the horizon, and every forecast value —
so the numbers in the report come from the system rather than from a summary
of it.

Run from the backend directory:
    ../venv/Scripts/python.exe ../audit/e2e_acceptance.py
"""

import io
import json
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from services.auth import current_user_id  # noqa: E402

current_user_id.set(1)

from agents.orchestrator import process_query  # noqa: E402

OUT = Path(__file__).resolve().parent / "results"
OUT.mkdir(exist_ok=True)
SCOPE = ["sales", "geo", "products", "people"]

QUERIES = [
    ("Forecast revenue for the next 3 months.", "prediction"),
    ("Forecast revenue for the next 6 months.", "prediction"),
    ("Forecast revenue for the next 12 months.", "prediction"),
    ("Forecast revenue by region for the next 12 months.", "prediction"),
    ("Forecast revenue by product for the next 12 months.", "prediction"),
    ("Forecast revenue by salesperson for the next 6 months.", "prediction"),
    ("Forecast the top 5 products by revenue for the next 12 months.", "prediction"),
    ("Will the top 5 products remain the same next year?", "prediction"),
    ("Provide details of all products sold by salesperson.", "detail"),
    ("Rank countries by revenue.", "ranking"),
    ("Show revenue trend over time.", "trend"),
]

# Wording a detail answer has no business producing on its own.
UNSOLICITED = ["top product", "best performer", "leading", "recommend",
               "you should", "boost", "increase marketing", "opportunity",
               "actionable", "next steps"]


def summarise_prediction(res):
    pred = (res.get("result") or {}).get("prediction") or {}
    cfg = res.get("config") or (res.get("metadata") or {}).get("prediction_config") or {}
    meta = pred.get("model_metadata") or {}
    per_group = meta.get("per_group") or {}

    rows = pred.get("forecast_rows") or []
    by_group = {}
    for r in rows:
        by_group.setdefault(str(r.get("group")), []).append(
            (str(r.get("period"))[:10], r.get("value")))

    if per_group:
        models = {}
        for entry in per_group.values():
            if isinstance(entry, dict) and entry.get("selected_model_label"):
                models[entry["selected_model_label"]] = models.get(
                    entry["selected_model_label"], 0) + 1
        mases = [e.get("selected_score") for e in per_group.values()
                 if isinstance(e, dict) and e.get("selected_score") is not None]
        beats = sum(1 for e in per_group.values()
                    if isinstance(e, dict) and e.get("beats_naive"))
        model_desc = ", ".join(f"{k} x{v}" for k, v in sorted(models.items()))
        mase_desc = (f"{min(mases):.2f}-{max(mases):.2f}" if mases else "-")
        beats_desc = f"{beats}/{len(per_group)}"
    else:
        model_desc = meta.get("selected_model_label") or "-"
        mase_desc = (f"{meta.get('selected_score'):.2f}"
                     if meta.get("selected_score") is not None else "-")
        beats_desc = str(meta.get("beats_naive"))

    diag = pred.get("series_diagnostics") or {}
    return {
        "frequency": cfg.get("time_frequency") or diag.get("requested_frequency"),
        "observations": diag.get("n_observed"),
        "horizon": cfg.get("horizon"),
        "granularity": cfg.get("result_granularity") or "total",
        "n_groups": len(by_group),
        "periods_per_group": (len(next(iter(by_group.values()))) if by_group else 0),
        "models": model_desc,
        "mase": mase_desc,
        "beats_naive": beats_desc,
        "values": {g: v[:12] for g, v in list(by_group.items())[:3]},
    }


def main() -> None:
    report, summary = [], []
    for i, (q, kind) in enumerate(QUERIES, 1):
        t0 = time.perf_counter()
        try:
            res = process_query(q, table_names=SCOPE, cache_mode=False)
        except Exception as exc:
            summary.append(f"{i:2d}. FAILED  {q[:52]}  {type(exc).__name__}")
            report.append(f"## {i}. {q}\n\nEXCEPTION: {exc}\n")
            continue
        ms = (time.perf_counter() - t0) * 1000

        result = res.get("result") or {}
        insight = res.get("insight") or ""
        pipeline = (res.get("metadata") or {}).get("pipeline_type")
        line = [f"## {i}. {q}", "",
                f"- pipeline: {pipeline} | rows: {result.get('row_count')} | "
                f"{ms/1000:.1f}s"]

        if kind == "prediction" and pipeline == "PREDICTIVE":
            info = summarise_prediction(res)
            line += [f"- frequency: {info['frequency']} | observations: "
                     f"{info['observations']} | horizon: {info['horizon']}",
                     f"- granularity: {info['granularity']} | groups: "
                     f"{info['n_groups']} | periods per group: "
                     f"{info['periods_per_group']}",
                     f"- model(s): {info['models']}",
                     f"- MASE: {info['mase']} | beats naive: {info['beats_naive']}",
                     "- forecast values:"]
            for g, vals in info["values"].items():
                pretty = ", ".join(f"{d}={v:,.0f}" for d, v in vals if v is not None)
                line.append(f"    - {g}: {pretty}")
            flag = (f"h={info['horizon']} x{info['periods_per_group']}p "
                    f"MASE {info['mase']} beats {info['beats_naive']}")
            summary.append(f"{i:2d}. {'PRED':5s} {q[:46]:48s} {flag}")
        else:
            found = [w for w in UNSOLICITED if w in insight.lower()]
            if kind == "detail":
                line.append(f"- unsolicited analysis phrases: {found or 'none'}")
                summary.append(f"{i:2d}. {kind.upper():5s} {q[:46]:48s} "
                               f"rows={result.get('row_count')} "
                               f"unsolicited={found or 'none'}")
            else:
                summary.append(f"{i:2d}. {kind.upper():5s} {q[:46]:48s} "
                               f"rows={result.get('row_count')}")
            line.append(f"- sql: `{(res.get('sql') or '').replace(chr(10), ' ')[:180]}`")

        line += ["", f"answer: {insight[:400]}", ""]
        report.append("\n".join(line))
        print(summary[-1])

    io.open(OUT / "e2e_acceptance.md", "w", encoding="utf-8").write(
        "# End-to-end acceptance run\n\n" + "\n".join(report))
    io.open(OUT / "e2e_summary.txt", "w", encoding="utf-8").write("\n".join(summary))
    print("\nwritten:", OUT / "e2e_acceptance.md")


if __name__ == "__main__":
    main()
