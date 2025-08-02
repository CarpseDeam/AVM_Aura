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
        self,
        prompt: str,
        context: Optional[Dict[str, str]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Union[str, Dict[str, Any]]:
        """
        Get a response from the LLM, optionally with tool-calling capabilities
        and a stateful context.

        Args:
            prompt: The user's input prompt.
            context: An optional dictionary containing contextual information,
                     such as the content of previously read files. This allows
                     for stateful conversations.
            tools: An optional list of tool definitions that the LLM can use.
                   Each tool is a dictionary describing its name, description,
                   and parameters.

        Returns:
            A string containing the text response from the LLM, or a dictionary
            representing a tool call if the LLM decides to use a tool.
        """
        pass