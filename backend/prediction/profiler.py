"""
Prediction Package — Dataset Profiler

Builds a description of what a dataset can support, from the dataset itself.

The profile is what makes interpretation possible without domain assumptions:
instead of asking "does this question mention revenue?", the resolver asks
"which of this dataset's measures best matches what was asked?". Point the
system at a churn table, a transactions table or a logistics table and the
profile simply describes different candidates.

Nothing here knows that a column called ``amount`` is money or that ``geo``
holds countries. Candidates are ranked by what their values are.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any

import pandas as pd

from prediction.target_resolution import TargetSpec, resolve_target
from prediction.time_resolution import TimeColumnProfile, profile_time_columns

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class DatasetProfile:
    """Everything the resolver needs to know about one table."""
    table: str
    n_rows: int = 0
    columns: list[str] = dataclasses.field(default_factory=list)

    measures: list[TargetSpec] = dataclasses.field(default_factory=list)
    labels: list[TargetSpec] = dataclasses.field(default_factory=list)
    identifiers: list[str] = dataclasses.field(default_factory=list)

    time_columns: list[TimeColumnProfile] = dataclasses.field(default_factory=list)
    dimensions: list[dict[str, Any]] = dataclasses.field(default_factory=list)

    @property
    def has_time_axis(self) -> bool:
        return bool(self.time_columns)

    @property
    def measure_names(self) -> list[str]:
        return [m.column for m in self.measures]

    @property
    def label_names(self) -> list[str]:
        return [label.column for label in self.labels]

    @property
    def dimension_names(self) -> list[str]:
        return [d["column"] for d in self.dimensions]

    def summary_for_prompt(self) -> str:
        """
        Compact, factual description of the dataset for an interpreting model.

        Deliberately shows sample values: they are what let a model connect
        "country" to a column called ``geo``, without any mapping table.
        """
        lines = [f"TABLE: {self.table} ({self.n_rows:,} rows)"]

        if self.time_columns:
            lines.append("TIME COLUMNS (usable as the forecast axis):")
            for t in self.time_columns[:4]:
                lines.append(
                    f"  - {t.column}: {t.min_date} to {t.max_date}, "
                    f"~{t.inferred_frequency} granularity"
                )
        else:
            lines.append("TIME COLUMNS: none (forecasting is unavailable)")

        if self.measures:
            lines.append("MEASURES (numeric quantities that can be forecast or regressed):")
            for m in self.measures:
                sample = ", ".join(str(v) for v in m.sample_values[:3])
                lines.append(f"  - {m.column}: {m.n_distinct:,} distinct values, e.g. {sample}")

        if self.labels:
            lines.append("LABELS (categorical targets for classification):")
            for label in self.labels:
                sample = ", ".join(str(v) for v in label.sample_values[:4])
                lines.append(f"  - {label.column}: {label.n_distinct} classes, e.g. {sample}")

        if self.dimensions:
            lines.append("DIMENSIONS (columns a prediction can be grouped by):")
            for d in self.dimensions:
                sample = ", ".join(str(v) for v in d["sample_values"][:4])
                lines.append(
                    f"  - {d['column']} (in {d['table']}): "
                    f"{d['n_distinct']} values, e.g. {sample}"
                )

        return "\n".join(lines)


def build_profile(table: str, df: pd.DataFrame | None = None) -> DatasetProfile:
    """
    Profile a table: its measures, labels, identifiers, time axes and dimensions.

    Every column is classified by the same resolvers the engine uses later, so
    what the profile advertises is exactly what the engine can deliver.
    """
    from prediction.dimensions import build_dimension_catalog

    if df is None:
        from services.database import get_connection
        conn = get_connection()
        try:
            df = pd.read_sql_query(f"SELECT * FROM [{table}]", conn)
        finally:
            conn.close()

    profile = DatasetProfile(table=table, n_rows=int(len(df)), columns=list(df.columns))
    profile.time_columns = profile_time_columns(df)
    has_time = bool(profile.time_columns)
    time_column_names = {t.column for t in profile.time_columns}

    for column in df.columns:
        if column in time_column_names:
            continue
        spec = resolve_target(column, df, has_time_axis=has_time)
        if spec.semantic_role == "measure":
            profile.measures.append(spec)
        elif spec.semantic_role == "label":
            profile.labels.append(spec)
        elif spec.semantic_role == "identifier":
            profile.identifiers.append(column)

    # Dimensions come from the whole reachable schema, not just this table, so
    # a star schema's lookup tables are offered alongside the fact table's own
    # categorical columns.
    exclude = set(time_column_names) | {m.column for m in profile.measures}
    try:
        for candidate in build_dimension_catalog(table, exclude_columns=exclude):
            profile.dimensions.append({
                "column": candidate.column,
                "table": candidate.table,
                "n_distinct": candidate.n_distinct,
                "sample_values": candidate.sample_values,
                "in_base_table": candidate.in_base_table,
            })
    except Exception as exc:  # a missing catalog must not block profiling
        logger.warning("[Profiler] Dimension catalog unavailable for %s: %s", table, exc)

    logger.info(
        "[Profiler] %s: %d rows, %d measures, %d labels, %d time columns, %d dimensions",
        table, profile.n_rows, len(profile.measures), len(profile.labels),
        len(profile.time_columns), len(profile.dimensions),
    )
    return profile


def choose_dataset_table(
    candidate_tables: list[str] | None = None,
    require_time_axis: bool = True,
) -> tuple[str | None, list[DatasetProfile]]:
    """
    Pick the fact table to predict from, by structure rather than by name.

    The best candidate is the one that looks most like a fact table: the most
    rows, carrying measures, and (when forecasting) a usable time axis. The
    previous implementation matched table names against a list of words like
    "sales" and "customer", which only worked for datasets that happened to
    use those words.
    """
    from services.database import get_all_table_names

    tables = candidate_tables or get_all_table_names()
    profiles: list[DatasetProfile] = []

    for table in tables:
        if table.startswith("_vbi_"):
            continue
        try:
            profile = build_profile(table)
        except Exception as exc:
            logger.warning("[Profiler] Could not profile %s: %s", table, exc)
            continue
        if profile.measures:
            profiles.append(profile)

    if not profiles:
        return None, []

    def score(p: DatasetProfile) -> tuple:
        return (
            bool(p.time_columns) if require_time_axis else False,
            len(p.measures),
            p.n_rows,
        )

    profiles.sort(key=score, reverse=True)
    return profiles[0].table, profiles
