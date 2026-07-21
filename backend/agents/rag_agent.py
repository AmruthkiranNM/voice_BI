"""
RAG Retriever Agent

Uses the FAISS vector store to retrieve database schema documents
that are most relevant to the user's query. This provides context
to the SQL Generator Agent, preventing hallucinated table/column names.

When ``table_names`` is provided, retrieval is pinned to exactly those
tables (one data source's scope) so queries never reference tables from
another source, and joins are only ever built within the scope.
"""

import logging
from services.vector_store import search, is_index_ready
from services.database import get_table_schema
from models.schema_loader import generate_table_document

logger = logging.getLogger(__name__)


def run(query: str, plan: dict, table_names: list[str] | None = None) -> dict:
    """
    Retrieve relevant schema documents using RAG.

    Constructs an enriched search query from the user query and plan,
    then searches the FAISS vector store for matching schema documents.

    Args:
        query: Original natural language query.
        plan: Execution plan from the Planner Agent.
        table_names: When set, restrict scope to exactly these tables (skip
            vector search). One entry = single-table query; several = join
            scope. This is the active data source's table set.

    Returns:
        Dictionary with retrieved schema context.
    """
    logger.info("[RAG Agent] Retrieving schema for query: %s", query[:80])

    if table_names:
        return _context_for_tables(table_names)

    if not is_index_ready():
        raise RuntimeError(
            "FAISS vector store is not initialized. "
            "Ensure the system startup has built the index."
        )

    enriched_query = _build_enriched_query(query, plan)
    logger.info("[RAG Agent] Enriched search query: %s", enriched_query[:120])

    results = search(enriched_query)

    retrieved_tables = []
    schema_context_parts = []
    seen_tables = set()

    for result in results:
        tname = result["table_name"]
        if tname not in seen_tables:
            seen_tables.add(tname)
            retrieved_tables.append(tname)
            schema_context_parts.append(result["document"])

    schema_context = "\n\n---\n\n".join(schema_context_parts)
    if len(retrieved_tables) > 1:
        join_hints = _build_join_hints(retrieved_tables)
        if join_hints:
            schema_context += "\n\n---\n\n" + join_hints

    rag_output = {
        "retrieved_tables": retrieved_tables,
        "schema_context": schema_context,
        "num_results": len(results),
        "similarity_scores": {
            r["table_name"]: r["similarity_score"] for r in results
        },
        "pinned_table": None,
        "pinned_tables": None,
    }

    logger.info(
        "[RAG Agent] Retrieved %d tables: %s",
        len(retrieved_tables),
        retrieved_tables,
    )

    return rag_output


def _context_for_tables(table_names: list[str]) -> dict:
    """Build schema context for exactly the given tables (the active source scope)."""
    parts = [generate_table_document(t) for t in table_names]
    schema_context = "\n\n---\n\n".join(parts)
    if len(table_names) > 1:
        join_hints = _build_join_hints(table_names)
        if join_hints:
            schema_context += "\n\n---\n\n" + join_hints

    logger.info("[RAG Agent] Scoped to %d table(s): %s", len(table_names), table_names)
    return {
        "retrieved_tables": list(table_names),
        "schema_context": schema_context,
        "num_results": len(table_names),
        "similarity_scores": {t: 1.0 for t in table_names},
        "pinned_table": table_names[0] if len(table_names) == 1 else None,
        "pinned_tables": list(table_names),
    }


def _build_join_hints(tables: list[str]) -> str:
    """
    Uploaded CSVs never carry real foreign keys (SQLite PRAGMA returns none
    for pandas.to_sql tables), so the SQL generator has no way to know which
    columns join two tables. Suggest join keys heuristically: columns with
    the same name in two or more of the retrieved tables are very likely the
    join columns (e.g. "customer_id" in both "orders" and "customers").
    """
    cols_by_table = {t: {c["column_name"] for c in get_table_schema(t)} for t in tables}
    lines = []
    for i, t1 in enumerate(tables):
        for t2 in tables[i + 1:]:
            shared = sorted(cols_by_table[t1] & cols_by_table[t2])
            shared = [c for c in shared if c.lower() not in ("id", "name")]
            if shared:
                lines.append(f"  - {t1}.{'/'.join(shared)} = {t2}.{'/'.join(shared)}")
    if not lines:
        return ""
    return (
        "Likely JOIN keys (columns with matching names across these tables — "
        "no real foreign keys exist since this data comes from separate CSV "
        "uploads, so use these to JOIN when the question spans tables):\n"
        + "\n".join(lines)
    )


def _build_enriched_query(query: str, plan: dict) -> str:
    """
    Build an enriched search query by combining the original query
    with extracted metrics and filters from the plan.
    """
    parts = [query]

    metrics = plan.get("metrics", [])
    if metrics:
        parts.append(f"Metrics: {', '.join(metrics)}")

    grouping = plan.get("grouping")
    if grouping:
        parts.append(f"Group by: {grouping}")

    filters = plan.get("filters", {})
    for key, value in filters.items():
        if value and value != "null":
            parts.append(f"Filter {key}: {value}")

    return " | ".join(parts)
