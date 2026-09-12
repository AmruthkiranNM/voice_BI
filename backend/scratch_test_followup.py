import asyncio
import sys
import os

# Set up paths
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from agents.predictive_followup_agent import run

def test():
    # Construct a dummy prediction context
    context = {
        "query": "Forecast revenue by country for the next 6 months",
        "result": {
            "pipeline_type": "PREDICTIVE",
            "prediction": {
                "target_column": "revenue",
                "table_name": "sales_data",
                "horizon": 6,
                "group_dimensions": ["country"],
                "predictions": [
                    {
                        "group": "US",
                        "final_value": 5000,
                        "historical": [{"value": 4000}, {"value": 4500}],
                        "forecast": [{"value": 4700}, {"value": 5000}]
                    },
                    {
                        "group": "UK",
                        "final_value": 3000,
                        "historical": [{"value": 2000}, {"value": 2500}],
                        "forecast": [{"value": 2700}, {"value": 3000}]
                    }
                ]
            },
            "visualization": {
                "problem_type": "forecasting",
                "mode": "forecast"
            }
        }
    }
    
    print("=== Test 1: Rank Highest ===")
    res1 = run("Which country has the highest predicted revenue?", context, [])
    print(f"Reply: {res1.get('reply')}")
    if res1.get('new_response'):
        print(f"New Viz Type: {res1['new_response']['result']['visualization']['charts'][0]['type']}")
        
    print("\n=== Test 2: Growth Highest ===")
    res2 = run("Which country has the highest growth?", context, [])
    print(f"Reply: {res2.get('reply')}")
    if res2.get('new_response'):
        print(f"New Viz Type: {res2['new_response']['result']['visualization']['charts'][0]['type']}")

    print("\n=== Test 3: Change Horizon ===")
    res3 = run("Make it 12 months", context, [])
    print(f"Reply: {res3.get('reply')}")
    # Note: Test 3 might fail because we don't have the real sqlite DB set up in this test environment

if __name__ == "__main__":
    test()
