import logging
import pandas as pd
from fastapi import APIRouter, UploadFile, File, HTTPException
from pathlib import Path
import sqlite3

from config import DATABASE_PATH
from services.vector_store import build_index
from models.schema_loader import generate_schema_documents
from services.database import get_all_table_names

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Upload"])

@router.post("/upload")
async def upload_dataset(file: UploadFile = File(...)):
    """Upload a CSV dataset, create a table, and rebuild the RAG index."""
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")
        
    try:
        # Read the CSV into pandas, with fallback encodings for Excel-exported CSVs
        try:
            df = pd.read_csv(file.file)
        except UnicodeDecodeError:
            file.file.seek(0)
            try:
                df = pd.read_csv(file.file, encoding="ISO-8859-1")
            except UnicodeDecodeError:
                file.file.seek(0)
                df = pd.read_csv(file.file, encoding="cp1252")
        
        # Clean the table name (e.g. "My Data.csv" -> "my_data")
        table_name = Path(file.filename).stem.lower().replace(" ", "_").replace("-", "_")
        
        # Write to SQLite database (replace if exists)
        conn = sqlite3.connect(DATABASE_PATH)
        df.to_sql(table_name, conn, if_exists="replace", index=False)
        conn.close()
        
        # Rebuild the RAG Vector Store to map this new table
        schema_docs = generate_schema_documents()
        if schema_docs:
            build_index(schema_docs)
        
        tables = get_all_table_names()
        
        logger.info(f"Successfully uploaded {file.filename} as table {table_name}")
        return {
            "success": True, 
            "table_name": table_name, 
            "total_tables": len(tables),
            "message": f"Dataset '{table_name}' successfully imported and indexed!"
        }
    
    except Exception as e:
        logger.exception("Upload failed")
        raise HTTPException(status_code=500, detail=str(e))
