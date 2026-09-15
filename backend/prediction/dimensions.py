"""
Prediction Package — Generic Dimension Resolution

Turns a user's words ("country", "product category", "sales rep") into concrete
(table, column, join path) triples, using nothing but the live schema and its
data. There is no alias table anywhere in this module: no list of countries, no
mapping from "country" to a particular column name, no assumption that the
dataset is about sales at all. Point it at a different database and it behaves
the same way.

Resolution is layered, cheapest and most certain first:

  1. exact column-name match          ("region" -> region)
  2. normalised / token overlap        ("product category" -> category)
  3. value match                       ("bars" -> the column containing 'Bars')
  4. embedding similarity over a column profile built from its name, its table
     and its actual values ("country" -> geo.geo, because that column contains
     India, USA, Canada...)

Only step 4 needs a model, and it only runs when the cheaper steps found
nothing. Every resolution records how it was made and how confident it is, so
an ambiguous match is visible rather than silent.

Join paths are discovered by intersecting column names between the fact table
and the dimension table and then *verifying* that the candidate key's values
actually overlap. Guessing a key from the table's name (``people`` -> ``pid``)
is what previously pointed the team dimension at the product key.
"""

from __future__ import annotations

import dataclasses
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# A column with more distinct values than this is not offered as a forecasting
# dimension by default — one series per value would be unmodellable.
MAX_DIMENSION_CARDINALITY = 200

# Embedding similarity below this is treated as "no idea", not a weak guess.
MIN_EMBEDDING_SIMILARITY = 0.20

# How many distinct values to sample into a column's profile document.
PROFILE_SAMPLE_VALUES = 12


class DimensionalityError(ValueError):
    """
    Raised when a forecast's dimensionality does not match what was requested.

    This is deliberately fatal. A grouped forecast that has quietly lost a
    dimension still looks like a valid result — it just answers a different
    question than the one asked, which is worse than an error.
    """


@dataclasses.dataclass
class DimensionCandidate:
    """One column that could serve as a grouping dimension."""
    table: str
    column: str
    n_distinct: int
    sample_values: list[str] = dataclasses.field(default_factory=list)
    in_base_table: bool = False

    @property
    def profile(self) -> str:
        """Text used for embedding similarity: name, table, and real values."""
        values = ", ".join(self.sample_values[:PROFILE_SAMPLE_VALUES])
        readable = self.column.replace("_", " ")
        return f"{readable}. Table {self.table}. Values: {values}"


@dataclasses.dataclass
class ResolvedDimension:
    """A user hint bound to a concrete column, with a verified join path."""
    hint: str
    table: str
    column: str
    n_distinct: int = 0
    requires_join: bool = True
    join_key_base: str | None = None
    join_key_target: str | None = None
    method: str = ""          # exact_name | token_match | value_match | embedding
    confidence: float = 0.0
    runner_up: str | None = None
    ambiguous: bool = False

    def to_dim_info(self) -> dict[str, Any]:
        """Serialise into the dict shape the predictor consumes."""
        return {
            "target_table": self.table,
            "group_column": self.column,
            "join_key_base": self.join_key_base,
            "join_key_target": self.join_key_target,
            "requires_join": self.requires_join,
            "semantic_hint": self.hint,
            "resolution_method": self.method,
            "resolution_confidence": round(self.confidence, 4),
            "n_distinct": self.n_distinct,
            "ambiguous": self.ambiguous,
            "runner_up": self.runner_up,
        }


@dataclasses.dataclass
class DimensionResolution:
    """Outcome of resolving every hint in one request."""
    requested: list[str] = dataclasses.field(default_factory=list)
    resolved: list[ResolvedDimension] = dataclasses.field(default_factory=list)
    unresolved: list[dict[str, Any]] = dataclasses.field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.unresolved and len(self.resolved) == len(self.requested)

    def error_message(self) -> str:
        parts = []
        for item in self.unresolved:
            suggestion = ""
            if item.get("closest"):
                suggestion = f" Closest available: {', '.join(item['closest'])}."
            parts.append(f"'{item['hint']}' could not be matched to any column.{suggestion}")
        return " ".join(parts)


# ──────────────────────────────────────────────────────────
# Catalog
# ──────────────────────────────────────────────────────────

def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", str(text).lower()) if t}


