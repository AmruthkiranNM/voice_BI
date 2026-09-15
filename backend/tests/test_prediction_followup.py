import os
import sys
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from prediction import predictor
from prediction.schemas import UniversalPredictionResult
from agents import predictive_followup_agent

def test_predictor_insufficient_history():
    df = pd.DataFrame({
        "DATE": pd.date_range("2020-01-01", periods=10),
        "COUNTRY": ["US", "US", "US", "UK", "UK", "US", "US", "US", "US", "US"],
        "PRODUCT": ["A", "A", "A", "A", "A", "A", "A", "A", "A", "A"],
        "REVENUE": [100, 110, 120, 50, None, 130, 140, 150, 160, 170]
    })
    
    dim1 = {"dim_df": pd.DataFrame({"COUNTRY": ["US", "UK"]}), "join_key_base": "COUNTRY", "join_key_dim": "COUNTRY", "join_key_target": "COUNTRY", "group_column": "COUNTRY", "dim_name": "COUNTRY"}
    dim2 = {"dim_df": pd.DataFrame({"PRODUCT": ["A"]}), "join_key_base": "PRODUCT", "join_key_dim": "PRODUCT", "join_key_target": "PRODUCT", "group_column": "PRODUCT", "dim_name": "PRODUCT"}
    
    class MockDetection:
        def __init__(self):
            self.date_column = "DATE"
            self.target_column = "REVENUE"
            
    with patch("prediction.predictor.detector.detect") as mock_detect:
        mock_detect.return_value = MockDetection()
        result = predictor.predict_grouped_forecast(
            df,
            dimensions=[dim1, dim2],
            target_col="REVENUE",
            steps=3,
            frequency="days",
            table_name="sales",
            ranking_metric="growth"
        )
    
    print("RAW_FORECAST_RESULTS:", result.raw_forecast_results)
    uk_pred = next((p for p in getattr(result, "raw_forecast_results", []) if p["group"] == "UK - A"), None)
    assert uk_pred is not None
    assert uk_pred.get("status") == "insufficient_history"
    assert uk_pred.get("final_value") is None
    
    us_pred = next((p for p in getattr(result, "raw_forecast_results", []) if p["group"] == "US - A"), None)
    assert us_pred is not None
    assert us_pred.get("status") != "insufficient_history"
    assert us_pred.get("final_value") is not None


def test_followup_deterministic_calculation_does_not_mutate():
    context = {
        "query": "Rank highest next year",
        "result": {
            "prediction": {
                "task_type": "grouped_forecasting",
                "table_name": "sales",
                "dimensions": ["COUNTRY"],
                "target_column": "REVENUE",
                "predictions": [
                    {"group": "US", "final_value": 500, "forecast": []},
                    {"group": "UK", "final_value": 300, "forecast": []}
                ],
                "raw_forecast_results": [
                    {"group": "US", "final_value": 500},
                    {"group": "UK", "final_value": 300}
                ]
            }
        }
    }
    
    intent_data = {"intent": "rank_highest"}
    res = predictive_followup_agent._handle_deterministic_calculation("Which one is highest?", intent_data, context)
    
    new_result = res["new_response"]["result"]
    assert "derived_insights" in new_result["prediction"]
    assert new_result["prediction"]["derived_insights"]["task_type"] == "grouped_ranking"
    assert new_result["prediction"]["derived_insights"]["sorted_preds"][0]["group"] == "US"
    assert len(new_result["prediction"]["predictions"]) == 2


@patch("prediction.service.predict_rows")
def test_hierarchical_forecast_intent(mock_predict):
    mock_result = UniversalPredictionResult(
        target_column="REVENUE",
        table_name="sales",
        task_type="grouped_forecasting",
        raw_forecast_results=[
            {"group_dict": {"COUNTRY": "US", "PRODUCT": "A"}, "final_value": 1500, "forecast": []},
            {"group_dict": {"COUNTRY": "US", "PRODUCT": "B"}, "final_value": 500, "forecast": []},
            {"group_dict": {"COUNTRY": "UK", "PRODUCT": "A"}, "final_value": 800, "forecast": []}
        ]
    )
    mock_predict.return_value = mock_result
    
    context = {
        "table_name": "sales",
        "result": {
            "prediction": {
                "dimensions": ["COUNTRY"],
                "target_column": "REVENUE"
            }
        }
    }
    
    intent_data = {
        "intent": "hierarchical_forecast",
        "new_child_dimension": "PRODUCT"
    }
    
    res = predictive_followup_agent._handle_hierarchical_forecast("What about their top products?", intent_data, context)
    
    assert res["new_response"] is not None
    new_pred = res["new_response"]["result"]["prediction"]
    
    assert "derived_insights" in new_pred
    assert new_pred["derived_insights"]["task_type"] == "hierarchical_ranking"
    
    hierarchy = new_pred["derived_insights"]["hierarchy"]
    assert "US" in hierarchy
    assert "UK" in hierarchy
    assert hierarchy["US"][0]["child"] == "A"
    assert hierarchy["US"][0]["final_value"] == 1500
    assert hierarchy["US"][1]["child"] == "B"
