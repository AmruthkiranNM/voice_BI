"""
LLM Service Module

Provides a unified interface to interact with LLM providers.
Supports Google Gemini API and a mock fallback for development.
"""

import logging
import json
import re
import time
from typing import Any

from config import LLM_PROVIDER, GEMINI_API_KEY, GEMINI_MODEL, OLLAMA_MODEL

logger = logging.getLogger(__name__)

# Lazy-loaded Gemini model
_gemini_model = None


def _get_gemini_model():
    """Initialize and cache the Gemini model with auto-discovery fallback."""
    global _gemini_model
    if _gemini_model is None:
        import google.generativeai as genai

        if not GEMINI_API_KEY:
            raise ValueError(
                "GEMINI_API_KEY environment variable is not set. "
                "Set it or use LLM_PROVIDER=mock for development."
            )
        genai.configure(api_key=GEMINI_API_KEY)
        
        # Try configured model first, but auto-discover if it fails or doesn't exist
        model_name = GEMINI_MODEL
        try:
            # Check if model exists in available models
            available_models = [
                m.name for m in genai.list_models() 
                if 'generateContent' in m.supported_generation_methods
            ]
            
            # Clean "models/" prefix if present
            clean_available = [m.replace('models/', '') for m in available_models]
            
            if model_name not in clean_available and f"models/{model_name}" not in available_models:
                logger.warning("Configured model %s not found. Available: %s", model_name, clean_available)
                
                # Auto-pick best available model prioritizing widely available free-tier models
                if 'gemini-1.5-flash-8b' in clean_available:
                    model_name = 'gemini-1.5-flash-8b'
                elif 'gemini-1.5-flash' in clean_available:
                    model_name = 'gemini-1.5-flash'
                elif 'gemini-1.0-pro' in clean_available:
                    model_name = 'gemini-1.0-pro'
                elif 'gemini-pro' in clean_available:
                    model_name = 'gemini-pro'
                elif any('flash' in m for m in clean_available):
                    model_name = next(m for m in clean_available if 'flash' in m)
                elif clean_available:
                    model_name = clean_available[0]
                
                logger.info("Auto-fallback to model: %s", model_name)
                
        except Exception as e:
            logger.warning("Could not list models for auto-discovery: %s", e)

        _gemini_model = genai.GenerativeModel(model_name)
        logger.info("Gemini model initialized: %s", model_name)
    return _gemini_model


def call_llm(prompt: str, expect_json: bool = False, provider: str = None) -> str:
    """
    Send a prompt to the configured LLM and return the response text.

    Args:
        prompt: The full prompt string.
        expect_json: If True, attempts to clean response for JSON parsing.
        provider: Override provider for this call.

    Returns:
        Response text from the LLM.
    """
    active_provider = provider or LLM_PROVIDER
    if active_provider == "mock":
        return _mock_llm(prompt)
    elif active_provider == "ollama":
        return _call_ollama(prompt, expect_json)

    return _call_gemini(prompt, expect_json)


def _call_ollama(prompt: str, expect_json: bool = False) -> str:
    """Call a local Ollama instance via HTTP."""
    import urllib.request
    import json
    
    url = "http://localhost:11434/api/generate"
    data = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False
    }
    
    if expect_json:
        data["format"] = "json"
        
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=300) as response:
            result = json.loads(response.read().decode('utf-8'))
            text = result.get('response', '').strip()
            
            if expect_json:
                text = _clean_json_response(text)
                
            logger.debug("Ollama response (first 200 chars): %s", text[:200])
            return text
    except Exception as e:
        logger.error("Ollama API call failed: %s", str(e))
        raise RuntimeError(f"Ollama call failed. Is Ollama running on port 11434? Error: {e}") from e



