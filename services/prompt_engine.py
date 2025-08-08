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

    def create_architect_prompt(self, user_prompt: str) -> str:
        """

        Builds a comprehensive prompt for the Architect, layering relevant context.
        """
        logger.info("Creating a new Architect prompt...")
        context_parts = []

        # 1. Add general context (RAG, open files)
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

        # 2. Assemble the final prompt with the user's high-level goal.
        context_parts.append("\n--- USER GOAL ---")
        context_parts.append(f"The user wants to achieve the following goal: '{user_prompt}'")
        context_parts.append(
            "\nBased on this goal and the available context, your task is to generate a brief reasoning statement "
            "followed by a comprehensive, step-by-step plan in a numbered list."
        )

        final_prompt = "\n".join(context_parts)
        logger.debug("Final Architect prompt created with layered context.")
        return final_prompt

    def create_technician_prompt(self, task: str, available_tools: List[Dict[str, Any]]) -> str:
        """
        Builds a precise prompt for the Technician agent to convert a task into a tool call plan.
        """
        logger.info(f"Creating a new Technician prompt for task: '{task}'")

        tools_json = json.dumps(available_tools, indent=2)

        final_prompt = f"""--- AVAILABLE TOOLS ---
{tools_json}

--- TASK ---
{task}

--- YOUR RESPONSE ---
"""
        return final_prompt