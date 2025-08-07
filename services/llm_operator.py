# services/llm_operator.py
import logging
import json
from typing import Callable, Optional, List

from event_bus import EventBus
from events import (
    ActionReadyForExecution, PlanReadyForApproval, UserPromptEntered, PlanApproved, PlanDenied,
    DirectToolInvocationRequest
)
from providers import LLMProvider
from .prompt_engine import PromptEngine
from .instruction_factory import InstructionFactory
from foundry import FoundryManager

logger = logging.getLogger(__name__)


class LLMOperator:
    """
    Orchestrates LLM interactions. It uses the Architect to generate a plan via the
    `submit_plan` tool, which it intercepts to populate the Mission Log.
    """

    def __init__(
            self,
            provider: LLMProvider,
            event_bus: EventBus,
            foundry_manager: FoundryManager,
            prompt_engine: PromptEngine,
            instruction_factory: InstructionFactory,
            display_callback: Optional[Callable[[str, str], None]] = None,
            max_retries: int = 2
    ):
        self.provider = provider
        self.event_bus = event_bus
        self.foundry_manager = foundry_manager
        self.prompt_engine = prompt_engine
        self.instruction_factory = instruction_factory
        self.display_callback = display_callback
        self.max_retries = max_retries
        logger.info("LLMOperator initialized.")
        # These are no longer needed as plan approval happens via Mission Log
        # self.event_bus.subscribe(PlanApproved, self.handle_plan_approved)
        # self.event_bus.subscribe(PlanDenied, self.handle_plan_denied)

    def _display(self, message: str, tag: str) -> None:
        if self.display_callback:
            self.display_callback(message, tag)

    def _summarize_tool_call(self, tool_call: dict) -> str:
        """Creates a human-readable summary of a tool call."""
        tool_name = tool_call.get('tool_name', 'unknown_tool')
        args = tool_call.get('arguments', {})

        summary = tool_name.replace('_', ' ').title()

        path = args.get('path') or args.get('source_path')
        if path:
            summary += f" '{path}'"

        desc = args.get('description')
        if desc:
            summary += f": {desc[:50]}..."

        return summary

    def handle(self, event: UserPromptEntered) -> None:
        """
        Handles a user prompt by generating a plan and populating the Mission Log.
        The 'build' mode (auto_approve_plan=True) is no longer used for planning.
        """
        self._display("🧠 Architect is planning...", "system_message")

        try:
            # We must pass all other tool definitions to the prompt so the Architect
            # knows what tools it can include in its plan.
            all_tools = self.foundry_manager.get_llm_tool_definitions()
            prompt_tools = [t for t in all_tools if t.get("name") != 'submit_plan']

            prompt_with_tools = self.prompt_engine.create_prompt(
                user_prompt=event.prompt_text,
                available_tools=prompt_tools  # Pass tool info into the prompt text
            )

            # However, we only give the API ONE tool to actually call: `submit_plan`.
            api_tools = [t for t in all_tools if t.get("name") == 'submit_plan']
            if not api_tools:
                self._display("❌ CRITICAL ERROR: The 'submit_plan' tool is not defined.", "avm_error")
                return

            response = None
            for attempt in range(self.max_retries + 1):
                if attempt > 0:
                    self._display(f"Architect response was invalid. Retrying ({attempt}/{self.max_retries})...",
                                  "avm_warning")

                response = self.provider.get_response(prompt=prompt_with_tools, mode='plan', tools=api_tools)

                # Check if the response contains the specific tool call we're looking for
                if response and response.get("tool_calls"):
                    if any(tc.get("tool_name") == "submit_plan" for tc in response["tool_calls"]):
                        break  # Success! We got the call we wanted.

                prompt_with_tools = f"Your previous response was not a valid call to the `submit_plan` tool. Please try again, adhering strictly to the required format. Original request: {event.prompt_text}"

            # Intercept and process the `submit_plan` call
            submit_plan_call = next(
                (tc for tc in response.get("tool_calls", []) if tc.get("tool_name") == "submit_plan"), None)

            if submit_plan_call:
                args = submit_plan_call.get("arguments", {})
                reasoning = args.get("reasoning", "No reasoning provided.")
                plan = args.get("plan", [])

                self._display(f"💬 Architect's Plan:\n{reasoning}", "avm_response")

                if plan and isinstance(plan, list):
                    self._display(f"✅ Plan received. Populating Mission Log with {len(plan)} tasks...",
                                  "system_message")
                    for tool_call_dict in plan:
                        params = {
                            "description": self._summarize_tool_call(tool_call_dict),
                            "tool_call": tool_call_dict
                        }
                        self.event_bus.publish(DirectToolInvocationRequest(
                            tool_id='add_task_to_mission_log',
                            params=params
                        ))
                else:
                    self._display("⚠️ Architect submitted a plan with an empty or invalid `plan` list.", "avm_warning")
            else:
                self._display(
                    f"❌ Architect failed to call 'submit_plan' after retries. The system cannot proceed.",
                    "avm_error"
                )

        except Exception as e:
            logger.error(f"Error processing prompt in LLMOperator: {e}", exc_info=True)
            self._display(f"An unexpected error occurred: {e}", "avm_error")