def _call_gemini(prompt: str, expect_json: bool = False) -> str:
    """Call Google Gemini API with automatic retry on 429 errors."""
    model = _get_gemini_model()
    max_retries = 3
    retry_delay = 5  # Seconds to wait between retries

    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            text = response.text.strip()

            if expect_json:
                text = _clean_json_response(text)

            logger.debug("Gemini response (first 200 chars): %s", text[:200])
            return text

        except Exception as e:
            error_str = str(e)
            
            # Handle 403 Forbidden
            if "403" in error_str and "denied access" in error_str.lower():
                raise RuntimeError(
                    "Gemini API Error (403 Forbidden): Your Google Cloud project has been denied access or suspended by Google. "
                    "This means the API key you provided belongs to a blocked account. Please create a new project in Google AI Studio "
                    "or use the Mock Mode for your presentation."
                ) from e
                
            if "429" in error_str or "quota" in error_str.lower():
                if attempt < max_retries - 1 and "limit: 0" not in error_str:
                    logger.warning(
                        "[LLM Service] Rate limit hit. Retrying in %d seconds... (Attempt %d/%d)",
                        retry_delay, attempt + 1, max_retries
                    )
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue
                else:
                    # If it's a hard limit 0, don't retry, fail fast with a helpful message
                    if "limit: 0" in error_str:
                        raise RuntimeError(
                            "Gemini API Quota Error (Limit: 0). Your Google account cannot use this model on the free tier. "
                            "This usually happens if you are in a region where the free tier is restricted (like the EU/UK) "
                            "or if you need to attach a billing account to your Google Cloud project."
                        ) from e
            
            logger.error("Gemini API call failed: %s", error_str)
            raise RuntimeError(f"LLM call failed: {error_str}") from e
    
    raise RuntimeError("LLM call failed after multiple retries due to rate limits.")


def _clean_json_response(text: str) -> str:
    """
    Clean LLM response to extract valid JSON.
    Handles markdown code blocks and extra text around JSON.
    """
    # Remove markdown code fences
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    text = text.strip()

    # Try to find JSON object or array
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start_idx = text.find(start_char)
        end_idx = text.rfind(end_char)
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            candidate = text[start_idx:end_idx + 1]
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                continue

    return text


def _mock_llm(prompt: str) -> str:
    """
    Intelligent Mock LLM for development/testing without an API key.

    Parses the user's original query from the prompt and uses keyword-based
    rules to generate query-specific plans, SQL, and insights.
    This ensures different queries produce different outputs.
    """
    prompt_lower = prompt.lower()

    # Extract the original user query from the prompt
    user_query = _extract_user_query(prompt)
    logger.info("[Mock LLM] Extracted user query: '%s'", user_query)

    # Route to the appropriate mock handler
    if "query planner agent" in prompt_lower:
        return _mock_planner(user_query)

    if "sql generator agent" in prompt_lower:
        return _mock_sql_generator(user_query, prompt)

    if "insight agent" in prompt_lower:
        return _mock_insight_generator(user_query, prompt)

    return "Mock LLM response for: " + prompt[:100]


# ──────────────────────────────────────────────
# Helper: Extract user query from prompt text
# ──────────────────────────────────────────────

def _extract_user_query(prompt: str) -> str:
    """
    Extract the original user query from the LLM prompt.
    Handles multiple prompt formats used by different agents.
    """
    # Format 1: Planner uses — User Query: "..."
    match = re.search(r'User Query:\s*"([^"]+)"', prompt)
    if match:
        return match.group(1).strip()

    # Format 2: SQL/Insight use — USER QUERY: ...\n═══ or USER QUESTION: ...\n═══
    match = re.search(r'USER (?:QUERY|QUESTION):\s*(.+?)(?:\n═|$)', prompt, re.DOTALL)
    if match:
        return match.group(1).strip()

    # Fallback: return first 100 chars
    return prompt[:100]


# ──────────────────────────────────────────────
# Mock Planner — Keyword-aware plan generation
# ──────────────────────────────────────────────

