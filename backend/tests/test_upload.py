"""Tests for CSV upload endpoint."""

import io

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client(temp_database):
    return TestClient(app)


def test_upload_csv_creates_table_with_preview(client, temp_database):
    df = pd.DataFrame({
        "product_name": ["Widget", "Gadget"],
        "sales_amount": [100, 200],
        "region": ["North", "South"],
    })
    buffer = io.StringIO()
    df.to_csv(buffer, index=False)
    buffer.seek(0)

    response = client.post(
        "/api/upload",
        files={"file": ("sales.csv", buffer.getvalue(), "text/csv")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["row_count"] == 2
    assert "product_name" in data["columns"]
    assert len(data["preview_rows"]) == 2
    assert data["domain"]["id"] in ("sales", "detected")
    assert "sales" in data["domain"]["label"].lower() or "amount" in data["domain"]["label"].lower()
    joined = " ".join(data["suggestions"]).lower()
    assert len(data["suggestions"]) > 0
    assert any(word in joined for word in ("revenue", "money", "sold", "sales", "best", "top"))


def test_upload_rejects_non_csv(client, temp_database):
    response = client.post(
        "/api/upload",
        files={"file": ("data.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 400


def test_query_blocked_without_data(client, temp_database):
    response = client.post("/api/query", json={"query": "show total sales"})
    assert response.status_code == 400
