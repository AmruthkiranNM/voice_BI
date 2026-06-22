"""
RAG Retriever Agent

Uses the FAISS vector store to retrieve database schema documents
that are most relevant to the user's query. This provides context
to the SQL Generator Agent, preventing hallucinated table/column names.

When ``table_name`` is provided, retrieval is pinned to that table only
so queries always target the dataset the user uploaded in this session.
"""

import logging
from services.vector_store import search, is_index_ready
from models.schema_loader import generate_table_document

logger = logging.getLogger(__name__)


def run(query: str, plan: dict, table_name: str | None = None) -> dict:
    """
    Retrieve relevant schema documents using RAG.

    Constructs an enriched search query from the user query and plan,
    then searches the FAISS vector store for matching schema documents.

    Args:
        query: Original natural language query.
        plan: Execution plan from the Planner Agent.
        table_name: When set, use only this uploaded table (skip vector search).

    Returns:
        Dictionary with retrieved schema context.
    """
    logger.info("[RAG Agent] Retrieving schema for query: %s", query[:80])

    if table_name:
        return _context_for_table(table_name)

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

    rag_output = {
        "retrieved_tables": retrieved_tables,
        "schema_context": schema_context,
        "num_results": len(results),
        "similarity_scores": {
            r["table_name"]: r["similarity_score"] for r in results
        },
        "pinned_table": None,
    }

    logger.info(
        "[RAG Agent] Retrieved %d tables: %s",
        len(retrieved_tables),
        retrieved_tables,
    )

    return rag_output


def _context_for_table(table_name: str) -> dict:
    """Build schema context for the active uploaded table only."""
    document = generate_table_document(table_name)
    logger.info("[RAG Agent] Pinned to active table: %s", table_name)
    return {
        "retrieved_tables": [table_name],
        "schema_context": document,
        "num_results": 1,
        "similarity_scores": {table_name: 1.0},
        "pinned_table": table_name,
    }


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
