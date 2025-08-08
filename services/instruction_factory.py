# services/instruction_factory.py
import json
import logging
import re
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

    def _extract_json_from_text(self, text: str) -> Optional[Dict]:
        """
        Finds and parses a JSON object from a string, even if it's
        embedded in markdown code blocks.
        """
        # Regex to find content within ```json ... ```
        match = re.search(r'```json\s*([\s\S]+?)\s*```', text)
        if match:
            json_str = match.group(1).strip()
        else:
            # If no markdown block, assume the whole text is the JSON
            json_str = text.strip()

        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            logger.warning(f"Failed to decode JSON from extracted string: {json_str}")
            return None

    def create_invocations_from_plan_data(self, llm_response: Dict[str, Any]) -> Optional[List[BlueprintInvocation]]:
        """
        Parses an LLM response intended to contain a JSON plan with a list of tool calls.
        This is designed for the Technician's output and is robust enough to handle
        both raw text JSON and native tool calls that wrap the JSON plan.
        """
        data = None
        # 1. Prioritize native tool calls from the API
        native_tool_calls = llm_response.get("tool_calls")
        if native_tool_calls and isinstance(native_tool_calls, list) and len(native_tool_calls) > 0:
            logger.debug("Processing native tool call from Technician...")
            wrapper_call = native_tool_calls[0]
            # The Technician's JSON plan is expected to be inside the arguments of a single wrapper call.
            if 'arguments' in wrapper_call and isinstance(wrapper_call['arguments'], dict):
                 data = wrapper_call['arguments']
            else:
                 logger.warning(f"Native tool call from Technician was malformed, missing 'arguments' dict: {wrapper_call}")

        # 2. Fallback to parsing the text response if no valid native call was found.
        if data is None:
            logger.debug("No valid native tool call found, falling back to parsing text response.")
            text_response = llm_response.get("text")
            if not text_response or not isinstance(text_response, str):
                logger.warning("LLM response for plan data is missing or not a string.")
                return None
            data = self._extract_json_from_text(text_response)

        if not data:
            logger.error("Could not parse valid JSON from any part of the LLM response. Cannot create instruction plan.")
            return None

        # 3. Once we have the JSON data, extract the plan list.
        plan_list = data.get("plan")
        if not plan_list or not isinstance(plan_list, list):
            logger.error(f"Parsed JSON response is missing a 'plan' list: {data}")
            return None

        # 4. Convert the plan list into executable BlueprintInvocations.
        invocations = []
        for tool_call_data in plan_list:
            invocation = self._parse_tool_call_dict(tool_call_data)
            if invocation:
                invocations.append(invocation)
            else:
                logger.error(f"Failed to parse a tool call within the Technician's plan. Aborting. Data: {tool_call_data}")
                return None  # If one part of the plan is invalid, the whole plan is invalid.

        logger.info(f"Successfully created {len(invocations)} invocations from Technician's plan.")
        return invocations

    def _parse_tool_call_dict(self, data: Dict) -> Optional[BlueprintInvocation]:
        """Converts a dictionary into a BlueprintInvocation."""
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