def _looks_like_key(column: str) -> bool:
    c = column.lower()
    return c.endswith(("id", "key", "code", "no", "num")) or c in ("index", "rownumber")


def joinable_tables(base_table: str) -> dict[str, tuple[str, str] | None]:
    """
    Map every table that can legitimately contribute a dimension to its
    verified join key (the base table maps to None — no join needed).

    Reachability is the scope rule. A column in a table with no verified join
    path to the fact table cannot group it, no matter how well its name
    matches: an unrelated upload that happens to contain a "country" column
    must not be offered as the country dimension for this fact table.
    """
    from services.database import get_all_table_names

    reachable: dict[str, tuple[str, str] | None] = {base_table: None}
    for table in get_all_table_names():
        if table == base_table:
            continue
        path = find_join_path(base_table, table)
        if path is not None:
            reachable[table] = path
    return reachable


def build_dimension_catalog(
    base_table: str,
    max_cardinality: int = MAX_DIMENSION_CARDINALITY,
    exclude_columns: set[str] | None = None,
    reachable: dict[str, tuple[str, str] | None] | None = None,
) -> list[DimensionCandidate]:
    """
    Enumerate every column that could group a forecast of ``base_table``.

    Includes columns of the fact table itself, so a denormalised single-table
    dataset (one CSV with a country column in it) works exactly like a star
    schema — the previous implementation only ever looked at *other* tables and
    could not group a flat file at all. Tables with no verified join path are
    excluded entirely.
    """
    from services.database import get_table_schema, get_connection

    if reachable is None:
        reachable = joinable_tables(base_table)

    exclude = {c.lower() for c in (exclude_columns or set())}
    candidates: list[DimensionCandidate] = []
    conn = get_connection()
    try:
        for table in reachable:
            schema = get_table_schema(table)
            for col in schema:
                name = col["column_name"]
                if name.lower() in exclude or _looks_like_key(name):
                    continue
                dtype = (col.get("data_type") or "").upper()
                # Numeric columns are measures, not dimensions.
                if dtype in ("INTEGER", "REAL", "FLOAT", "NUMERIC", "DOUBLE", "BIGINT"):
                    continue
                try:
                    n_distinct = conn.execute(
                        f"SELECT COUNT(DISTINCT [{name}]) FROM [{table}];"
                    ).fetchone()[0]
                except Exception:
                    continue
                if not n_distinct or n_distinct > max_cardinality or n_distinct < 2:
                    continue
                try:
                    values = [
                        str(r[0]) for r in conn.execute(
                            f"SELECT DISTINCT [{name}] FROM [{table}] "
                            f"WHERE [{name}] IS NOT NULL LIMIT ?;",
                            (PROFILE_SAMPLE_VALUES,),
                        )
                    ]
                except Exception:
                    values = []
                # A date-like column is a time axis, not a grouping dimension.
                if values and all(re.match(r"^\d{4}-\d{2}-\d{2}", v) for v in values):
                    continue
                candidates.append(DimensionCandidate(
                    table=table, column=name, n_distinct=int(n_distinct),
                    sample_values=values, in_base_table=(table == base_table),
                ))
    finally:
        conn.close()

    return candidates


# ──────────────────────────────────────────────────────────
# Join discovery
# ──────────────────────────────────────────────────────────

