# providers/base.py
"""
Define the abstract contract (interface) that all LLM providers must adhere to,
ensuring architectural consistency.
"""
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """
    Abstract Base Class for all Large Language Model (LLM) providers.

    This defines the contract that all concrete provider implementations must follow.
    """

    @abstractmethod
    def get_response(
        self,
        prompt: str,
        mode: str,
        context: Optional[Dict[str, str]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Get a response from the LLM, optionally with tool-calling capabilities.

        Args:
            prompt: The user's input prompt.
            mode: The interaction mode ('plan' or 'build').
            context: Optional dictionary with contextual info (e.g., file contents).
            tools: Optional list of tool definitions for the LLM.

        Returns:
            A dictionary with a standardized structure:
            {
                "text": Optional[str],       # The conversational part of the response
                "tool_calls": Optional[list] # A list of tool call dictionaries
            }
        """
        pass