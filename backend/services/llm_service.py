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

from config import LLM_PROVIDER

logger = logging.getLogger(__name__)

# The specific Ollama model we are using
OLLAMA_MODEL = "qwen2.5-coder:3b"
OLLAMA_API_URL = "http://localhost:11434/api/generate"

def call_llm(prompt: str, expect_json: bool = False) -> str:
    """
    Send a prompt to the local Ollama LLM and return the response text.

    Args:
        prompt: The full prompt string.
        expect_json: If True, attempts to clean response for JSON parsing.

    Returns:
        Response text from the LLM.
    """
    # If the user still has LLM_PROVIDER=mock set, we can either obey it or force Ollama.
    # We will force Ollama for now since we are actively developing it.
    logger.info(f"Sending prompt to Ollama ({OLLAMA_MODEL})...")
    
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