def find_join_path(base_table: str, target_table: str) -> tuple[str, str] | None:
    """
    Find a key joining the fact table to a dimension table.

    Candidate keys are columns present in *both* tables. Each candidate is then
    verified by sampling: its values must actually overlap. A shared column name
    with disjoint values is a coincidence, not a relationship.

    Returns (base_column, target_column) or None when no verified path exists.
    """
    from services.database import get_table_schema, get_connection

    if base_table == target_table:
        return None

    base_cols = {c["column_name"] for c in get_table_schema(base_table)}
    target_cols = {c["column_name"] for c in get_table_schema(target_table)}

    shared = {c for c in base_cols if c in target_cols}
    if not shared:
        # Case-insensitive fallback for schemas that differ only in casing.
        lowered = {c.lower(): c for c in target_cols}
        shared = {c for c in base_cols if c.lower() in lowered}
        if not shared:
            return None

    # Key-looking columns first; they are far more likely to be the real key.
    ordered = sorted(shared, key=lambda c: (not _looks_like_key(c), c))

    conn = get_connection()
    try:
        best: tuple[str, float] | None = None
        for col in ordered:
            target_col = next((t for t in target_cols if t.lower() == col.lower()), col)
            try:
                overlap = conn.execute(
                    f"SELECT COUNT(*) FROM (SELECT DISTINCT [{col}] AS v FROM [{base_table}]) b "
                    f"WHERE b.v IN (SELECT DISTINCT [{target_col}] FROM [{target_table}]);"
                ).fetchone()[0]
                total = conn.execute(
                    f"SELECT COUNT(DISTINCT [{col}]) FROM [{base_table}];"
                ).fetchone()[0]
            except Exception:
                continue
            if not total:
                continue
            ratio = overlap / total
            if ratio > 0 and (best is None or ratio > best[1]):
                best = ((col, target_col), ratio)
        if best and best[1] >= 0.5:
            return best[0]
    finally:
        conn.close()

    return None


# ──────────────────────────────────────────────────────────
# Resolution
# ──────────────────────────────────────────────────────────

def _lexical_score(hint: str, cand: DimensionCandidate) -> tuple[float, str]:
    """Deterministic name-based scoring. Returns (score in 0..1, method)."""
    h_norm, c_norm = _normalise(hint), _normalise(cand.column)
    if h_norm == c_norm:
        return 1.0, "exact_name"

    h_tokens, c_tokens = _tokens(hint), _tokens(cand.column)
    if h_tokens and c_tokens:
        if c_tokens <= h_tokens or h_tokens <= c_tokens:
            # "product category" contains "category"; "category" is contained by it.
            return 0.9, "token_match"
        overlap = h_tokens & c_tokens
        if overlap:
            return 0.6 * len(overlap) / max(len(h_tokens), len(c_tokens)), "token_match"

    # Substring, but only for reasonably long hints to avoid "id" matching everything.
    if len(h_norm) >= 4 and (h_norm in c_norm or c_norm in h_norm):
        return 0.55, "token_match"

    return 0.0, ""


def _value_score(hint: str, cand: DimensionCandidate) -> float:
    """1.0 when the hint names one of the column's actual values (e.g. 'bars')."""
    h = _normalise(hint)
    if not h:
        return 0.0
    for value in cand.sample_values:
        if _normalise(value) == h:
            return 1.0
    return 0.0


def _embedding_scores(hints: list[str], candidates: list[DimensionCandidate]):
    """
    Cosine similarity between each hint and each column's profile document.

    This is the layer that resolves a hint with no lexical counterpart — the
    word "country" appears nowhere in this schema, but the column holding
    India/USA/Canada is recognisably about countries.
    """
    try:
        import numpy as np
        from services.embeddings import generate_embeddings_batch
    except Exception as exc:  # embeddings are optional; degrade, don't crash
        logger.warning("[Dimensions] Embedding resolution unavailable: %s", exc)
        return None

    try:
        cand_vecs = generate_embeddings_batch([c.profile for c in candidates])
        hint_vecs = generate_embeddings_batch(hints)
        return np.asarray(hint_vecs) @ np.asarray(cand_vecs).T
    except Exception as exc:
        logger.warning("[Dimensions] Embedding resolution failed: %s", exc)
        return None


