# foundry/actions/planning_actions.py
"""
Contains special planning-related actions that are typically intercepted by the LLMOperator
and not executed directly.
"""
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

def submit_plan(reasoning: str, plan: List[Dict]):
    """
    This is a special action that is intercepted by the LLMOperator.
    It is used by the Architect to submit a plan, but it does not perform
    any direct execution itself.
    """
    logger.info("submit_plan action was called, but is being intercepted by the LLMOperator.")
    pass