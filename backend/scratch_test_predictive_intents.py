import asyncio
import sys
import os

# Set up paths
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from agents.predictive_followup_agent import run

def test():
    # Construct a dummy prediction context
    context = {
        "query": "Forecast revenue by country for the next 3 months",
        "result": {
            "pipeline_type": "PREDICTIVE",
            "prediction": {
                "target_column": "revenue",
                "table_name": "sales",
                "horizon": 3,
                "group_dimensions": ["country"],
                "predictions": [
                    {
                        "group": "Australia",
                        "final_value": 520000,
                        "historical": [{"value": 400000}, {"value": 450000}],
                        "forecast": [{"value": 470000}, {"value": 520000}]
                    },
                    {
                        "group": "India",
                        "final_value": 490000,
                        "historical": [{"value": 300000}, {"value": 350000}],
                        "forecast": [{"value": 400000}, {"value": 490000}]
                    },
                    {
                        "group": "Canada",
                        "final_value": 470000,
                        "historical": [{"value": 200000}, {"value": 250000}],
                        "forecast": [{"value": 300000}, {"value": 470000}]
                    }
                ]
            },
            "visualization": {
                "problem_type": "forecasting",
                "mode": "forecast"
            }
        }
    }
    
    queries = [
        "What about India?",
        "Compare India with Australia",
        "Why is Australia highest, and will it remain highest next year?"
    ]
    
    with open("test_predictive_intents.txt", "w", encoding="utf-8") as f:
        for q in queries:
            print(f"Testing: {q}")
            try:
                res = run(q, context, [])
                f.write(f"\n=== Query: {q} ===\n")
                f.write(f"Reply: {res.get('reply')}\n")
                if res.get('new_response'):
                    f.write(f"New Viz: {res['new_response']['result']['visualization']['charts'][0]['type']}\n")
            except Exception as e:
                f.write(f"Error on '{q}': {e}\n")

if __name__ == "__main__":
    test()
