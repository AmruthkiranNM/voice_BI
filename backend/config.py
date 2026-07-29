"""
Configuration module for the Agentic AI BI System.

Centralizes all configuration constants, API keys, model settings,
and database paths. Uses environment variables with sensible defaults.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

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
# Supports: "ollama" (local, default — keeps the "100% local" guarantee) or
# "groq" (free-tier cloud API, much larger models, but data leaves the machine).
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:3b")

# Per-call timeout for Ollama generation requests. Kept well under the old
# 300s default so a stuck/overloaded local model fails fast with a clear
# error instead of hanging the request for 5 minutes on modest hardware.
OLLAMA_TIMEOUT_SECONDS = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "180"))

# Groq (https://console.groq.com) — free tier, OpenAI-compatible chat API.
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_TIMEOUT_SECONDS = int(os.getenv("GROQ_TIMEOUT_SECONDS", "60"))


# ──────────────────────────────────────────────
# Embedding Configuration
# ──────────────────────────────────────────────
# sentence-transformers model for schema embeddings
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL", "all-MiniLM-L6-v2"
)

# Force embeddings onto CPU so the GPU's limited VRAM (e.g. 4GB on a
# GTX 1650) is reserved entirely for the Ollama LLM. The embedding model
# is tiny and runs fine on CPU.
EMBEDDING_DEVICE = os.getenv("EMBEDDING_DEVICE", "cpu")

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

# CSV upload limits
MAX_UPLOAD_ROWS = int(os.getenv("MAX_UPLOAD_ROWS", "100000"))
MAX_UPLOAD_COLUMNS = int(os.getenv("MAX_UPLOAD_COLUMNS", "100"))
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "50"))

# ──────────────────────────────────────────────
# Query Cache
# ──────────────────────────────────────────────
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "3600"))
CACHE_MAX_ENTRIES = int(os.getenv("CACHE_MAX_ENTRIES", "100"))

# ──────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ──────────────────────────────────────────────
# Auth
# ──────────────────────────────────────────────
# Signs session tokens. The default only works for a single local dev
# instance — set JWT_SECRET in .env for anything shared/deployed.
JWT_SECRET = os.getenv("JWT_SECRET", "dev-insecure-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", str(60 * 24 * 7)))  # 7 days
