"""
RAG Retriever Agent

Uses the FAISS vector store to retrieve database schema documents
that are most relevant to the user's query. This provides context
to the SQL Generator Agent, preventing hallucinated table/column names.
"""

import logging
from services.vector_store import search, is_index_ready

logger = logging.getLogger(__name__)


def run(query: str, plan: dict) -> dict:
    """
    Retrieve relevant schema documents using RAG.

    Constructs an enriched search query from the user query and plan,
    then searches the FAISS vector store for matching schema documents.

    Args:
        query: Original natural language query.
        plan: Execution plan from the Planner Agent.

    Returns:
        Dictionary with retrieved schema context.
    """
    logger.info("[RAG Agent] Retrieving schema for query: %s", query[:80])

    if not is_index_ready():
        raise RuntimeError(
            "FAISS vector store is not initialized. "
            "Ensure the system startup has built the index."
        )

    # Enrich the search query with plan context for better retrieval
    enriched_query = _build_enriched_query(query, plan)
    logger.info("[RAG Agent] Enriched search query: %s", enriched_query[:120])

    # Search FAISS
    results = search(enriched_query)

    # Extract unique table names and schema text
    retrieved_tables = []
    schema_context_parts = []
    seen_tables = set()

    for result in results:
        table_name = result["table_name"]
        if table_name not in seen_tables:
            seen_tables.add(table_name)
            retrieved_tables.append(table_name)
            schema_context_parts.append(result["document"])

    schema_context = "\n\n---\n\n".join(schema_context_parts)

    rag_output = {
        "retrieved_tables": retrieved_tables,
        "schema_context": schema_context,
        "num_results": len(results),
        "similarity_scores": {
            r["table_name"]: r["similarity_score"] for r in results
        },
    }

    logger.info(
        "[RAG Agent] Retrieved %d tables: %s",
        len(retrieved_tables),
        retrieved_tables,
    )

    return rag_output


def _build_enriched_query(query: str, plan: dict) -> str:
    """
    Build an enriched search query by combining the original query
    with extracted metrics and filters from the plan.
    """
    parts = [query]

    # Add metrics for better table retrieval
    metrics = plan.get("metrics", [])
    if metrics:
        parts.append(f"Metrics: {', '.join(metrics)}")

    # Add grouping info
    grouping = plan.get("grouping")
    if grouping:
        parts.append(f"Group by: {grouping}")

    # Add filter context
    filters = plan.get("filters", {})
    for key, value in filters.items():
        if value and value != "null":
            parts.append(f"Filter {key}: {value}")

    return " | ".join(parts)
