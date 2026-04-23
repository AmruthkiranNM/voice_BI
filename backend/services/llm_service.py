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

from config import LLM_PROVIDER, GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger(__name__)

# Lazy-loaded Gemini model
_gemini_model = None


def _get_gemini_model():
    """Initialize and cache the Gemini model."""
    global _gemini_model
    if _gemini_model is None:
        import google.generativeai as genai

        if not GEMINI_API_KEY:
            raise ValueError(
                "GEMINI_API_KEY environment variable is not set. "
                "Set it or use LLM_PROVIDER=mock for development."
            )
        genai.configure(api_key=GEMINI_API_KEY)
        _gemini_model = genai.GenerativeModel(GEMINI_MODEL)
        logger.info("Gemini model initialized: %s", GEMINI_MODEL)
    return _gemini_model


def call_llm(prompt: str, expect_json: bool = False) -> str:
    """
    Send a prompt to the configured LLM and return the response text.

    Args:
        prompt: The full prompt string.
        expect_json: If True, attempts to clean response for JSON parsing.

    Returns:
        Response text from the LLM.
    """
    if LLM_PROVIDER == "mock":
        return _mock_llm(prompt)

    return _call_gemini(prompt, expect_json)


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
            if "429" in error_str or "quota" in error_str.lower():
                if attempt < max_retries - 1:
                    logger.warning(
                        "[LLM Service] Rate limit hit. Retrying in %d seconds... (Attempt %d/%d)",
                        retry_delay, attempt + 1, max_retries
                    )
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue
            
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
    Mock LLM for development/testing without an API key.
    Returns reasonable responses based on prompt content.
    """
    prompt_lower = prompt.lower()

    # Mock planner response
    if "query planner agent" in prompt_lower:
        return json.dumps({
            "steps": [
                "Identify the relevant tables and columns",
                "Construct SQL query to fetch the requested data",
                "Run query and return results",
            ],
            "requires_aggregation": True,
            "requires_comparison": False,
        })

    # Mock SQL generation
    if "sql generator agent" in prompt_lower:
        return "SELECT SUM(total_price) as total_sales FROM sales WHERE sale_date >= date('now', '-1 month');"

    # Mock insight generation
    if "insight agent" in prompt_lower:
        return "Based on the query results, the data shows significant patterns in the requested metrics. The values indicate a positive trend compared to previous periods."

    return "Mock LLM response for: " + prompt[:100]
