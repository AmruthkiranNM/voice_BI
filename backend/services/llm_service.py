"""
LLM Service Module (Ollama Local LLM Version)

Provides a unified interface to interact with a local Ollama server.
100% local, private inference.
"""

import logging
import json
import re
import socket
import urllib.error
import urllib.request
from typing import Any

import config

logger = logging.getLogger(__name__)


def call_llm(prompt: str, expect_json: bool = False) -> str:
    """
    Send a prompt to the configured LLM provider and return the response text.

    Provider is selected by config.LLM_PROVIDER ("ollama", the default and
    fully local, or "groq" for the free-tier cloud API). Both return plain
    response text so every calling agent stays provider-agnostic.

    Args:
        prompt: The full prompt string.
        expect_json: If True, attempts to clean response for JSON parsing.

    Returns:
        Response text from the LLM.
    """
    if config.LLM_PROVIDER == "groq":
        text = _call_groq(prompt)
        if expect_json:
            text = _clean_json_response(text)
        return text
    return _call_ollama(prompt, expect_json)


def _call_groq(prompt: str) -> str:
    """Call the Groq free-tier cloud API (OpenAI-compatible chat completions)."""
    if not config.GROQ_API_KEY:
        raise RuntimeError(
            "LLM_PROVIDER is set to 'groq' but GROQ_API_KEY is not configured. "
            "Get a free key at https://console.groq.com/keys and set it in your .env file."
        )

    url = "https://api.groq.com/openai/v1/chat/completions"
    data = {
        "model": config.GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.GROQ_API_KEY}",
            # Groq's Cloudflare WAF blocks the default urllib User-Agent (error 1010).
            "User-Agent": "Mozilla/5.0 (compatible; voice-bi/1.0)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=config.GROQ_TIMEOUT_SECONDS) as response:
            result = json.loads(response.read().decode("utf-8"))
            text = result["choices"][0]["message"]["content"].strip()
            logger.debug("Groq response (first 200 chars): %s", text[:200])
            return text
    except (socket.timeout, TimeoutError) as e:
        logger.error("Groq API call timed out after %ss", config.GROQ_TIMEOUT_SECONDS)
        raise RuntimeError(f"Groq did not respond within {config.GROQ_TIMEOUT_SECONDS}s.") from e
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        logger.error("Groq API call failed: %s %s", e.code, body)
        raise RuntimeError(f"Groq call failed ({e.code}): {body}") from e
    except urllib.error.URLError as e:
        logger.error("Groq API call failed: %s", str(e))
        raise RuntimeError(f"Groq call failed: {e}") from e


def _call_ollama(prompt: str, expect_json: bool = False) -> str:
    """Call a local Ollama instance via HTTP."""
    url = f"{config.OLLAMA_HOST}/api/generate"
    data = {
        "model": config.OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,  # Low temperature for deterministic SQL generation
            "num_ctx": 2048      # Limit context window to save VRAM on GTX 1650 (4GB)
        }
    }
    
    if expect_json:
        # data["format"] = "json"  # Disabled: Causes HTTP 500 Internal Server Error on some Ollama versions/models
        pass
        
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=config.OLLAMA_TIMEOUT_SECONDS) as response:
            result = json.loads(response.read().decode('utf-8'))
            text = result.get('response', '').strip()

            if expect_json:
                text = _clean_json_response(text)

            logger.debug("Ollama response (first 200 chars): %s", text[:200])
            return text
    except (socket.timeout, TimeoutError) as e:
        logger.error("Ollama API call timed out after %ss", config.OLLAMA_TIMEOUT_SECONDS)
        raise RuntimeError(
            f"Ollama did not respond within {config.OLLAMA_TIMEOUT_SECONDS}s. "
            "The model may be overloaded for this hardware — try a smaller model "
            "or enable fast mode."
        ) from e
    except urllib.error.URLError as e:
        logger.error("Ollama API call failed: %s", str(e))
        raise RuntimeError(f"Ollama call failed. Is Ollama running at {config.OLLAMA_HOST}? Error: {e}") from e
    except Exception as e:
        logger.error("Ollama API call failed: %s", str(e))
        raise RuntimeError(f"Ollama call failed. Is Ollama running at {config.OLLAMA_HOST}? Error: {e}") from e


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
