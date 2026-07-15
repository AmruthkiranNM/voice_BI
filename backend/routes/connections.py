"""
Database Connection API — connect to an external Postgres-compatible
database (Supabase, Neon, RDS, ...) and import selected tables into the
local workspace. See services/db_import.py for why this is a snapshot
import rather than a live query passthrough.
"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.database import get_all_table_names
from services.db_import import list_tables, import_tables

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/connections", tags=["Connections"])


class TestConnectionRequest(BaseModel):
    connection_string: str = Field(..., min_length=5, max_length=2000)


class ImportRequest(BaseModel):
    connection_string: str = Field(..., min_length=5, max_length=2000)
    tables: list[str] = Field(..., min_length=1, max_length=50)


@router.post("/test")
def test_connection(request: TestConnectionRequest):
    """Connect and list available tables, without importing anything."""
    try:
        tables = list_tables(request.connection_string)
        return {"success": True, "tables": tables}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Connection test failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import")
def import_connection(request: ImportRequest):
    """Import the selected tables into the local workspace."""
    try:
        result = import_tables(request.connection_string, request.tables)
        result["total_tables"] = len(get_all_table_names())
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Import failed")
        raise HTTPException(status_code=500, detail=str(e))
