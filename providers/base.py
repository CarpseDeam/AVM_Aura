"""
Define the abstract contract (interface) that all LLM providers must adhere to,
ensuring architectural consistency.
"""
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """
    Abstract Base Class for all Large Language Model (LLM) providers.

    This defines the contract that all concrete provider implementations must follow.
    """

    @abstractmethod
    def get_response(
        self, prompt: str, tools: Optional[List[Dict[str, Any]]] = None
    ) -> Union[str, Dict[str, Any]]:
        """
        Get a response from the LLM, optionally with tool-calling capabilities.

        Args:
            prompt: The user's input prompt.
            tools: An optional list of tool definitions that the LLM can use.
                   Each tool is a dictionary describing its name, description,
                   and parameters.

        Returns:
            A string containing the text response from the LLM, or a dictionary
            representing a tool call if the LLM decides to use a tool.
        """
        pass