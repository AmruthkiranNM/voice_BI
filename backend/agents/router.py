"""
Router Agent

Responsible for early classification of user queries.
Determines if a query requires the analytical (SQL) pipeline or 
the predictive (ML) pipeline.
"""

import logging
import re
from typing import Literal

logger = logging.getLogger(__name__)

PipelineType = Literal["ANALYTICAL", "PREDICTIVE"]


def run(query: str) -> PipelineType:
    """
    Determine the pipeline required for the given query.
    
    Currently uses heuristic keyword matching for fast, robust routing.
    Can be upgraded to a fast LLM call if the complexity increases.
    """
    query_lower = query.lower()
    
    # ── Heuristic Patterns for Prediction ──
    # These cover a broad range of natural-language prediction intents.
    # Each pattern uses word boundaries (\b) to avoid false positives.
    prediction_patterns = [
        # Direct prediction verbs
        r"\bpredict\b",
        r"\bforecast\b",
        # Churn / attrition / exit domain terms
        r"\bchurn\b",
        r"\battrition\b",
        r"\bretention\b",
        r"\bexited\b",
        # Probabilistic language
        r"\bprobability\b",
        r"\bchance\s+of\b",
        r"\blikelihood\b",
        r"\blikely\s+to\b",
        # "Will customer X ..." style
        r"\bwill\s+(the\s+)?(customer|user|client|they)\b",
        # Risk-oriented language
        r"\b(high|at)\s+risk\b",
        r"\brisk\s+of\s+(leaving|churning|exiting|losing)\b",
        # "Who / which customers might leave" style
        r"\b(likely|going|about)\s+to\s+(leave|churn|exit|cancel|stop|quit|abandon)\b",
        r"\bmight\s+(leave|churn|exit|cancel|stop)\b",
        r"\b(leave|churn|exit|cancel|abandon)\s+soon\b",
        # "Identify / find / list ... at risk" style
        r"\b(identify|find|list|show|flag|rank)\b.*\b(risk|churn|leave|exit|attrition)\b",
    ]
    
    # If the user is specifically asking *if* something will happen or
    # explicitly asking for a prediction/churn status, route to ML.
    for pattern in prediction_patterns:
        if re.search(pattern, query_lower):
            logger.info("[Router Agent] Classified as PREDICTIVE query: '%s' matched pattern '%s'", query, pattern)
            return "PREDICTIVE"
            
    logger.info("[Router Agent] Classified as ANALYTICAL query.")
    return "ANALYTICAL"
