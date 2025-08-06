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

    def __init__(self, foundry_manager: FoundryManager):
        self.foundry_manager = foundry_manager
        logger.info("InstructionFactory initialized.")

    def _deep_convert_proto_maps(self, data: Any) -> Any:
        """Recursively converts protobuf MapComposite objects to standard Python dicts."""
        if isinstance(data, MapComposite):
            return {k: self._deep_convert_proto_maps(v) for k, v in data.items()}
        if isinstance(data, dict):
            return {k: self._deep_convert_proto_maps(v) for k, v in data.items()}
        if isinstance(data, list):
            return [self._deep_convert_proto_maps(item) for item in data]
        return data

    def create_instruction(self, llm_tool_calls: Optional[List[Dict[str, Any]]]) -> Optional[
        Union[BlueprintInvocation, List[BlueprintInvocation]]]:
        """
        Parses a list of raw LLM tool calls and attempts to build a valid instruction or plan.
        Returns the instruction or None, but does NOT display anything.
        """
        if not llm_tool_calls:
            return None

        # If there's only one tool call, return it as a single invocation.
        if len(llm_tool_calls) == 1:
            return self.create_single_invocation_from_data(llm_tool_calls[0])

        # If there are multiple, it's a plan.
        return self._create_plan_from_data(llm_tool_calls)

    def _create_plan_from_data(self, plan_data: List[Dict]) -> Optional[List[BlueprintInvocation]]:
        """Validates a list of tool calls and converts it into a plan."""
        plan_invocations: List[BlueprintInvocation] = []
        logger.info(f"LLM has proposed a {len(plan_data)}-step plan. Validating...")
        for i, step in enumerate(plan_data):
            invocation = self.create_single_invocation_from_data(step)
            if not invocation:
                logger.error(f"Invalid tool call data in plan step {i + 1}: {step}")
                return None
            plan_invocations.append(invocation)
        logger.info("Plan validated successfully.")
        return plan_invocations

    def create_single_invocation_from_data(self, data: Dict) -> Optional[BlueprintInvocation]:
        """Validates a single tool call dictionary and creates a BlueprintInvocation."""
        tool_name = data.get("tool_name")
        if not tool_name:
            logger.warning(f"Tool call data is missing 'tool_name': {data}")
            return None

        blueprint = self.foundry_manager.get_blueprint(tool_name)
        if not blueprint:
            logger.error(f"LLM requested unknown tool '{tool_name}'.")
            return None

        arguments = data.get("arguments", {})
        sanitized_arguments = self._deep_convert_proto_maps(arguments)
        return BlueprintInvocation(blueprint=blueprint, parameters=sanitized_arguments)