def _mock_planner(user_query: str) -> str:
    """
    Generate a structured execution plan based on keyword analysis.
    Returns different plans for different types of queries.
    """
    q = user_query.lower()

    # ── Detect intent ──
    intent = "detail"
    if any(w in q for w in ["total", "sum", "revenue", "overall"]):
        intent = "aggregation"
    elif any(w in q for w in ["count", "how many", "number of"]):
        intent = "count"
    elif any(w in q for w in ["trend", "monthly", "weekly", "daily", "over time", "growth"]):
        intent = "trend"
    elif any(w in q for w in ["compare", "vs", "versus", "difference"]):
        intent = "comparison"
    elif any(w in q for w in ["top", "best", "highest", "most", "bottom", "worst", "lowest", "least"]):
        intent = "aggregation"
    elif any(w in q for w in ["by city", "by region", "by product", "by category", "by customer", "by month"]):
        intent = "aggregation"

    # ── Detect metrics ──
    metrics = []
    if any(w in q for w in ["sale", "sales", "revenue", "amount"]):
        metrics.append("sales")
    if any(w in q for w in ["order", "orders"]):
        metrics.append("orders")
    if any(w in q for w in ["customer", "customers"]):
        metrics.append("customers")
    if any(w in q for w in ["product", "products"]):
        metrics.append("products")
    if any(w in q for w in ["quantity", "units"]):
        metrics.append("quantity")
    if not metrics:
        metrics = ["sales"]  # Default

    # ── Detect grouping ──
    grouping = None
    if "by city" in q:
        grouping = "city"
    elif "by region" in q:
        grouping = "region"
    elif "by product" in q or "by product name" in q:
        grouping = "product"
    elif "by category" in q:
        grouping = "category"
    elif "by customer" in q:
        grouping = "customer"
    elif "by month" in q or "monthly" in q:
        grouping = "month"
    elif "by state" in q:
        grouping = "state"

    # ── Detect filters ──
    time_range = None
    if "last month" in q:
        time_range = "last month"
    elif "this month" in q:
        time_range = "this month"
    elif "last year" in q:
        time_range = "last year"
    elif "this year" in q:
        time_range = "this year"
    elif "last week" in q:
        time_range = "last week"

    location = None
    for city in ["bangalore", "mumbai", "delhi", "chennai", "hyderabad", "pune", "kolkata", "jaipur"]:
        if city in q:
            location = city.title()
            break

    category = None
    for cat in ["electronics", "furniture", "stationery"]:
        if cat in q:
            category = cat.title()
            break

    # ── Build steps ──
    steps = []

    if "customer" in q and intent == "detail":
        steps.append("Retrieve customer records from the customers table")
    elif "product" in q and intent == "detail":
        steps.append("Retrieve product records from the products table")
    elif "order" in q and intent == "detail":
        steps.append("Retrieve order records from the orders table")
    else:
        steps.append("Identify relevant tables: " + ", ".join(metrics))

    if time_range:
        steps.append(f"Apply time filter: {time_range}")
    if location:
        steps.append(f"Filter by location: {location}")
    if category:
        steps.append(f"Filter by category: {category}")

    if intent == "aggregation":
        steps.append("Calculate aggregate metrics (SUM/COUNT/AVG)")
    if grouping:
        steps.append(f"Group results by {grouping}")
    if any(w in q for w in ["top", "best", "highest", "bottom", "worst", "lowest"]):
        steps.append("Sort and limit results to get top/bottom entries")

    steps.append("Execute query and return results")

    plan = {
        "original_query": user_query,
        "steps": steps,
        "intent": intent,
        "metrics": metrics,
        "filters": {
            "time_range": time_range,
            "location": location,
            "category": category,
            "other": None,
        },
        "grouping": grouping,
        "requires_aggregation": intent in ("aggregation", "count", "trend"),
        "requires_comparison": intent == "comparison",
    }

    logger.info("[Mock Planner] Intent=%s, Metrics=%s, Grouping=%s", intent, metrics, grouping)
    return json.dumps(plan)


# ──────────────────────────────────────────────
# Mock SQL Generator — Rule-based SQL construction
# ──────────────────────────────────────────────

