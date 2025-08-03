# services/llm_operator.py
"""
This module defines the LLMOperator, which is responsible for orchestrating the
interaction between user prompts, the context memory, the available tools (from
the Foundry), and the underlying LLM provider.
"""

import json
import logging
from typing import Any, Callable, Dict, Optional, Union

from rich.console import Console
from proto.marshal.collections.maps import MapComposite

from event_bus import EventBus
from events import ActionReadyForExecution, BlueprintInvocation, UserPromptEntered
from foundry import FoundryManager
from providers import LLMProvider
# --- THIS IS THE FIX: Use relative imports for sibling modules ---
from .context_manager import ContextManager
from .vector_context_service import VectorContextService

logger = logging.getLogger(__name__)


class LLMOperator:
    """
    Orchestrates LLM interactions by managing context, tools, and responses.

    This class now implements a RAG (Retrieval-Augmented Generation) flow by
    querying a vector database for relevant code context before calling the LLM.
    """

    def __init__(
            self,
            console: Console,
            provider: LLMProvider,
            event_bus: EventBus,
            foundry_manager: FoundryManager,
            context_manager: ContextManager,
            vector_context_service: VectorContextService,
            display_callback: Optional[Callable[[str, str], None]] = None,
    ):
        """
        Initializes the LLMOperator.
        """
        self.console = console
        self.provider = provider
        self.event_bus = event_bus
        self.foundry_manager = foundry_manager
        self.context_manager = context_manager
        self.vector_context_service = vector_context_service
        self.display_callback = display_callback

    def _display(self, message: str, tag: str) -> None:
        """
        Sends a message to the display callback, if one is configured.
        """
        if self.display_callback:
            self.display_callback(message, tag)

    def _deep_convert_proto_maps(self, data: Any) -> Any:
        """
        Recursively converts Gemini's special MapComposite objects (and other
        mappables) into standard Python dicts and lists.
        """
        if isinstance(data, MapComposite):
            return {k: self._deep_convert_proto_maps(v) for k, v in data.items()}
        if isinstance(data, dict):
            return {k: self._deep_convert_proto_maps(v) for k, v in data.items()}
        if isinstance(data, list):
            return [self._deep_convert_proto_maps(item) for item in data]
        return data

    def _parse_and_validate_llm_response(
            self, llm_response: Union[str, Dict[str, Any]]
    ) -> Optional[BlueprintInvocation]:
        """
        Parses and validates the response from the LLM provider.
        """
        if isinstance(llm_response, str):
            try:
                data: Dict[str, Any] = json.loads(llm_response)
            except json.JSONDecodeError:
                logger.info("LLM returned a non-JSON string. Displaying as text.")
                self._display(f"💬 LLM Response:\n{llm_response}", "avm_response")
                return None
        elif isinstance(llm_response, dict):
            data = llm_response
        else:
            logger.error(
                "Received unexpected response type from provider: %s",
                type(llm_response).__name__,
            )
            self._display("Error: Unexpected response type from provider.", "avm_error")
            return None

        tool_name = data.get("tool_name")
        if not tool_name:
            self._display("Error: LLM output missing 'tool_name'.", "avm_error")
            return None

        arguments = data.get("arguments")
        if arguments is None:
            self._display("Error: LLM output missing 'arguments' block.", "avm_error")
            return None

        blueprint = self.foundry_manager.get_blueprint(tool_name)
        if not blueprint:
            self._display(
                f"Error: LLM requested unknown tool '{tool_name}'.", "avm_error"
            )
            return None

        sanitized_arguments = self._deep_convert_proto_maps(arguments)

        if not isinstance(sanitized_arguments, dict):
            self._display(f"Error: Tool '{tool_name}' arguments could not be converted to a dictionary.", "avm_error")
            return None

        return BlueprintInvocation(blueprint=blueprint, parameters=sanitized_arguments)

    def handle(self, event: UserPromptEntered) -> None:
        """
        Handles a UserPromptEntered event, now with RAG.
        """
        self._display("🧠 Thinking...", "system_message")
        try:
            tool_definitions = self.foundry_manager.get_llm_tool_definitions()

            logger.info("Querying vector database for relevant context...")
            relevant_docs = self.vector_context_service.query(event.prompt_text)

            context_parts = []

            if relevant_docs:
                context_parts.append("--- CONTEXT FROM RELEVANT CODE (RAG) ---")
                for doc in relevant_docs:
                    metadata = doc.get('metadata', {})
                    file_path = metadata.get('file_path', 'N/A')
                    node_name = metadata.get('node_name', 'N/A')
                    context_parts.append(f"# From file '{file_path}', node '{node_name}':")
                    context_parts.append(f"```python\n{doc['document']}\n```")
                context_parts.append("--- END RAG CONTEXT ---")

            current_context = self.context_manager.get_context()
            if current_context:
                context_parts.append("--- CONTEXT FROM OPEN FILES ---")
                for key, content in current_context.items():
                    context_parts.append(f"Content of file '{key}':\n```\n{content}\n```")
                context_parts.append("--- END OPEN FILES CONTEXT ---")

            if context_parts:
                context_str = "\n\n".join(context_parts)
                final_prompt = f"{context_str}\n\nUser Prompt: {event.prompt_text}"
                logger.info("Injecting RAG and/or file context into the prompt.")
            else:
                final_prompt = event.prompt_text
                logger.debug("No context to inject into prompt.")

            response = self.provider.get_response(
                prompt=final_prompt,
                context=None,
                tools=tool_definitions
            )

            instruction = self._parse_and_validate_llm_response(response)
            if instruction:
                action_event = ActionReadyForExecution(instruction=instruction)
                self.event_bus.publish(action_event)
        except Exception as e:
            logger.error(f"Error processing prompt: {e}", exc_info=True)
            self._display("Error getting response from provider.", "avm_error")