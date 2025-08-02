import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

"""
This module defines the ContextManager service.

The ContextManager acts as the AVM's working memory, storing information
(like the contents of recently read files) that can be injected into
subsequent LLM prompts to provide context.
"""


class ContextManager:
    """
    Manages the working memory context for the AVM.

    This class provides a simple key-value store for contextual information
    that needs to be persisted across multiple user prompts and LLM interactions.
    It is primarily used to hold the contents of files that have been read,
    so the LLM is aware of them in future operations.
    """

    def __init__(self) -> None:
        """Initializes the ContextManager with an empty context."""
        self._context_data: Dict[str, str] = {}
        logger.info("ContextManager initialized.")

    def add_to_context(self, key: str, content: str) -> None:
        """
        Adds or updates a piece of information in the context.

        If the key already exists, its content will be overwritten. This is
        the primary method for populating the context, for example, after
        reading a file.

        Args:
            key (str): The unique identifier for the context item (e.g., a filename).
            content (str): The content to be stored (e.g., file contents).
        """
        logger.info(f"Adding/updating context for key: '{key}'")
        self._context_data[key] = content

    def get_context(self) -> Dict[str, str]:
        """
        Retrieves the entire current context.

        This method is called to get all accumulated context, which is then
        passed to the LLM provider to be included in the prompt. It returns
        a copy of the context dictionary to prevent direct modification of the
        internal state.

        Returns:
            Dict[str, str]: A copy of the current context data, where keys are
                            identifiers (like filenames) and values are the content.
        """
        logger.debug("Retrieving a copy of the full context.")
        return self._context_data.copy()

    def get_item(self, key: str) -> Optional[str]:
        """
        Retrieves a single item from the context by its key.

        Args:
            key (str): The key of the item to retrieve.

        Returns:
            Optional[str]: The content associated with the key, or None if the
                           key does not exist.
        """
        logger.debug(f"Attempting to retrieve context item for key: '{key}'")
        return self._context_data.get(key)

    def clear_context(self) -> None:
        """
        Clears all data from the working memory context.

        This can be used to reset the AVM's memory for a new, unrelated task.
        """
        if not self._context_data:
            logger.info("Context is already empty. No action taken.")
            return

        logger.info(
            f"Clearing all {len(self._context_data)} items from context."
        )
        self._context_data.clear()