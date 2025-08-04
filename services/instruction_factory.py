# services/instruction_factory.py
import json
import logging
from typing import Any, Callable, Dict, Optional, Union, List

from proto.marshal.collections.maps import MapComposite

from events import BlueprintInvocation
from foundry import FoundryManager

logger = logging.getLogger(__name__)


class InstructionFactory:
    """
    Parses and validates raw LLM output, converting it into executable
    BlueprintInvocation instructions.
    """

    def __init__(self, foundry_manager: FoundryManager, display_callback: Optional[Callable[[str, str], None]]):
        self.foundry_manager = foundry_manager
        self.display_callback = display_callback
        logger.info("InstructionFactory initialized.")

    def _display(self, message: str, tag: str) -> None:
        if self.display_callback:
            self.display_callback(message, tag)

    def _deep_convert_proto_maps(self, data: Any) -> Any:
        """Recursively converts protobuf MapComposite objects to standard Python dicts."""
        if isinstance(data, MapComposite):
            return {k: self._deep_convert_proto_maps(v) for k, v in data.items()}
        if isinstance(data, dict):
            return {k: self._deep_convert_proto_maps(v) for k, v in data.items()}
        if isinstance(data, list):
            return [self._deep_convert_proto_maps(item) for item in data]
        return data

    def create_instruction(self, llm_response: Union[str, Dict[str, Any]]) -> Optional[
        Union[BlueprintInvocation, List[BlueprintInvocation]]]:
        """
        Parses the raw LLM response and attempts to build a valid instruction or plan.

        Returns:
            A single BlueprintInvocation, a list of them (for a plan), or None if parsing fails.
        """
        logger.info("Attempting to create instruction from LLM response.")
        if isinstance(llm_response, str):
            try:
                # If the response is a string, it must be valid JSON.
                data: Dict[str, Any] = json.loads(llm_response)
            except json.JSONDecodeError:
                # Not valid JSON, so we treat it as a conversational text response.
                self._display(f"💬 Aura:\n{llm_response}", "avm_response")
                return None
        elif isinstance(llm_response, dict):
            data = llm_response
        else:
            self._display(f"Error: Unexpected response type from provider: {type(llm_response).__name__}", "avm_error")
            return None

        # Check for a multi-step plan first.
        if "plan" in data and isinstance(data["plan"], list):
            return self._create_plan_from_data(data["plan"])

        # Check for a single tool call.
        tool_name = data.get("tool_name")
        if tool_name:
            return self._create_single_invocation_from_data(data)

        # If it's a dict but neither a plan nor a tool call, display it as structured text.
        pretty_json = json.dumps(data, indent=2)
        self._display(f"💬 Aura (JSON Response):\n{pretty_json}", "avm_response")
        return None

    def _create_plan_from_data(self, plan_data: List[Dict]) -> Optional[List[BlueprintInvocation]]:
        """Validates a list of tool calls and converts it into a plan."""
        plan_invocations: List[BlueprintInvocation] = []
        self._display(f"📋 LLM has proposed a {len(plan_data)}-step plan. Validating...", "system_message")
        for i, step in enumerate(plan_data):
            invocation = self._create_single_invocation_from_data(step)
            if not invocation:
                self._display(f"Error in Plan Step {i + 1}: Invalid tool call data.", "avm_error")
                return None  # The entire plan is invalid if one step fails.
            plan_invocations.append(invocation)

        self._display("✅ Plan validated successfully.", "system_message")
        return plan_invocations

    def _create_single_invocation_from_data(self, data: Dict) -> Optional[BlueprintInvocation]:
        """Validates a single tool call dictionary and creates a BlueprintInvocation."""
        tool_name = data.get("tool_name")
        if not tool_name:
            # This is an error, as a step in a plan or a single call MUST have a name.
            logger.warning(f"Tool call data is missing 'tool_name': {data}")
            return None

        blueprint = self.foundry_manager.get_blueprint(tool_name)
        if not blueprint:
            self._display(f"Error: LLM requested unknown tool '{tool_name}'.", "avm_error")
            return None

        arguments = data.get("arguments", {})
        sanitized_arguments = self._deep_convert_proto_maps(arguments)
        return BlueprintInvocation(blueprint=blueprint, parameters=sanitized_arguments)