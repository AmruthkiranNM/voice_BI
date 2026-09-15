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
    Decide whether a question is about the future (or about a model-predicted
    quantity) rather than about what the data already records.

    This is a semantic test, not a catalogue of phrasings. A question is
    predictive when it uses future or expectation language, or names a
    prediction task outright. The previous version listed twenty specific
    patterns and so missed most natural phrasings — "Will these countries
    remain the top 3?" and "Which market is likely to lead?" both fell through
    to the historical SQL pipeline and were answered from past data.
    """
    from prediction.intent_markers import is_predictive_question

    predictive, reason = is_predictive_question(query)
    logger.info(
        "[Router Agent] Classified as %s (%s)",
        "PREDICTIVE" if predictive else "ANALYTICAL", reason,
    )
    return "PREDICTIVE" if predictive else "ANALYTICAL"
