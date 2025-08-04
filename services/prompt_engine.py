# services/prompt_engine.py
import logging
from typing import Dict

from .context_manager import ContextManager
from .vector_context_service import VectorContextService

logger = logging.getLogger(__name__)


class PromptEngine:
    """
    Constructs the final, context-rich prompt to be sent to the LLM.
    """

    def __init__(self, vector_context_service: VectorContextService, context_manager: ContextManager):
        self.vector_context_service = vector_context_service
        self.context_manager = context_manager
        logger.info("PromptEngine initialized.")

    def create_prompt(self, user_prompt: str) -> str:
        """
        Builds a comprehensive prompt by augmenting the user's query with
        retrieved context from the vector database (RAG) and open files.
        """
        logger.info("Creating a new prompt...")
        context_parts = []

        # 1. RAG: Add relevant code snippets from the vector database
        relevant_docs = self.vector_context_service.query(user_prompt)
        if relevant_docs:
            logger.info(f"Found {len(relevant_docs)} relevant document(s) from vector store.")
            context_parts.append("--- CONTEXT FROM RELEVANT CODE (RAG) ---")
            for doc in relevant_docs:
                metadata = doc.get('metadata', {})
                context_parts.append(
                    f"# From file '{metadata.get('file_path', 'N/A')}', "
                    f"node '{metadata.get('node_name', 'N/A')}':"
                )
                context_parts.append(f"```python\n{doc['document']}\n```")
            context_parts.append("--- END RAG CONTEXT ---")

        # 2. Add context from currently open files
        current_context = self.context_manager.get_context()
        if current_context:
            logger.info(f"Adding context from {len(current_context)} open file(s).")
            context_parts.append("--- CONTEXT FROM OPEN FILES ---")
            for key, content in current_context.items():
                context_parts.append(f"Content of file '{key}':\n```\n{content}\n```")
            context_parts.append("--- END OPEN FILES CONTEXT ---")

        # 3. Assemble the final prompt
        if context_parts:
            final_prompt = f"{'\n\n'.join(context_parts)}\n\nUser Prompt: {user_prompt}"
            logger.debug("Final prompt includes augmented context.")
        else:
            final_prompt = user_prompt
            logger.debug("Final prompt is just the user's prompt (no context found).")

        return final_prompt