def resolve_dimensions(
    hints: list[str],
    base_table: str,
    exclude_columns: set[str] | None = None,
) -> DimensionResolution:
    """
    Resolve every hint to a concrete column with a verified join path.

    Args:
        hints: the user's grouping words, in the order they were asked for.
        base_table: the fact table the forecast is built from.
        exclude_columns: columns to keep out of the catalog (target, date).

    Returns:
        DimensionResolution. ``ok`` is False when any hint failed; the caller
        must not fall back to a default dimension, because guessing which
        dimension the user meant produces a confidently mislabelled answer.
    """
    resolution = DimensionResolution(requested=list(hints))
    if not hints:
        return resolution

    reachable = joinable_tables(base_table)
    catalog = build_dimension_catalog(
        base_table, exclude_columns=exclude_columns, reachable=reachable,
    )
    if not catalog:
        for hint in hints:
            resolution.unresolved.append({
                "hint": hint,
                "reason": "No categorical columns are available to group by.",
                "closest": [],
            })
        return resolution

    # Cheap layers first; only embed the hints that still need it.
    deterministic: dict[str, tuple[DimensionCandidate, float, str, str | None]] = {}
    needs_embedding: list[str] = []

    for hint in hints:
        scored: list[tuple[float, str, DimensionCandidate]] = []
        for cand in catalog:
            lex, method = _lexical_score(hint, cand)
            val = _value_score(hint, cand)
            score, how = (val, "value_match") if val > lex else (lex, method)
            if score > 0:
                scored.append((score, how, cand))

        if not scored:
            needs_embedding.append(hint)
            continue

        scored.sort(key=lambda s: (-s[0], s[2].table, s[2].column))
        best_score, best_method, best_cand = scored[0]
        runner = None
        if len(scored) > 1 and scored[1][0] >= best_score - 1e-9:
            runner = f"{scored[1][2].table}.{scored[1][2].column}"
        if best_score < 0.5:
            needs_embedding.append(hint)
            continue
        deterministic[hint] = (best_cand, best_score, best_method, runner)

    embedding_matrix = None
    if needs_embedding:
        embedding_matrix = _embedding_scores(needs_embedding, catalog)

    for hint in hints:
        cand = score = method = runner = None

        if hint in deterministic:
            cand, score, method, runner = deterministic[hint]
        elif embedding_matrix is not None:
            import numpy as np
            row = embedding_matrix[needs_embedding.index(hint)]
            order = np.argsort(-row)
            if float(row[order[0]]) >= MIN_EMBEDDING_SIMILARITY:
                cand = catalog[int(order[0])]
                score = float(row[order[0]])
                method = "embedding"
                if len(order) > 1:
                    runner = (f"{catalog[int(order[1])].table}."
                              f"{catalog[int(order[1])].column}"
                              f" ({float(row[order[1]]):.3f})")

        if cand is None:
            resolution.unresolved.append({
                "hint": hint,
                "reason": "No column name, value, or profile matched this term.",
                "closest": sorted({f"{c.table}.{c.column}" for c in catalog})[:8],
            })
            continue

        if cand.in_base_table:
            join_base = join_target = None
            requires_join = False
        else:
            path = reachable.get(cand.table)
            if path is None:
                resolution.unresolved.append({
                    "hint": hint,
                    "reason": (
                        f"Matched column '{cand.table}.{cand.column}', but no verified "
                        f"join key connects '{cand.table}' to '{base_table}'."
                    ),
                    "closest": [],
                })
                continue
            join_base, join_target = path
            requires_join = True

        # Flag a near-tie so a marginal choice is visible instead of silent.
        ambiguous = False
        if method == "embedding" and runner:
            try:
                runner_score = float(runner.rsplit("(", 1)[1].rstrip(")"))
                ambiguous = (score - runner_score) < 0.05
            except (IndexError, ValueError):
                ambiguous = False

        resolved = ResolvedDimension(
            hint=hint, table=cand.table, column=cand.column,
            n_distinct=cand.n_distinct, requires_join=requires_join,
            join_key_base=join_base, join_key_target=join_target,
            method=method, confidence=float(score), runner_up=runner,
            ambiguous=ambiguous,
        )
        resolution.resolved.append(resolved)
        logger.info(
            "[Dimensions] '%s' -> %s.%s via %s (confidence %.3f%s)",
            hint, cand.table, cand.column, method, score,
            ", AMBIGUOUS" if ambiguous else "",
        )

    return resolution


