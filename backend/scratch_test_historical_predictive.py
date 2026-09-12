import asyncio
import sys
import os

# Set up paths
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from agents.followup_orchestrator import run_followup

def test():
    # Construct a dummy historical context
    context = {
        "query": "Rank countries by revenue, then show the top 3 products within each of the top 3 countries.",
        "table_name": "sales",
        "result": {
            "pipeline_type": "ANALYTICAL",
            "columns": ["country", "product", "revenue"],
            "rows": [
                {"country": "New Zealand", "product": "70% Dark Bites", "revenue": 413273},
                {"country": "New Zealand", "product": "Raspberry Choco", "revenue": 393757},
                {"country": "New Zealand", "product": "After Nines", "revenue": 388220},
                {"country": "Canada", "product": "After Nines", "revenue": 412482},
                {"country": "Canada", "product": "Organic Choco Syrup", "revenue": 398335},
                {"country": "Canada", "product": "50% Dark Bites", "revenue": 374024},
                {"country": "India", "product": "Organic Choco Syrup", "revenue": 402269},
                {"country": "India", "product": "Milk Bars", "revenue": 394534},
                {"country": "India", "product": "Almond Choco", "revenue": 374220}
            ]
        }
    }
    
    message = "why is it like this...will it be same next year"
    
    print("=== Testing Historical to Predictive ===")
    # run_followup is synchronous in followup_orchestrator
    try:
        reply = run_followup(message, context, [])
        with open("test_output.txt", "w", encoding="utf-8") as f:
            if isinstance(reply, dict):
                f.write("\n[Final Reply Text]:\n")
                f.write(reply.get("reply", "") + "\n")
                if reply.get("new_response"):
                    f.write("\n[New Visualization Type]:\n")
                    f.write(reply["new_response"]["result"]["visualization"]["charts"][0]["type"] + "\n")
            else:
                f.write("\n[Final Reply Text]:\n")
                f.write(str(reply) + "\n")
        print("Test output written to test_output.txt")
    except Exception as e:
        print(f"Error during execution: {e}")

if __name__ == "__main__":
    test()