def _mock_sql_generator(user_query: str, prompt: str) -> str:
    """
    Generate SQL based on keyword detection in the user query.
    Uses the actual database schema (customers, products, orders, sales, regions).

    Key rules:
      - "total"/"sum" → SUM aggregation
      - "count"/"how many" → COUNT
      - "by X" → GROUP BY
      - "top"/"best" → ORDER BY DESC LIMIT
      - "last month" → date filter
      - "customers" → customers table
      - "products" → products table
    """
    q = user_query.lower()

    logger.info("[Mock SQL] Generating SQL for: '%s'", user_query)

    # ─────────────────────────────────────────
    # PATTERN 1: Show/list all records from a table
    # ─────────────────────────────────────────

    # "show customers" / "list all customers"
    if re.search(r'\b(show|list|all|display|get)\b.*\bcustomer', q) and not any(w in q for w in ["top", "best", "by", "total", "revenue", "sales"]):
        return "SELECT customer_id, name, email, city, state, join_date FROM customers ORDER BY name;"

    # "show products" / "list products"
    if re.search(r'\b(show|list|all|display|get)\b.*\bproduct', q) and not any(w in q for w in ["top", "best", "selling", "by", "revenue"]):
        return "SELECT product_id, product_name, category, price, stock_quantity FROM products ORDER BY category, product_name;"

    # "show orders" / "list orders"
    if re.search(r'\b(show|list|all|display|get)\b.*\border', q) and not any(w in q for w in ["top", "by", "total"]):
        return ("SELECT o.order_id, c.name AS customer_name, o.order_date, o.total_amount, o.status "
                "FROM orders o JOIN customers c ON o.customer_id = c.customer_id "
                "ORDER BY o.order_date DESC;")

    # "show regions"
    if re.search(r'\b(show|list|all|display|get)\b.*\bregion', q):
        return "SELECT region_id, region_name, city, state FROM regions ORDER BY region_name;"

    # ─────────────────────────────────────────
    # PATTERN 2: Top N queries
    # ─────────────────────────────────────────

    # Extract LIMIT number (default 5)
    limit = 5
    limit_match = re.search(r'top\s+(\d+)', q)
    if limit_match:
        limit = int(limit_match.group(1))

    # "top N customers by revenue/sales"
    if re.search(r'top.*customer', q):
        return (f"SELECT c.name AS customer_name, SUM(o.total_amount) AS total_revenue "
                f"FROM orders o JOIN customers c ON o.customer_id = c.customer_id "
                f"GROUP BY c.name ORDER BY total_revenue DESC LIMIT {limit};")

    # "top N / best selling products"
    if re.search(r'(top|best).*(product|selling)', q):
        return (f"SELECT p.product_name, p.category, SUM(s.quantity) AS total_qty_sold, "
                f"SUM(s.total_price) AS total_revenue "
                f"FROM sales s JOIN products p ON s.product_id = p.product_id "
                f"GROUP BY p.product_name, p.category ORDER BY total_revenue DESC LIMIT {limit};")

    # "top regions by sales"
    if re.search(r'top.*region', q):
        return (f"SELECT r.region_name, SUM(s.total_price) AS total_sales "
                f"FROM sales s JOIN regions r ON s.region_id = r.region_id "
                f"GROUP BY r.region_name ORDER BY total_sales DESC LIMIT {limit};")

    # "top cities"
    if re.search(r'top.*cit', q):
        return (f"SELECT r.city, SUM(s.total_price) AS total_sales "
                f"FROM sales s JOIN regions r ON s.region_id = r.region_id "
                f"GROUP BY r.city ORDER BY total_sales DESC LIMIT {limit};")

    # ─────────────────────────────────────────
    # PATTERN 3: Trend / time-series queries
    # ─────────────────────────────────────────

    # "monthly sales trend" / "sales by month" / "sales over time"
    if any(w in q for w in ["trend", "over time", "month by month"]) or ("monthly" in q and "sales" in q) or ("sales" in q and "by month" in q):
        return ("SELECT strftime('%Y-%m', sale_date) AS month, "
                "SUM(total_price) AS total_sales, COUNT(*) AS num_transactions "
                "FROM sales GROUP BY month ORDER BY month;")

    # "daily sales"
    if "daily" in q and "sales" in q:
        return ("SELECT sale_date, SUM(total_price) AS total_sales, COUNT(*) AS num_transactions "
                "FROM sales GROUP BY sale_date ORDER BY sale_date;")

    # ─────────────────────────────────────────
    # PATTERN 4: GROUP BY queries
    # ─────────────────────────────────────────

    # "sales by city"
    if "by city" in q or "by cit" in q:
        sql = ("SELECT r.city, SUM(s.total_price) AS total_sales, COUNT(*) AS num_transactions "
               "FROM sales s JOIN regions r ON s.region_id = r.region_id ")
        sql += _add_time_filter(q, "s.sale_date")
        sql += "GROUP BY r.city ORDER BY total_sales DESC;"
        return sql

    # "sales by region"
    if "by region" in q:
        sql = ("SELECT r.region_name, SUM(s.total_price) AS total_sales, COUNT(*) AS num_transactions "
               "FROM sales s JOIN regions r ON s.region_id = r.region_id ")
        sql += _add_time_filter(q, "s.sale_date")
        sql += "GROUP BY r.region_name ORDER BY total_sales DESC;"
        return sql

    # "sales by product" / "revenue by product"
    if "by product" in q and "category" not in q:
        sql = ("SELECT p.product_name, SUM(s.total_price) AS total_revenue, SUM(s.quantity) AS total_qty "
               "FROM sales s JOIN products p ON s.product_id = p.product_id ")
        sql += _add_time_filter(q, "s.sale_date")
        sql += "GROUP BY p.product_name ORDER BY total_revenue DESC;"
        return sql

    # "sales by category" / "revenue by product category"
    if "by category" in q or "by product category" in q:
        sql = ("SELECT p.category, SUM(s.total_price) AS total_revenue, SUM(s.quantity) AS total_qty "
               "FROM sales s JOIN products p ON s.product_id = p.product_id ")
        sql += _add_time_filter(q, "s.sale_date")
        sql += "GROUP BY p.category ORDER BY total_revenue DESC;"
        return sql

    # "orders by customer" / "sales by customer"
    if "by customer" in q:
        sql = ("SELECT c.name AS customer_name, SUM(o.total_amount) AS total_spent, COUNT(o.order_id) AS num_orders "
               "FROM orders o JOIN customers c ON o.customer_id = c.customer_id ")
        sql += _add_time_filter(q, "o.order_date")
        sql += "GROUP BY c.name ORDER BY total_spent DESC;"
        return sql

    # "by state"
    if "by state" in q:
        sql = ("SELECT r.state, SUM(s.total_price) AS total_sales "
               "FROM sales s JOIN regions r ON s.region_id = r.region_id ")
        sql += _add_time_filter(q, "s.sale_date")
        sql += "GROUP BY r.state ORDER BY total_sales DESC;"
        return sql

    # ─────────────────────────────────────────
    # PATTERN 5: Aggregation with time filter
    # ─────────────────────────────────────────

    # "total sales last month" / "revenue last month"
    if any(w in q for w in ["total", "sum", "overall", "revenue"]) and any(w in q for w in ["sale", "sales", "revenue", "amount"]):
        sql = "SELECT SUM(total_price) AS total_sales, COUNT(*) AS num_transactions FROM sales "
        time_clause = _add_time_filter(q, "sale_date")
        if time_clause.strip().startswith("WHERE"):
            sql += time_clause
        sql = sql.rstrip() + ";"
        return sql

    # "count orders" / "how many orders"
    if any(w in q for w in ["count", "how many", "number of"]):
        if "customer" in q:
            return "SELECT COUNT(*) AS total_customers FROM customers;"
        if "product" in q:
            return "SELECT COUNT(*) AS total_products FROM products;"
        if "order" in q:
            sql = "SELECT COUNT(*) AS total_orders FROM orders "
            sql += _add_time_filter(q, "order_date")
            return sql.rstrip() + ";"
        # Default: count sales
        sql = "SELECT COUNT(*) AS total_sales_records FROM sales "
        sql += _add_time_filter(q, "sale_date")
        return sql.rstrip() + ";"

    # ─────────────────────────────────────────
    # PATTERN 6: Specific entity queries
    # ─────────────────────────────────────────

    # "average order value"
    if "average" in q and "order" in q:
        return "SELECT AVG(total_amount) AS avg_order_value, COUNT(*) AS total_orders FROM orders;"

    # "average price" / "average product price"
    if "average" in q and ("price" in q or "product" in q):
        return "SELECT AVG(price) AS avg_price FROM products;"

    # "stock" / "inventory"
    if any(w in q for w in ["stock", "inventory"]):
        return ("SELECT product_name, category, stock_quantity, price "
                "FROM products ORDER BY stock_quantity ASC;")

    # ─────────────────────────────────────────
    # FALLBACK: Try to guess from keywords
    # ─────────────────────────────────────────

    # If query mentions sales at all
    if any(w in q for w in ["sale", "sales", "revenue"]):
        sql = "SELECT SUM(total_price) AS total_sales, COUNT(*) AS num_transactions FROM sales "
        sql += _add_time_filter(q, "sale_date")
        return sql.rstrip() + ";"

    # If query mentions customers
    if "customer" in q:
        return "SELECT customer_id, name, email, city, state, join_date FROM customers ORDER BY name;"

    # If query mentions products
    if "product" in q:
        return "SELECT product_id, product_name, category, price, stock_quantity FROM products ORDER BY product_name;"

    # If query mentions orders
    if "order" in q:
        return ("SELECT o.order_id, c.name AS customer_name, o.order_date, o.total_amount "
                "FROM orders o JOIN customers c ON o.customer_id = c.customer_id "
                "ORDER BY o.order_date DESC LIMIT 20;")

    # Ultimate fallback — general sales overview
    logger.warning("[Mock SQL] No pattern matched, returning general sales overview")
    return ("SELECT SUM(total_price) AS total_sales, COUNT(*) AS num_transactions, "
            "AVG(total_price) AS avg_sale_value FROM sales;")


