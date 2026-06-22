"""
LLM Service Module (Ollama Local LLM Version)

Provides a unified interface to interact with a local Ollama server.
Replaces the Google Gemini implementation for 100% local, private inference.
"""

import logging
import json
import re
import requests
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
    Send a prompt to the local Ollama LLM and return the response text.

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

    
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1 # Low temperature for more deterministic/SQL-focused output
        }
    }

    try:
        response = requests.post(OLLAMA_API_URL, json=payload, timeout=120)
        response.raise_for_status() # Raise an exception for bad status codes
        
        result_data = response.json()
        text = result_data.get("response", "").strip()

        if expect_json:
            text = _clean_json_response(text)

        logger.debug("Ollama response (first 200 chars): %s", text[:200])
        return text

    except requests.exceptions.ConnectionError:
        error_msg = "Could not connect to Ollama. Is the Ollama app running on your machine?"
        logger.error(error_msg)
        raise RuntimeError(error_msg)
    except Exception as e:
        logger.error("Ollama API call failed: %s", str(e))
        raise RuntimeError(f"LLM call failed: {str(e)}") from e


def _clean_json_response(text: str) -> str:
    """
    Clean LLM response to extract valid JSON.
    Small models sometimes output extra conversational text alongside the JSON.
    """
    # Remove markdown code fences if the model output them
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    text = text.strip()

    # Try to find JSON object or array brackets
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
    """Fallback mock LLM that returns canned responses based on the prompt content."""
    prompt_lower = prompt.lower()
    
    # 1. Planner Agent Mock
    if "query planner agent" in prompt_lower:
        return json.dumps({
            "intent": "analytical",
            "metrics": ["mock_metric"],
            "grouping": ["mock_group"],
            "filters": {},
            "steps": ["Retrieve schema", "Generate SQL", "Extract Insight"]
        })
        
    # 2. SQL Agent Mock
    if "sql generator agent" in prompt_lower:
        if "monthly" in prompt_lower or "trend" in prompt_lower:
            return "SELECT MONTH_ID as month, SUM(SALES) as total_sales FROM sales_data_sample GROUP BY MONTH_ID ORDER BY MONTH_ID;"
        return "SELECT 1 as mock_data, 'mock' as category;"
        
    # 3. Insight Agent Mock
    if "insight" in prompt_lower or "business" in prompt_lower:
        if "monthly" in prompt_lower or "trend" in prompt_lower:
            return "The data shows a clear monthly trend with peaks in the latter half of the year (specifically November), typical of holiday season sales boosts."
        return "Based on the mock data, the system is performing nominally. This is a placeholder insight."

    # Default fallback
    return json.dumps({"status": "mocked", "message": "This is a mock response."})