#: Function words, time words and quantity words. Purely linguistic — it
#: contains no domain vocabulary, so it behaves identically on any dataset.
_NON_DIMENSION_WORDS = {
    "a", "an", "the", "of", "in", "on", "by", "for", "per", "to", "from", "at",
    "and", "or", "with", "over", "across", "within", "each", "every", "is",
    "are", "was", "were", "be", "will", "would", "could", "might", "shall",
    "do", "does", "did", "show", "me", "us", "give", "list", "tell", "what",
    "which", "who", "whom", "whose", "where", "when", "how", "why", "many",
    "much", "most", "least", "best", "worst", "highest", "lowest", "top",
    "bottom", "rank", "ranked", "lead", "leads", "leading", "leader", "grow",
    "grows", "grow", "growth", "growing", "decline", "declining", "increase",
    "decrease", "rise", "fall", "falling", "behind", "ahead", "change",
    "expected", "expect", "likely", "projected", "project", "forecast",
    "forecasted", "predict", "predicted", "prediction", "next", "last",
    "coming", "upcoming", "future", "now", "then", "day", "days", "week",
    "weeks", "month", "months", "quarter", "quarters", "year", "years",
    "period", "periods", "total", "sum", "average", "count", "number",
    "numbers", "amount", "value", "values", "have", "has", "had", "it",
    "its", "they", "them", "their", "this", "that", "these", "those",
    "remain", "stay", "same", "about", "instead", "into", "one", "two",
    "three", "four", "five", "six", "seven", "eight", "nine", "ten", "twelve",
}


def _content_words(
    question: str,
    exclude_columns: set[str] | None = None,
    exclude_words: set[str] | None = None,
) -> list[str]:
    """
    Words from a question that could plausibly name a dimension.

    Strips function, time and quantity words, plus anything already committed
    as the target. What remains are the nouns worth resolving against the
    schema. Adjacent survivors are also offered as a pair, so "sales team" and
    "product category" resolve as phrases rather than as isolated words.
    """
    excluded = {c.lower() for c in (exclude_columns or set())}
    # Words already consumed by the target ("revenue", "boxes sold") must not
    # then be offered as groupings — a measure is not a dimension.
    excluded |= {w.lower() for w in (exclude_words or set())}
    raw = [w for w in re.split(r"[^a-z0-9]+", (question or "").lower()) if w]
    kept = [
        w for w in raw
        if w not in _NON_DIMENSION_WORDS and w not in excluded and len(w) > 2
    ]

    phrases: list[str] = []
    for i, word in enumerate(kept):
        if i + 1 < len(kept):
            phrases.append(f"{word} {kept[i + 1]}")
    # Longer phrases first: "sales team" should win over "sales".
    return phrases + kept


#: Inference is a guess, so it needs a firmer bar than an explicit hint. A hint
#: tells us a dimension was intended and only asks which; inference must also
#: decide *whether* one was meant at all.
MIN_INFERENCE_CONFIDENCE = 0.26


def infer_dimensions(
    question: str,
    base_table: str,
    exclude_columns: set[str] | None = None,
    max_dimensions: int = 3,
    exclude_words: set[str] | None = None,
) -> list[ResolvedDimension]:
    """
    Find the groupings a free-text question is asking for, without being told.

    Used when interpretation returns no dimensions. Every candidate column in
    the reachable schema is scored against the question by the same layers used
    for an explicit hint — its name, its values, and its embedded profile — and
    those that clear a confidence bar are returned in the order they appear in
    the question, so "revenue by country and category" keeps country first.

    Scoring the question as a whole (rather than hunting for noun phrases)
    keeps this free of grammar rules and of any particular phrasing.
    """
    if not question:
        return []

    reachable = joinable_tables(base_table)
    catalog = build_dimension_catalog(
        base_table, exclude_columns=exclude_columns, reachable=reachable,
    )
    if not catalog:
        return []

    question_tokens = _tokens(question)
    hits: list[tuple[int, float, str, DimensionCandidate]] = []

    for candidate in catalog:
        column_tokens = _tokens(candidate.column)
        score, method = 0.0, ""

        # The question names the column outright.
        if column_tokens and column_tokens <= question_tokens:
            score, method = 1.0, "exact_name"
        else:
            # The question names one of the column's values ("in APAC").
            for value in candidate.sample_values:
                value_tokens = _tokens(value)
                if value_tokens and value_tokens <= question_tokens:
                    score, method = 0.95, "value_match"
                    break

        if score:
            position = min(
                (question.lower().find(t) for t in (column_tokens or {""})
                 if question.lower().find(t) >= 0),
                default=10_000,
            )
            hits.append((position, score, method, candidate))

    if not hits:
        # Nothing lexical matched. Embedding the whole sentence dilutes the
        # signal badly, so score the question's *content words* individually
        # through the ordinary hint resolver — the same path that connects
        # "country" to a column of country names.
        candidate_words = _content_words(question, exclude_columns, exclude_words)
        if not candidate_words:
            return []
        resolution = resolve_dimensions(
            candidate_words, base_table, exclude_columns=exclude_columns,
        )
        seen: set[str] = set()
        for dimension in resolution.resolved:
            if dimension.column in seen:
                continue
            if (dimension.method == "embedding"
                    and dimension.confidence < MIN_INFERENCE_CONFIDENCE):
                continue
            seen.add(dimension.column)
            position = question.lower().find(dimension.hint.lower())
            hits.append((
                position if position >= 0 else 10_000,
                dimension.confidence, f"word_{dimension.method}",
                DimensionCandidate(
                    table=dimension.table, column=dimension.column,
                    n_distinct=dimension.n_distinct,
                    in_base_table=not dimension.requires_join,
                ),
            ))
        if not hits:
            return []

    hits.sort(key=lambda h: h[0])
    resolved: list[ResolvedDimension] = []
    for _, score, method, candidate in hits[:max_dimensions]:
        if candidate.in_base_table:
            join_base = join_target = None
            requires_join = False
        else:
            path = reachable.get(candidate.table)
            if path is None:
                continue
            join_base, join_target = path
            requires_join = True
        resolved.append(ResolvedDimension(
            hint=candidate.column, table=candidate.table, column=candidate.column,
            n_distinct=candidate.n_distinct, requires_join=requires_join,
            join_key_base=join_base, join_key_target=join_target,
            method=f"inferred_{method}", confidence=score,
        ))

    if resolved:
        logger.info(
            "[Dimensions] Inferred %s from the question text.",
            [d.column for d in resolved],
        )
    return resolved