def _add_time_filter(query_lower: str, date_column: str) -> str:
    """
    Build a WHERE clause for time-based filtering based on keywords.
    Returns an empty string if no time filter is detected.
    """
    if "last month" in query_lower:
        return f"WHERE {date_column} >= date('now', '-1 month') "
    if "this month" in query_lower:
        return f"WHERE {date_column} >= date('now', 'start of month') "
    if "last year" in query_lower:
        return f"WHERE {date_column} >= date('now', '-1 year') "
    if "this year" in query_lower:
        return f"WHERE {date_column} >= date('now', 'start of year') "
    if "last week" in query_lower:
        return f"WHERE {date_column} >= date('now', '-7 days') "
    if "last 3 months" in query_lower or "last quarter" in query_lower:
        return f"WHERE {date_column} >= date('now', '-3 months') "
    if "last 6 months" in query_lower:
        return f"WHERE {date_column} >= date('now', '-6 months') "
    return ""


# ──────────────────────────────────────────────
# Mock Insight Generator — Result-aware insights
# ──────────────────────────────────────────────

def _mock_insight_generator(user_query: str, prompt: str) -> str:
    """
    Generate a context-aware insight based on the user query and results.
    Extracts result data from the prompt and produces a relevant summary.
    """
    q = user_query.lower()

    # Try to extract row count from prompt
    row_match = re.search(r'QUERY RESULTS \((\d+) rows?\)', prompt)
    row_count = int(row_match.group(1)) if row_match else 0

    if row_count == 0:
        return (
            "No data was found matching your query. This could mean the specified "
            "criteria don't match any records in the current database."
        )

    # Try to extract some actual numbers from the results text
    numbers = re.findall(r'(?:total_sales|total_revenue|total|revenue|amount|count):\s*([\d,.]+)', prompt)

    if "by city" in q or "by region" in q:
        return (
            f"The query returned {row_count} geographic segments. "
            f"The data reveals regional performance differences across your business areas. "
            f"Consider focusing on high-performing regions while investigating growth opportunities in underperforming ones."
        )

    if "by product" in q or "by category" in q:
        return (
            f"Product analysis shows {row_count} items in the results. "
            f"The data highlights which product lines are driving revenue. "
            f"This insight can inform inventory decisions and marketing focus areas."
        )

    if "top" in q and "customer" in q:
        return (
            f"Your top customers have been identified with {row_count} results. "
            f"These high-value customers represent a significant portion of revenue. "
            f"Consider loyalty programs or personalized engagement strategies for retention."
        )

    if "top" in q and ("product" in q or "selling" in q):
        return (
            f"Analysis reveals {row_count} top-performing products. "
            f"These best sellers are the core revenue drivers. "
            f"Ensure adequate stock levels and consider promotional strategies for complementary products."
        )

    if "trend" in q or "monthly" in q:
        return (
            f"The trend analysis covers {row_count} time periods. "
            f"Review the data for seasonal patterns and growth trajectories. "
            f"Month-over-month changes can reveal business cycle dynamics and inform forecasting."
        )

    if "total" in q or "sum" in q or "revenue" in q:
        if numbers:
            return (
                f"The total aggregation returned a value of {numbers[0]}. "
                f"This figure represents the cumulative metric for the specified period. "
                f"Compare with previous periods to assess growth trajectory."
            )
        return (
            f"The aggregation query completed successfully with {row_count} result(s). "
            f"The total reflects your business performance for the requested scope."
        )

    if "customer" in q:
        return (
            f"Customer data returned {row_count} records. "
            f"Your customer base spans multiple cities and states. "
            f"Analyzing customer distribution can help optimize regional marketing efforts."
        )

    if "order" in q:
        return (
            f"Order data shows {row_count} records. "
            f"Review order patterns to identify peak periods and customer buying behavior. "
            f"This data can inform supply chain and inventory management decisions."
        )

    # Generic fallback
    return (
        f"The query returned {row_count} row(s) of data. "
        f"The results provide insights into the requested business metrics. "
        f"Review the detailed data table and chart visualization for specific patterns."
    )

