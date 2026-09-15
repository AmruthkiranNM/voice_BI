import os
import sys
import pandas as pd
from unittest.mock import patch

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from prediction.schemas import UniversalPredictionResult, ForecastingRow
from prediction import service
from agents import predictive_followup_agent
from agents import ml_agent

def test_hierarchical_lifecycle():
    """
    Simulates the 5-step hierarchical query lifecycle:
    1. Initial Prediction context setup (from prediction engine)
    2. Follow-up query parsing ("What about their top products?")
    3. Derived insights generation
    4. Visualization metadata building
    """
    
    # Step 1: Initial prediction context
    # Assume the user asked "Will the top 3 countries remain the same next year?"
    # The initial prediction result contains Country-level forecasts.
    initial_result = UniversalPredictionResult(
        target_column="REVENUE",
        table_name="sales",
        task_type="grouped_forecasting",
        dimensions=["COUNTRY"],
        raw_forecast_results=[
            {
                "group": "US",
                "group_dict": {"COUNTRY": "US"},
                "final_value": 2000,
                "historical": [ForecastingRow(date="2020-01-01", is_historical=True, value=1000)],
                "forecast": [ForecastingRow(date="2021-01-01", is_historical=False, value=2000)]
            },
            {
                "group": "UK",
                "group_dict": {"COUNTRY": "UK"},
                "final_value": 1500,
                "historical": [ForecastingRow(date="2020-01-01", is_historical=True, value=1000)],
                "forecast": [ForecastingRow(date="2021-01-01", is_historical=False, value=1500)]
            }
        ],
        available_granularities=[["COUNTRY"], ["COUNTRY", "PRODUCT"]]
    )
    
    context = {
        "table_name": "sales",
        "result": {
            "prediction": initial_result.__dict__
        }
    }
    
    # Step 2: Predictive follow-up intent detection
    intent_data = {
        "intent": "hierarchical_forecast",
        "new_child_dimension": "PRODUCT"
    }
    
    # We mock the predict_rows call to simulate the engine generating the new Country x Product forecasts
    mock_predict_result = UniversalPredictionResult(
        target_column="REVENUE",
        table_name="sales",
        task_type="grouped_forecasting",
        dimensions=["COUNTRY", "PRODUCT"],
        raw_forecast_results=[
            {"group_dict": {"COUNTRY": "US", "PRODUCT": "A"}, "final_value": 1200, "forecast": []},
            {"group_dict": {"COUNTRY": "US", "PRODUCT": "B"}, "final_value": 800, "forecast": []},
            {"group_dict": {"COUNTRY": "UK", "PRODUCT": "A"}, "final_value": 1500, "forecast": []}
        ]
    )
    
    with patch("prediction.service.predict_rows") as mock_predict_rows:
        mock_predict_rows.return_value = mock_predict_result
        
        # Step 3: Handle the hierarchical forecast
        followup_res = predictive_followup_agent._handle_hierarchical_forecast("What about their top products?", intent_data, context)
        
        new_pred = followup_res["new_response"]["result"]["prediction"]
        
        # Verify derived insights exist
        assert "derived_insights" in new_pred
        assert new_pred["derived_insights"]["task_type"] == "hierarchical_ranking"
        
        hierarchy = new_pred["derived_insights"]["hierarchy"]
        assert "US" in hierarchy
        assert hierarchy["US"][0]["child"] == "A"
        assert hierarchy["US"][0]["final_value"] == 1200
        assert hierarchy["US"][1]["child"] == "B"
        assert hierarchy["US"][1]["final_value"] == 800
        
        # Step 4: Verify ml_agent visualizer can process the derived insights
        # Note: We test the specific hierarchical metadata builder part
        from agents.ml_agent import _build_visualization_metadata
        
        # Convert prediction dict back to a shape that visualization expects
        visual_meta = _build_visualization_metadata(new_pred, is_single_customer=False)
        
        assert visual_meta["type"] == "prediction"
        assert visual_meta["prediction_type"] == "hierarchical_ranking"
        assert "hierarchy" in visual_meta["prediction_data"]
        assert visual_meta["prediction_data"]["hierarchy"]["US"][0]["child"] == "A"
