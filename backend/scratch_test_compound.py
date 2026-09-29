import asyncio
import json
import logging
import sys
from agents.orchestrator import process_query

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

TESTS = [
    (
        "TEST 1: Rank countries by revenue, then show the top 3 products within each of the top 3 countries.",
        "Rank countries by revenue, then show the top 3 products within each of the top 3 countries."
    ),
    (
        "TEST 2: Show the top 5 products by revenue and also show the top 3 regions.",
        "Show the top 5 products by revenue and also show the top 3 regions."
    ),
    (
        "TEST 3: Compare APAC revenue with Americas revenue and show their top products.",
        "Compare APAC revenue with Americas revenue and show their top products."
    ),
    (
        "TEST 4: Show total revenue and total boxes sold.",
        "Show total revenue and total boxes sold."
    ),
    (
        "TEST 5: Rank countries by revenue, then show the top 3 products within each country.",
        "Rank countries by revenue, then show the top 3 products within each country."
    ),
    (
        "TEST 6: Which are the highest selling bars in Australia?",
        "Which are the highest selling bars in Australia?"
    )
]

def run_tests():
    for name, query in TESTS:
        print("\n" + "="*80)
        print(f"RUNNING {name}")
        print("="*80)
        
        # Need to ensure cache_mode=False so it actually generates SQL
        result = process_query(query, table_names=["sales"], cache_mode=False)
        
        if result["success"]:
            print("\n✅ SUCCESS")
            print("SQL GENERATED:\n")
            print(result.get("sql", "N/A"))
            print(f"\nROWS RETURNED: {result.get('result', {}).get('row_count')}")
            if result.get("result", {}).get("rows"):
                print("SAMPLE ROW: ", result["result"]["rows"][0])
        else:
            print("\n❌ FAILED")
            print("ERROR: ", result.get("error"))
            if result.get("sql"):
                print("FAILED SQL:\n", result["sql"])

if __name__ == "__main__":
    run_tests()
