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

    def create_single_invocation_from_data(self, llm_response: Dict[str, Any]) -> Optional[BlueprintInvocation]:
        """
        Parses an LLM response intended to contain a single tool call,
        checking for native tool calls first, then falling back to parsing the text content as JSON.
        """
        # 1. Prioritize native tool calls from the API
        native_tool_calls = llm_response.get("tool_calls")
        if native_tool_calls and isinstance(native_tool_calls, list) and len(native_tool_calls) > 0:
            # We only expect one tool call from the Planner
            logger.info("Processing native tool call from Planner LLM response.")
            return self._parse_tool_call_dict(native_tool_calls[0])

        # 2. Fallback: Check if the text response is a JSON object
        text_response = llm_response.get("text")
        if text_response and isinstance(text_response, str):
            data = self._extract_json_from_text(text_response)
            if not data:
                logger.warning("LLM text response was not valid JSON. Cannot create instruction.")
                return None

            logger.info("Successfully parsed text response as JSON.")
            if "tool_name" in data:
                return self._parse_tool_call_dict(data)

        # If neither path yielded an instruction, return None
        return None

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