# ──────────────────────────────────────────────────────────
# Hard dimensionality validation
# ──────────────────────────────────────────────────────────

def validate_result_dimensions(
    result: Any,
    expected_hints: list[str],
    *,
    strict: bool = True,
) -> list[str]:
    """
    Verify that a grouped forecast actually carries the dimensions requested.

    Checks, in order:
      1. ``result.dimensions`` matches the requested hints exactly, in order.
      2. Every forecast entry exposes a ``group_dict`` keyed by all of them.
      3. No entry has collapsed several dimensions into one key.

    Args:
        result: a UniversalPredictionResult (or its asdict form).
        expected_hints: the dimensions the user asked for, in order.
        strict: raise DimensionalityError on violation; otherwise return issues.

    Returns:
        List of problem descriptions (empty when valid).
    """
    issues: list[str] = []

    dims = getattr(result, "dimensions", None)
    if dims is None and isinstance(result, dict):
        dims = result.get("dimensions")
    dims = list(dims or [])

    if dims != list(expected_hints):
        issues.append(
            f"Result dimensions {dims} do not match the requested "
            f"{list(expected_hints)}."
        )

    entries = getattr(result, "raw_forecast_results", None)
    if entries is None and isinstance(result, dict):
        entries = result.get("raw_forecast_results")
    entries = entries or []

    expected_keys = set(expected_hints)
    for i, entry in enumerate(entries):
        group_dict = entry.get("group_dict") if isinstance(entry, dict) else None
        if not group_dict:
            issues.append(f"Entry {i} ('{_entry_label(entry)}') has no group_dict.")
            continue
        keys = set(group_dict)
        if keys != expected_keys:
            missing = expected_keys - keys
            extra = keys - expected_keys
            detail = []
            if missing:
                detail.append(f"missing {sorted(missing)}")
            if extra:
                detail.append(f"unexpected {sorted(extra)}")
            issues.append(
                f"Entry {i} ('{_entry_label(entry)}') has dimensions {sorted(keys)}: "
                + ", ".join(detail)
            )
        # A collapsed key looks like {"country": "India - Bars"} — one field
        # holding what should have been two dimensions.
        for key, value in group_dict.items():
            if isinstance(value, str) and " - " in value and len(expected_keys) > 1:
                issues.append(
                    f"Entry {i}: dimension '{key}' holds a joined value '{value}', "
                    "which means dimensions were collapsed into one field."
                )

    if issues and strict:
        raise DimensionalityError(
            "Grouped forecast failed dimensionality validation: " + " | ".join(issues[:5])
        )
    return issues


def _entry_label(entry: Any) -> str:
    if isinstance(entry, dict):
        return str(entry.get("group", "?"))
    return str(entry)
