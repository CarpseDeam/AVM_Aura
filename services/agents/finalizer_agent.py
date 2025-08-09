from __future__ import annotations
import json
import re
from typing import TYPE_CHECKING, Dict, List, Optional
import unidiff

from event_bus import EventBus
from prompts import FINALIZER_PROMPT

if TYPE_CHECKING:
    from core.managers.service_manager import ServiceManager


class FinalizerAgent:
    """
    Analyzes the difference between generated code and existing code
    to produce a precise, surgical plan of tool calls for the Mission Log.
    """

    def __init__(self, service_manager: "ServiceManager"):
        self.service_manager = service_manager
        self.event_bus = service_manager.event_bus
        self.llm_client = service_manager.get_llm_client()
        self.foundry = service_manager.get_foundry_manager()

    async def create_tool_plan(self, generated_files: Dict[str, str],
                               existing_files: Optional[Dict[str, str]],
                               dependencies: Optional[List[str]]) -> Optional[List[Dict]]:
        """
        The main method to generate the final tool-based execution plan.
        """
        self.log("info", "Finalizer phase started. Comparing generated code to existing project.")
        diffs = self._calculate_diffs(generated_files, existing_files or {})

        if not diffs and not dependencies:
            self.log("warning", "No code changes or dependencies identified. Final plan is empty.")
            return []

        available_tools = self.foundry.get_llm_tool_definitions()

        finalizer_prompt = FINALIZER_PROMPT.format(
            diffs="\n".join(diffs),
            dependencies=json.dumps(dependencies or [], indent=2),
            available_tools=json.dumps(available_tools, indent=2)
        )

        plan = await self._get_plan_from_llm(finalizer_prompt)
        if plan:
            self.log("success", f"Finalizer created an execution plan with {len(plan)} steps.")
        return plan

    def _calculate_diffs(self, generated_files: Dict[str, str], existing_files: Dict[str, str]) -> List[str]:
        """Calculates git-style diffs for each file."""
        diff_texts = []
        all_filenames = set(generated_files.keys()) | set(existing_files.keys())

        for filename in sorted(list(all_filenames)):
            old_content = existing_files.get(filename, "")
            new_content = generated_files.get(filename, "")

            if old_content == new_content:
                continue

            diff = unidiff.patch.make_patch(old_content.splitlines(True), new_content.splitlines(True),
                                            fromfile=f"a/{filename}", tofile=f"b/{filename}")
            diff_texts.append(str(diff))
        return diff_texts

    async def _get_plan_from_llm(self, prompt: str) -> Optional[List[Dict]]:
        provider, model = self.llm_client.get_model_for_role("finalizer")
        if not provider or not model:
            self.log("error", "No model configured for finalizer role.")
            return None

        raw_response = ""
        try:
            async for chunk in self.llm_client.stream_chat(provider, model, prompt, "finalizer"):
                raw_response += chunk

            plan_data = self._parse_json_response(raw_response)
            if not isinstance(plan_data, dict) or "plan" not in plan_data:
                raise ValueError("Finalizer response is not a valid JSON object with a 'plan' key.")

            # TODO: Add validation against Foundry blueprints here
            return plan_data["plan"]

        except (json.JSONDecodeError, ValueError) as e:
            self.log("error", f"Finalizer plan creation failed: {e}\nResponse: {raw_response}")
            return None
        except Exception as e:
            self.log("error", f"An unexpected error during finalizer planning: {e}")
            return None

    def _parse_json_response(self, response: str) -> dict:
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if not match:
            raise ValueError("No JSON object found in the response.")
        return json.loads(match.group(0))

    def log(self, level: str, message: str):
        self.event_bus.emit("log_message_received", "FinalizerAgent", level, message)