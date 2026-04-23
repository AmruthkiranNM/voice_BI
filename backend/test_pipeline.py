"""
Test Script — Quick Validation

Run this to test the complete pipeline without starting the server.
Usage: python test_pipeline.py
"""

import sys
import os
import json
import logging

# Ensure backend is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-8s │ %(name)-30s │ %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger("test")


def main():
    logger.info("=" * 60)
    logger.info("  Agentic AI BI System — Pipeline Test")
    logger.info("=" * 60)

    # ── Step 1: Initialize Database ──
    logger.info("\n[1/3] Initializing database...")
    from services.database import initialize_database, get_all_table_names
    initialize_database()
    tables = get_all_table_names()
    logger.info("Database tables: %s", tables)

    # ── Step 2: Build FAISS Index ──
    logger.info("\n[2/3] Building FAISS vector store...")
    from models.schema_loader import generate_schema_documents
    from services.vector_store import build_index, load_index

    if not load_index():
        schema_docs = generate_schema_documents()
        logger.info("Schema documents generated: %d", len(schema_docs))
        for doc in schema_docs:
            logger.info("  → Table: %s (%d chars)", doc["table_name"], len(doc["document"]))
        build_index(schema_docs)

    # ── Step 3: Run Test Queries ──
    logger.info("\n[3/3] Testing query pipeline...")
    from agents.orchestrator import process_query

    test_queries = [
        "Show total sales last month",
        "What are the top 5 products by revenue?",
        "How many customers are from Bangalore?",
        "Show monthly sales trend for 2025",
    ]

    for i, query in enumerate(test_queries, 1):
        logger.info("\n" + "─" * 50)
        logger.info("TEST %d: %s", i, query)
        logger.info("─" * 50)

        result = process_query(query)

        if result["success"]:
            logger.info("✅ SQL: %s", result["sql"])
            logger.info("📊 Rows: %d", result["result"]["row_count"])
            logger.info("💡 Insight: %s", result.get("insight", "N/A")[:200])
        else:
            logger.error("❌ Error: %s", result.get("error", "Unknown error"))

        # Print agent logs
        for log_entry in result.get("agent_logs", []):
            logger.info(
                "   [%s] %s (%.0f ms)",
                log_entry["agent"],
                log_entry["status"],
                log_entry["timestamp_ms"],
            )

    logger.info("\n" + "=" * 60)
    logger.info("  Pipeline test complete!")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
