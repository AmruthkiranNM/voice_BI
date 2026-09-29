import logging
from agents import task_router
from services.sources import list_sources

logging.basicConfig(level=logging.INFO)

query = "Forecast sales amount for the next 3 months."

print("\n--- Route with scope_tables=['sales', 'Churn_Modelling'] ---")
res = task_router.route(query, scope_tables=['sales', 'Churn_Modelling'])
print(res.describe())
print("Blocked:", res.blocked)
print("Alternatives:", res.alternatives)
