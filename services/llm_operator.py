# services/llm_operator.py
"""
This module defines the LLMOperator, which is responsible for orchestrating the
interaction between user prompts, the context memory, the available tools (from
the Foundry), and the underlying LLM provider.
"""

import json
import logging
from typing import Any, Callable, Dict, Optional, Union, List

from rich.console import Console
from proto.marshal.collections.maps import MapComposite

from event_bus import EventBus
from events import ActionReadyForExecution, BlueprintInvocation, PlanReadyForApproval, UserPromptEntered
from foundry import FoundryManager
from providers import LLMProvider
from .context_manager import ContextManager
from .vector_context_service import VectorContextService

logger = logging.getLogger(__name__)


class LLMOperator:
    """
    Orchestrates LLM interactions by managing context, tools, and responses.
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
        self.console = console
        self.provider = provider
        self.event_bus = event_bus
        self.foundry_manager = foundry_manager
        self.context_manager = context_manager
        self.vector_context_service = vector_context_service
        self.display_callback = display_callback

    def _display(self, message: str, tag: str) -> None:
        if self.display_callback:
            self.display_callback(message, tag)

    def _deep_convert_proto_maps(self, data: Any) -> Any:
        if isinstance(data, MapComposite):
            return {k: self._deep_convert_proto_maps(v) for k, v in data.items()}
        if isinstance(data, dict):
            return {k: self._deep_convert_proto_maps(v) for k, v in data.items()}
        if isinstance(data, list):
            return [self._deep_convert_proto_maps(item) for item in data]
        return data

    def _parse_and_validate_llm_response(
            self, llm_response: Union[str, Dict[str, Any]]
    ) -> Optional[Union[BlueprintInvocation, List[BlueprintInvocation]]]:
        if isinstance(llm_response, str):
            try:
                data: Dict[str, Any] = json.loads(llm_response)
            except json.JSONDecodeError:
                self._display(f"💬 LLM Response:\n{llm_response}", "avm_response")
                return None
        elif isinstance(llm_response, dict):
            data = llm_response
        else:
            self._display(f"Error: Unexpected response type from provider: {type(llm_response).__name__}", "avm_error")
            return None

        if "plan" in data and isinstance(data["plan"], list):
            plan_invocations: List[BlueprintInvocation] = []
            self._display(f"📋 LLM has proposed a {len(data['plan'])}-step plan. Validating...", "system_message")
            for i, step in enumerate(data["plan"]):
                tool_name = step.get("tool_name")
                arguments = step.get("arguments", {})
                blueprint = self.foundry_manager.get_blueprint(tool_name)
                if not blueprint:
                    self._display(f"Error in Plan Step {i+1}: Unknown tool '{tool_name}'.", "avm_error")
                    return None
                sanitized_arguments = self._deep_convert_proto_maps(arguments)
                plan_invocations.append(BlueprintInvocation(blueprint=blueprint, parameters=sanitized_arguments))
            self._display("✅ Plan validated successfully.", "system_message")
            return plan_invocations

        tool_name = data.get("tool_name")
        if not tool_name:
            self._display("Error: LLM output missing 'tool_name' or 'plan'.", "avm_error")
            return None
        arguments = data.get("arguments", {})
        blueprint = self.foundry_manager.get_blueprint(tool_name)
        if not blueprint:
            self._display(f"Error: LLM requested unknown tool '{tool_name}'.", "avm_error")
            return None
        sanitized_arguments = self._deep_convert_proto_maps(arguments)
        return BlueprintInvocation(blueprint=blueprint, parameters=sanitized_arguments)

    def handle(self, event: UserPromptEntered) -> None:
        self._display("🧠 Thinking...", "system_message")
        try:
            tool_definitions = self.foundry_manager.get_llm_tool_definitions()
            relevant_docs = self.vector_context_service.query(event.prompt_text)
            context_parts = []
            if relevant_docs:
                context_parts.append("--- CONTEXT FROM RELEVANT CODE (RAG) ---")
                for doc in relevant_docs:
                    metadata = doc.get('metadata', {})
                    context_parts.append(f"# From file '{metadata.get('file_path', 'N/A')}', node '{metadata.get('node_name', 'N/A')}':")
                    context_parts.append(f"```python\n{doc['document']}\n```")
                context_parts.append("--- END RAG CONTEXT ---")
            current_context = self.context_manager.get_context()
            if current_context:
                context_parts.append("--- CONTEXT FROM OPEN FILES ---")
                for key, content in current_context.items():
                    context_parts.append(f"Content of file '{key}':\n```\n{content}\n```")
                context_parts.append("--- END OPEN FILES CONTEXT ---")
            final_prompt = f"{'\n\n'.join(context_parts)}\n\nUser Prompt: {event.prompt_text}" if context_parts else event.prompt_text

            response = self.provider.get_response(prompt=final_prompt, tools=tool_definitions)
            instruction = self._parse_and_validate_llm_response(response)

            if not instruction:
                return

            # --- NEW: Logic to handle auto-approval vs. interactive approval ---
            if isinstance(instruction, list):  # It's a plan
                if event.auto_approve_plan:
                    logger.info("Auto-approving plan and publishing for execution.")
                    self._display("✅ Plan auto-approved. Executing now...", "system_message")
                    self.event_bus.publish(ActionReadyForExecution(instruction=instruction))
                else:
                    logger.info("Plan requires approval. Publishing for GUI.")
                    self.event_bus.publish(PlanReadyForApproval(plan=instruction))
            else:  # It's a single action, which is always "auto-approved"
                logger.info("Single action is ready. Publishing for execution.")
                self.event_bus.publish(ActionReadyForExecution(instruction=instruction))

        except Exception as e:
            logger.error(f"Error processing prompt: {e}", exc_info=True)
            self._display(f"Error getting response from provider: {e}", "avm_error")