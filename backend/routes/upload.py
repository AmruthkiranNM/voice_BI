import logging
import pandas as pd
from fastapi import APIRouter, UploadFile, File, HTTPException

from config import MAX_UPLOAD_MB
from services.database import get_all_table_names
from services.ingest import ingest_dataframe, rebuild_index

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Upload"])


@router.post("/upload")
async def upload_dataset(file: UploadFile = File(...)):
    """Upload a business CSV, create a queryable table, and rebuild the RAG index."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")

    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > MAX_UPLOAD_MB:
        raise HTTPException(
            status_code=400,
            detail=f"File too large ({size_mb:.1f} MB). Maximum is {MAX_UPLOAD_MB} MB.",
        )

    try:
        from io import BytesIO
        buffer = BytesIO(content)
        try:
            df = pd.read_csv(buffer)
        except UnicodeDecodeError:
            buffer.seek(0)
            try:
                df = pd.read_csv(buffer, encoding="ISO-8859-1")
            except UnicodeDecodeError:
                buffer.seek(0)
                df = pd.read_csv(buffer, encoding="cp1252")

        result = ingest_dataframe(
            df, file.filename,
            source_label="Uploaded files",
            source_id="local_files",
            source_type="csv",
        )
        rebuild_index()
        result["total_tables"] = len(get_all_table_names())
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Upload failed")
        raise HTTPException(status_code=500, detail=str(e))
