# services/instruction_factory.py
import json
import logging
from typing import Any, Dict, Optional, Union, List

from proto.marshal.collections.maps import MapComposite

from events import BlueprintInvocation
from foundry import FoundryManager

logger = logging.getLogger(__name__)


class InstructionFactory:
    """
    Parses and validates raw LLM output, converting it into executable
    BlueprintInvocation instructions. Acts as the final gatekeeper for LLM responses.
    """

    def __init__(self, foundry_manager: FoundryManager):
        self.foundry_manager = foundry_manager
        logger.info("InstructionFactory initialized.")

    def _deep_convert_proto_maps(self, data: Any) -> Any:
        if isinstance(data, MapComposite):
            return {k: self._deep_convert_proto_maps(v) for k, v in data.items()}
        if isinstance(data, dict):
            return {k: self._deep_convert_proto_maps(v) for k, v in data.items()}
        if isinstance(data, list):
            return [self._deep_convert_proto_maps(item) for item in data]
        return data

    def create_instruction(self, llm_response: Dict[str, Any]) -> Optional[
        Union[BlueprintInvocation, List[BlueprintInvocation]]]:
        """
        Parses the entire raw LLM response object, checking for native tool calls
        first, then falling back to parsing the text content as JSON.
        """
        # 1. Prioritize native tool calls from the API
        native_tool_calls = llm_response.get("tool_calls")
        if native_tool_calls and isinstance(native_tool_calls, list):
            logger.info("Processing native tool calls from LLM response.")
            if len(native_tool_calls) == 1:
                return self.create_single_invocation_from_data(native_tool_calls[0])
            else:
                return self._create_plan_from_data(native_tool_calls)

        # 2. Fallback: Check if the text response is a JSON object
        text_response = llm_response.get("text")
        if text_response and isinstance(text_response, str):
            try:
                data = json.loads(text_response)
                logger.info("Successfully parsed text response as JSON.")

                # Check if the parsed JSON is a plan or a single tool call
                if "plan" in data and isinstance(data.get("plan"), list):
                    return self._create_plan_from_data(data["plan"])
                elif "tool_name" in data:
                    return self.create_single_invocation_from_data(data)

            except json.JSONDecodeError:
                logger.warning("LLM text response was not valid JSON. Cannot create instruction.")
                return None

        # If neither path yielded an instruction, return None
        return None

    def _create_plan_from_data(self, plan_data: List[Dict]) -> Optional[List[BlueprintInvocation]]:
        plan_invocations: List[BlueprintInvocation] = []
        logger.info(f"Validating {len(plan_data)}-step plan...")
        for i, step in enumerate(plan_data):
            invocation = self.create_single_invocation_from_data(step)
            if not invocation:
                logger.error(f"Invalid tool call in plan step {i + 1}: {step}")
                return None
            plan_invocations.append(invocation)
        logger.info("Plan validated successfully.")
        return plan_invocations

    def create_single_invocation_from_data(self, data: Dict) -> Optional[BlueprintInvocation]:
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