# services/llm_operator.py
import logging
import json
import re
from typing import Callable, Optional, List

from event_bus import EventBus
from events import (
    UserPromptEntered, DirectToolInvocationRequest
)
from providers import LLMProvider
from .prompt_engine import PromptEngine
from .instruction_factory import InstructionFactory
from foundry import FoundryManager
from prompts.planner import PLANNER_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class LLMOperator:
    """
    Orchestrates LLM interactions using a two-step "conversational planning" process.
    1. The Architect creates a human-readable plan.
    2. The Planner converts each step of the plan into a machine-readable tool call.
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

    def _display(self, message: str, tag: str) -> None:
        if self.display_callback:
            self.display_callback(message, tag)

    def _summarize_tool_call(self, tool_call: dict) -> str:
        """Creates a human-readable summary of a tool call."""
        tool_name = tool_call.get('tool_name', 'unknown_tool')
        args = tool_call.get('arguments', {})

        if not isinstance(args, dict):
            args = {}

        summary = tool_name.replace('_', ' ').title()
        path = args.get('path') or args.get('source_path')
        if path:
            summary += f" '{path}'"
        desc = args.get('description')
        if desc:
            summary += f": {desc[:50]}..."
        elif 'command' in args:
            summary += f": `{args['command']}`"

        return summary

    def _extract_plan_from_text(self, text: str) -> (str, List[str]):
        """
        Parses the Architect's text response to separate reasoning from the numbered list.
        """
        reasoning = text
        plan_items = []

        # Find the start of the numbered list.
        list_start_match = re.search(r'^\s*\d+[.)]', text, re.MULTILINE)

        if list_start_match:
            list_start_index = list_start_match.start()
            reasoning = text[:list_start_index].strip()
            plan_text = text[list_start_index:]
            plan_items = re.findall(r'^\s*\d+[.)]\s*(.*)', plan_text, re.MULTILINE)

        return reasoning, plan_items

    def handle(self, event: UserPromptEntered) -> None:
        """
        Handles a user prompt by generating a plan and populating the Mission Log.
        """
        self._display("🧠 Architect is planning...", "system_message")

        try:
            # --- Step 1: Call the Architect to get a human-readable plan ---
            architect_prompt = self.prompt_engine.create_architect_prompt(event.prompt_text)
            architect_response = self.provider.get_response(prompt=architect_prompt, mode='plan', tools=None)
            architect_text = architect_response.get("text")

            if not architect_text:
                self._display("❌ Architect failed to provide a plan. The system cannot proceed.", "avm_error")
                return

            reasoning, plan_steps = self._extract_plan_from_text(architect_text)

            if not plan_steps:
                self._display(
                    "⚠️ Architect provided reasoning but no actionable plan steps. The system cannot proceed.",
                    "avm_warning")
                self._display(f"💬 Architect's Response:\n{reasoning}", "avm_response")
                return

            self._display(f"💬 Architect's Plan:\n{reasoning}", "avm_response")
            self._display(f"✅ Plan received. Converting {len(plan_steps)} steps to tool calls...", "system_message")

            # --- Step 2: Call the Planner for each step to get a machine-readable tool call ---
            all_tools = self.foundry_manager.get_llm_tool_definitions()

            for i, step_text in enumerate(plan_steps):
                self._display(f"    - Step {i + 1}: `{step_text}`...", "system_message")
                planner_prompt = self.prompt_engine.create_planner_prompt(step_text, all_tools)

                planner_response = self.provider.get_response(
                    prompt=planner_prompt,
                    mode='build',
                    tools=all_tools,
                    system_instruction_override=PLANNER_SYSTEM_PROMPT
                )

                instruction = self.instruction_factory.create_single_invocation_from_data(planner_response)

                if instruction:
                    # ** THIS IS THE FIX **
                    # The instruction is valid, so immediately publish the request to add it to the mission log.
                    tool_call_dict = {
                        "tool_name": instruction.blueprint.id,
                        "arguments": instruction.parameters
                    }
                    params = {
                        "description": self._summarize_tool_call(tool_call_dict),
                        "tool_call": tool_call_dict
                    }
                    self.event_bus.publish(DirectToolInvocationRequest(
                        tool_id='add_task_to_mission_log',
                        params=params
                    ))
                else:
                    self._display(f"❌ Planner failed to convert step {i + 1}. Aborting.", "avm_error")
                    # Stop processing if a step fails to be converted.
                    return

            self._display("✅ Plan conversion complete. Mission Log is ready.", "system_message")

        except Exception as e:
            logger.error(f"Error processing prompt in LLMOperator: {e}", exc_info=True)
            self._display(f"An unexpected error occurred: {e}", "avm_error")