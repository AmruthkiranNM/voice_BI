import logging
from agents.orchestrator import process_query
from config import DATABASE_PATH
import sqlite3

logging.basicConfig(level=logging.INFO)

# Make sure Churn_Modelling is in DB
conn = sqlite3.connect(DATABASE_PATH)
cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [row[0] for row in cursor.fetchall()]
conn.close()
print("DB Tables:", tables)

print("\n--- Sending process_query with table_names=['sales', 'products', 'geo', 'people'] ---")
try:
    result = process_query(
        query="Forecast sales amount for the next 3 months.",
        table_names=['sales', 'products', 'geo', 'people'],
        cache_mode=False,
    )
    if not result['success']:
        print("ERROR:", result['error'])
    else:
        print("SUCCESS")
except Exception as e:
    print("EXCEPTION:", e)
