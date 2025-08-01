"""
Define the abstract contract (interface) that all LLM providers must adhere to,
ensuring architectural consistency.
"""
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """
    Abstract Base Class for all Large Language Model (LLM) providers.

    This defines the contract that all concrete provider implementations must follow.
    """

    @abstractmethod
    def get_response(self, prompt: str, context: dict) -> str:
        """
        Get a response from the LLM.

        Args:
            prompt: The user's input prompt.
            context: A dictionary containing any relevant context for the request.

        Returns:
            The text response from the LLM.
        """
        pass