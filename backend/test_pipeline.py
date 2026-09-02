import os
import sys
import json

# Ensure backend is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agents import orchestrator
import traceback

queries = {
    "Tests": [
        "Forecast sales revenue for the next 6 months.",
        "Forecast revenue for the next 3 months.",
        "Forecast the sales amount for the next 12 months.",
        "Forecast the number of customers for the next 6 months.",
        "Forecast boxes sold for the next 6 months.",
        "Forecast AMOUNT for the next 6 months.",
        "What was total revenue by country?",
        "Which product generated the most revenue?"
    ]
}

def run_tests():
    print("================== PIPELINE TESTS ==================")
    for category, qs in queries.items():
        print(f"\n--- {category} ---")
        for q in qs:
            print(f"Query: {q}")
            try:
                # Run the orchestrator directly
                res = orchestrator.process_query(q, cache_mode=False)
                
                pipeline_type = res.get("metadata", {}).get("pipeline_type", "ANALYTICAL")
                success = res.get("success", False)
                
                print(f"  -> Success: {success}, Pipeline: {pipeline_type}")
                
                if success:
                    if pipeline_type == "PREDICTIVE":
                        viz_mode = res.get("result", {}).get("visualization", {})
                        if viz_mode is not None:
                            viz_mode = viz_mode.get("mode")
                        print(f"  -> Viz Mode: {viz_mode}")
                        print(f"  -> Target Column: {res.get('result', {}).get('prediction', {}).get('target_column')}")
                        if res.get('result', {}).get('error'):
                            print(f"  -> Inner Error: {res.get('result', {}).get('error')}")
                    else:
                        print(f"  -> Rows returned: {res.get('result', {}).get('row_count')}")
                        print(f"  -> Generated SQL: {res.get('sql')}")
                else:
                    print(f"  -> Error: {res.get('error')}")
                    
            except Exception as e:
                print(f"  -> Exception: {e}")
                traceback.print_exc()

if __name__ == "__main__":
    run_tests()
