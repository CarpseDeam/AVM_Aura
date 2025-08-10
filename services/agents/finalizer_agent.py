# services/agents/finalizer_agent.py
from __future__ import annotations
import json
import re
import difflib
from typing import TYPE_CHECKING, Dict, List, Optional

from event_bus import EventBus
from prompts import FINALIZER_PROMPT
from prompts.master_rules import JSON_OUTPUT_RULE

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
            JSON_OUTPUT_RULE=JSON_OUTPUT_RULE,
            diffs="\n".join(diffs),
            dependencies=json.dumps(dependencies or [], indent=2),
            available_tools=json.dumps(available_tools, indent=2)
        )

        plan = await self._get_plan_from_llm(finalizer_prompt)
        if plan:
            self.log("success", f"Finalizer created a validated execution plan with {len(plan)} steps.")
        return plan

    def _calculate_diffs(self, generated_files: Dict[str, str], existing_files: Dict[str, str]) -> List[str]:
        """Calculates git-style diffs for each file using difflib."""
        diff_texts = []
        all_filenames = set(generated_files.keys()) | set(existing_files.keys())

        for filename in sorted(list(all_filenames)):
            old_content_lines = existing_files.get(filename, "").splitlines(keepends=True)
            new_content_lines = generated_files.get(filename, "").splitlines(keepends=True)

            if old_content_lines == new_content_lines:
                continue

            diff_generator = difflib.unified_diff(
                old_content_lines,
                new_content_lines,
                fromfile=f"a/{filename}",
                tofile=f"b/{filename}"
            )
            diff = "".join(diff_generator)
            if diff:
                diff_texts.append(diff)

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

            plan = plan_data.get("plan")
            if not isinstance(plan, list):
                raise ValueError("Finalizer response JSON does not contain a valid 'plan' list.")

            # --- Plan Validation Logic ---
            for i, step in enumerate(plan):
                tool_name = step.get("tool_name")
                if not tool_name:
                    raise ValueError(f"Plan step {i} is missing a 'tool_name'.")

                blueprint = self.foundry.get_blueprint(tool_name)
                if not blueprint:
                    raise ValueError(f"Plan step {i} uses a non-existent tool: '{tool_name}'.")

                provided_args = step.get("arguments", {}).keys()
                required_args = set(blueprint.parameters.get("required", []))
                all_possible_args = set(blueprint.parameters.get("properties", {}).keys())

                missing_args = required_args - provided_args
                if missing_args:
                    raise ValueError(
                        f"Plan step {i} ('{tool_name}') is missing required arguments: {list(missing_args)}")

                unknown_args = provided_args - all_possible_args
                if unknown_args:
                    raise ValueError(f"Plan step {i} ('{tool_name}') provided unknown arguments: {list(unknown_args)}")

            return plan

        except (json.JSONDecodeError, ValueError) as e:
            self.log("error", f"Finalizer plan creation or validation failed: {e}\nResponse: {raw_response}")
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