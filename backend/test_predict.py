import json
import io
import sys
from agents.ml_agent import run

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def run_tests():
    tests = [
        "Forecast the number of boxes sold in each region for the next 3 months and identify the region with the strongest expected growth.",
        "Forecast revenue for the next 6 months by country and product category and identify the highest expected revenue.",
        "Predict next month's sales.",
    ]
    
    for q in tests:
        print(f"\n==================================\nTEST: {q}\n")
        res = run(q)
        print("PIPELINE TYPE:", res.get("result", {}).get("pipeline_type"))
        
        viz = res.get("result", {}).get("visualization", {})
        if viz:
            charts = viz.get("charts", [])
            for c in charts:
                print("CHART TYPE:", c.get("type"))
                print("CHART TITLE:", c.get("title"))
            
        pred = res.get("result", {}).get("prediction", {})
        if pred:
            if "best_group" in pred:
                print("BEST GROUP:", pred["best_group"])
            if "group_dimensions" in pred:
                print("DIMENSIONS:", pred["group_dimensions"])
            
            preds = pred.get("predictions", [])
            if preds:
                print("TOP 3 PREDICTIONS:")
                for p in preds[:3]:
                    print(f"  {p.get('group')} -> {p.get('final_value')}")
            else:
                print("No predictions array found.")
                
        print("\nINSIGHT:", res.get("insight"))

if __name__ == "__main__":
    run_tests()
