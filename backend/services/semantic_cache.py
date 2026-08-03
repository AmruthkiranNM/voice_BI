"""
Semantic Cache Service using FAISS + SQLite
"""

import sqlite3
import json
import logging
import faiss
import numpy as np
import os
from sentence_transformers import SentenceTransformer
from services.database import get_database_path, get_all_table_names
import hashlib

logger = logging.getLogger(__name__)

CACHE_DB_PATH = "semantic_cache.db"
EMBEDDING_DIM = 384
SIMILARITY_THRESHOLD = 0.92

_model = None
_index = None
_id_to_db_id = []

def _get_schema_fingerprint() -> str:
    from services.database import get_all_table_names, get_database_path
    from pathlib import Path
    tables = ",".join(sorted(get_all_table_names()))
    db_path = Path(get_database_path())
    mtime = db_path.stat().st_mtime if db_path.exists() else 0
    raw = f"{tables}:{mtime}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

def init_cache():
    global _model, _index, _id_to_db_id
    try:
        if _model is None:
            _model = SentenceTransformer('all-MiniLM-L6-v2', device='cpu')
    except Exception as e:
        logger.error(f"Failed to load SentenceTransformer: {e}")
        return

    _index = faiss.IndexFlatIP(EMBEDDING_DIM)
    _id_to_db_id = []
    
    # Initialize SQLite
    conn = sqlite3.connect(CACHE_DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS semantic_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT,
            model_name TEXT,
            fast_mode BOOLEAN,
            skip_insight BOOLEAN,
            table_name TEXT,
            fingerprint TEXT,
            embedding BLOB,
            response TEXT
        )
    ''')
    
    # Load into FAISS
    c.execute("SELECT id, embedding FROM semantic_cache")
    rows = c.fetchall()
    
    if rows:
        embeddings = []
        for row in rows:
            _id_to_db_id.append(row[0])
            emb = np.frombuffer(row[1], dtype=np.float32)
            embeddings.append(emb)
        
        if embeddings:
            emb_matrix = np.vstack(embeddings)
            _index.add(emb_matrix)
            
    conn.commit()
    conn.close()
    logger.info(f"[SemanticCache] Initialized with {_index.ntotal if _index else 0} entries.")

def get_semantic_cache(query: str, model_name: str, fast_mode: bool, skip_insight: bool, table_name: str) -> dict | None:
    if not _model or not _index or _index.ntotal == 0:
        return None
        
    fp = _get_schema_fingerprint()
    emb = _model.encode([query])
    faiss.normalize_L2(emb)
    
    D, I = _index.search(emb, min(5, _index.ntotal))
    
    conn = sqlite3.connect(CACHE_DB_PATH)
    c = conn.cursor()
    
    for score, idx in zip(D[0], I[0]):
        if score >= SIMILARITY_THRESHOLD:
            db_id = _id_to_db_id[idx]
            c.execute("SELECT query, model_name, fast_mode, skip_insight, table_name, fingerprint, response FROM semantic_cache WHERE id = ?", (db_id,))
            row = c.fetchone()
            if row:
                r_query, r_model, r_fast, r_skip, r_table, r_fp, r_response = row
                
                # Check constraints
                if (r_model == (model_name or "") and 
                    bool(r_fast) == fast_mode and 
                    bool(r_skip) == skip_insight and 
                    (r_table or "") == (table_name or "") and
                    r_fp == fp):
                    
                    logger.info(f"[SemanticCache] HIT: '{query}' matched '{r_query}' (score: {score:.3f})")
                    response_dict = json.loads(r_response)
                    
                    # Update metadata
                    if "metadata" not in response_dict:
                        response_dict["metadata"] = {}
                    response_dict["metadata"]["cache_hit"] = True
                    response_dict["metadata"]["semantic_hit"] = True
                    response_dict["metadata"]["matched_query"] = r_query
                    response_dict["metadata"]["similarity_score"] = float(score)
                    
                    conn.close()
                    return response_dict
    
    conn.close()
    return None

def set_semantic_cache(query: str, model_name: str, fast_mode: bool, skip_insight: bool, table_name: str, response: dict):
    if not _model or not _index or not response.get("success"):
        return
        
    fp = _get_schema_fingerprint()
    emb = _model.encode([query])
    faiss.normalize_L2(emb)
    
    conn = sqlite3.connect(CACHE_DB_PATH)
    c = conn.cursor()
    
    c.execute('''
        INSERT INTO semantic_cache 
        (query, model_name, fast_mode, skip_insight, table_name, fingerprint, embedding, response)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        query, 
        model_name or "", 
        fast_mode, 
        skip_insight, 
        table_name or "", 
        fp, 
        emb.tobytes(), 
        json.dumps(response)
    ))
    
    db_id = c.lastrowid
    conn.commit()
    conn.close()
    
    _index.add(emb)
    _id_to_db_id.append(db_id)
    logger.info(f"[SemanticCache] STORED query: '{query}'")

def invalidate_semantic_cache():
    if os.path.exists(CACHE_DB_PATH):
        os.remove(CACHE_DB_PATH)
    init_cache()

# Init on module load
init_cache()
