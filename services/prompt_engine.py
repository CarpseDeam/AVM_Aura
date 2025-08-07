# services/prompt_engine.py
import logging
from typing import Dict, Optional, List, Any
import json

from .context_manager import ContextManager
from .vector_context_service import VectorContextService

logger = logging.getLogger(__name__)


class PromptEngine:
    """
    Constructs the final, context-rich prompt sent to the LLM.
    """

    def __init__(self, vector_context_service: VectorContextService, context_manager: ContextManager):
        self.vector_context_service = vector_context_service
        self.context_manager = context_manager
        logger.info("PromptEngine initialized.")

    def create_prompt(
            self,
            user_prompt: str,
            available_tools: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        Builds a comprehensive prompt, layering mission context with general context.

        Args:
            user_prompt: The core text for the current task or question.
            available_tools: A list of tool definitions to be included in the prompt text.

        Returns:
            The final, context-rich prompt string.
        """
        logger.info("Creating a new prompt...")
        context_parts = []

        # 1. Add definitions of available tools for the Architect to see
        if available_tools:
            # We format this nicely for the LLM to read
            tool_text = "\n".join([f"- `{tool['name']}`: {tool['description']}" for tool in available_tools])
            context_parts.append("--- AVAILABLE TOOLS ---")
            context_parts.append("You can use the following tools to construct your plan:")
            context_parts.append(tool_text)

        # 2. Add general context (RAG, open files)
        relevant_docs = self.vector_context_service.query(user_prompt)
        if relevant_docs:
            context_parts.append("\n--- RELEVANT EXISTING CODE (from project knowledge base) ---")
            for doc in relevant_docs:
                metadata = doc.get('metadata', {})
                context_parts.append(
                    f"# From file '{metadata.get('file_path', 'N/A')}', node '{metadata.get('node_name', 'N/A')}':")
                context_parts.append(f"```python\n{doc['document']}\n```")

        current_files_context = self.context_manager.get_context()
        if current_files_context:
            context_parts.append("\n--- CONTEXT FROM OPEN FILES ---")
            for key, content in current_files_context.items():
                context_parts.append(f"Content of file '{key}':\n```\n{content}\n```")

        # 3. Assemble the final prompt with the user's high-level goal.
        context_parts.append("\n--- USER GOAL ---")
        context_parts.append(f"The user wants to achieve the following goal: '{user_prompt}'")
        context_parts.append(
            "\nBased on this goal and the available tools and context, call the `submit_plan` tool now.")

        final_prompt = "\n".join(context_parts)
        logger.debug("Final prompt created with layered context and tool definitions.")
        return final_prompt