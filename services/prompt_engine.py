# services/prompt_engine.py
import logging
from typing import Dict, Optional

from .context_manager import ContextManager
from .vector_context_service import VectorContextService

logger = logging.getLogger(__name__)


class PromptEngine:
    """
    Constructs the final, context-rich prompt sent to the LLM.
    It now handles both general context (RAG, open files) and
    mission-specific context (code written in previous tasks).
    """

    def __init__(self, vector_context_service: VectorContextService, context_manager: ContextManager):
        self.vector_context_service = vector_context_service
        self.context_manager = context_manager
        logger.info("PromptEngine initialized.")

    def create_prompt(
        self,
        user_prompt: str,
        mission_goal: Optional[str] = None,
        mission_context: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Builds a comprehensive prompt, layering mission context with general context.

        Args:
            user_prompt: The core text for the current task or question.
            mission_goal: The high-level goal of the entire mission, if applicable.
            mission_context: Code generated in previous steps of the current mission.

        Returns:
            The final, context-rich prompt string.
        """
        logger.info("Creating a new prompt...")
        context_parts = []

        # 1. Add the overall mission goal if this is part of a mission.
        if mission_goal:
            context_parts.append("--- OVERALL MISSION GOAL ---")
            context_parts.append(mission_goal)

        # 2. Add the context from previously completed tasks in this mission.
        if mission_context:
            context_parts.append("\n--- PREVIOUSLY COMPLETED CODE IN THIS MISSION ---")
            for path, content in mission_context.items():
                context_parts.append(f"Content of file '{path}':\n```python\n{content}\n```")

        # 3. Add general context (RAG, open files)
        # This allows the AI to reference the whole project, not just new code.
        relevant_docs = self.vector_context_service.query(user_prompt)
        if relevant_docs:
            context_parts.append("\n--- RELEVANT EXISTING CODE (from project knowledge base) ---")
            for doc in relevant_docs:
                metadata = doc.get('metadata', {})
                context_parts.append(f"# From file '{metadata.get('file_path', 'N/A')}', node '{metadata.get('node_name', 'N/A')}':")
                context_parts.append(f"```python\n{doc['document']}\n```")

        current_files_context = self.context_manager.get_context()
        if current_files_context:
            context_parts.append("\n--- CONTEXT FROM OPEN FILES ---")
            for key, content in current_files_context.items():
                context_parts.append(f"Content of file '{key}':\n```\n{content}\n```")


        # 4. Assemble the final prompt with the current, specific task.
        context_parts.append("\n--- CURRENT TASK ---")
        if mission_goal:
             context_parts.append(
                "Based on the overall goal and all the context provided, your current, specific task is to:"
                f"\n'{user_prompt}'"
             )
        else:
            context_parts.append(f"User Prompt: {user_prompt}")


        final_prompt = "\n".join(context_parts)
        logger.debug("Final prompt created with layered context.")
        return final_prompt