"""
Configuration module for the Agentic AI BI System.

Centralizes all configuration constants, API keys, model settings,
and database paths. Uses environment variables with sensible defaults.
"""

import os
from pathlib import Path

# ──────────────────────────────────────────────
# Project Paths
# ──────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
VECTOR_STORE_DIR = BASE_DIR / "vector_store"

# ──────────────────────────────────────────────
# Database Configuration
# ──────────────────────────────────────────────
DATABASE_PATH = str(DATA_DIR / "business.db")

# ──────────────────────────────────────────────
# LLM Configuration
# ──────────────────────────────────────────────
# Uses local Ollama server
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:3b")

LLM_PROVIDER = "ollama"

# ──────────────────────────────────────────────
# Embedding Configuration
# ──────────────────────────────────────────────
# sentence-transformers model for schema embeddings
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL", "all-MiniLM-L6-v2"
)

# Number of top-k schema chunks to retrieve via RAG
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "5"))

# ──────────────────────────────────────────────
# Security / Validator Settings
# ──────────────────────────────────────────────
# SQL keywords that are always blocked
BLOCKED_SQL_KEYWORDS = [
    "DROP", "DELETE", "UPDATE", "INSERT", "ALTER",
    "TRUNCATE", "EXEC", "EXECUTE", "CREATE", "GRANT",
    "REVOKE", "--", "/*", "*/", "xp_", "sp_",
]

# Maximum rows returned from any query
MAX_RESULT_ROWS = int(os.getenv("MAX_RESULT_ROWS", "500"))

# ──────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
