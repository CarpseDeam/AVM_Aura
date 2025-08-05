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

    def create_instruction(self, llm_response: Union[str, Dict[str, Any]]) -> Optional[
        Union[BlueprintInvocation, List[BlueprintInvocation]]]:
        """
        Parses the raw LLM response and attempts to build a valid instruction or plan.
        Returns the instruction or None, but does NOT display anything.
        """
        logger.info("Attempting to create instruction from LLM response.")
        data = None
        if isinstance(llm_response, str):
            try:
                data = json.loads(llm_response)
            except json.JSONDecodeError:
                logger.warning("LLM response was a string but not valid JSON.")
                return None  # Not a valid instruction, but not an error either.
        elif isinstance(llm_response, dict):
            data = llm_response
        else:
            logger.error(f"Unexpected response type from provider: {type(llm_response).__name__}")
            return None

        if not isinstance(data, dict):
             logger.warning(f"Parsed JSON is not a dictionary: {type(data).__name__}")
             return None

        # Check for a multi-step plan first.
        if "plan" in data and isinstance(data.get("plan"), list):
            return self._create_plan_from_data(data["plan"])

        # Check for a single tool call.
        if "tool_name" in data:
            return self._create_single_invocation_from_data(data)

        # The data was a valid dict, but not in a recognized instruction format.
        logger.warning("LLM response was valid JSON but not a recognized tool call or plan.")
        return None

    def _create_plan_from_data(self, plan_data: List[Dict]) -> Optional[List[BlueprintInvocation]]:
        """Validates a list of tool calls and converts it into a plan."""
        plan_invocations: List[BlueprintInvocation] = []
        logger.info(f"LLM has proposed a {len(plan_data)}-step plan. Validating...")
        for i, step in enumerate(plan_data):
            invocation = self._create_single_invocation_from_data(step)
            if not invocation:
                logger.error(f"Invalid tool call data in plan step {i + 1}: {step}")
                return None  # The entire plan is invalid if one step fails.
            plan_invocations.append(invocation)
        logger.info("Plan validated successfully.")
        return plan_invocations

    def _create_single_invocation_from_data(self, data: Dict) -> Optional[BlueprintInvocation]:
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