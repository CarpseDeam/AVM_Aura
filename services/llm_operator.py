# services/llm_operator.py
import logging
import json
import re
import threading
from typing import Callable, Optional, List

from event_bus import EventBus
from events import (
    UserPromptEntered, DirectToolInvocationRequest, StatusUpdate
)
from providers import LLMProvider
from .prompt_engine import PromptEngine
from .instruction_factory import InstructionFactory
from foundry import FoundryManager
from prompts.translator import TRANSLATOR_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class LLMOperator:
    """
    Orchestrates LLM interactions using a two-step "Architect -> Translator" process
    to generate robust, step-by-step plans for the Mission Log.
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
        logger.info("LLMOperator initialized with new Architect->Translator workflow.")

    def _display(self, message: str, tag: str) -> None:
        if self.display_callback:
            self.display_callback(message, tag)

    def _summarize_tool_call(self, tool_call: dict) -> str:
        """Creates a human-readable summary of a tool call for the Mission Log."""
        tool_name = tool_call.get('tool_name', 'unknown_tool')
        args = tool_call.get('arguments', {})
        if not isinstance(args, dict): args = {}

        # Start with the formatted tool name
        summary = ' '.join(word.capitalize() for word in tool_name.split('_'))

        # Add primary identifier like path or name
        path = args.get('path') or args.get('source_path')
        if path:
            summary += f": '{path}'"
        elif 'project_name' in args:
            summary += f": '{args['project_name']}'"

        # Add a snippet of the content if relevant
        content_keys = ['content', 'function_code', 'class_code', 'command']
        for key in content_keys:
            if key in args:
                summary += f" with `{str(args[key])[:40].strip()}...`"
                break  # Only show the first content-like key

        return summary

    def _extract_plan_from_text(self, text: str) -> (str, List[str]):
        """Parses the Architect's response to separate reasoning from the numbered plan."""
        reasoning = text
        plan_items = []

        # The regex now looks for one or more digits, a dot or parenthesis, and optional whitespace.
        list_start_match = re.search(r'^\s*\d+[.)]\s+', text, re.MULTILINE)

        if list_start_match:
            list_start_index = list_start_match.start()
            reasoning = text[:list_start_index].strip()
            plan_text = text[list_start_index:]
            # This regex is more robust to variations in list formatting.
            plan_items = re.findall(r'^\s*\d+[.)]\s*(.*)', plan_text, re.MULTILINE)

        return reasoning, [item.strip() for item in plan_items if item.strip()]

    def handle(self, event: UserPromptEntered) -> None:
        """Handles the user prompt by running the full planning workflow in a background thread."""
        thread = threading.Thread(target=self._handle_prompt_thread, args=(event,))
        thread.start()

    def _handle_prompt_thread(self, event: UserPromptEntered):
        """
        The core orchestration logic for the Architect -> Translator workflow.
        """
        try:
            # --- Step 1: Call the Architect for the high-level plan ---
            self.event_bus.publish(StatusUpdate("PLANNING", "Architect is formulating a plan...", True))
            architect_prompt = self.prompt_engine.create_architect_prompt(event.prompt_text)
            architect_response = self.provider.get_response(prompt=architect_prompt, mode='plan', tools=None)
            architect_text = architect_response.get("text")

            if not architect_text:
                self._display("❌ Architect failed to provide a plan.", "avm_error")
                self.event_bus.publish(StatusUpdate("FAIL", "Architect failed to respond.", False))
                return

            reasoning, plan_steps = self._extract_plan_from_text(architect_text)

            if not plan_steps:
                self._display("⚠️ Architect provided reasoning but no actionable plan.", "avm_warning")
                self._display(f"💬 Architect's Response:\n{reasoning}", "avm_response")
                self.event_bus.publish(StatusUpdate("IDLE", "Ready for input.", False))
                return

            self._display(f"💬 Architect's Plan:\n{reasoning}", "avm_response")

            # --- Step 2: Loop through the plan, calling the Translator for each step ---
            all_tools = self.foundry_manager.get_llm_tool_definitions()
            total_steps = len(plan_steps)

            for i, step_text in enumerate(plan_steps):
                self.event_bus.publish(StatusUpdate(
                    "PLANNING", f"Translator converting step...", True, progress=i + 1, total=total_steps
                ))
                self._display(f"    - Step {i + 1}/{total_steps}: `{step_text}`", "system_message")

                translator_prompt = self.prompt_engine.create_translator_prompt(step_text, all_tools)
                translator_response = self.provider.get_response(
                    prompt=translator_prompt, mode='build', tools=all_tools,
                    system_instruction_override=TRANSLATOR_SYSTEM_PROMPT
                )
                instruction = self.instruction_factory.create_single_invocation_from_data(translator_response)

                if instruction:
                    # Successfully translated step into a tool call
                    tool_call_dict = {"tool_name": instruction.blueprint.id, "arguments": instruction.parameters}
                    params = {"description": self._summarize_tool_call(tool_call_dict), "tool_call": tool_call_dict}
                    self.event_bus.publish(DirectToolInvocationRequest(
                        tool_id='add_task_to_mission_log', params=params
                    ))
                else:
                    # Failed to translate the step, abort the entire plan.
                    error_message = f"❌ Translator failed to convert step {i + 1}. Aborting plan.\nResponse: {translator_response.get('text', 'No text in response.')}"
                    self._display(error_message, "avm_error")
                    self.event_bus.publish(StatusUpdate("FAIL", f"Translator failed on step {i + 1}.", False))
                    return

            self.event_bus.publish(StatusUpdate("IDLE", "Mission Log is ready for dispatch.", False))

        except Exception as e:
            logger.error(f"An unexpected error occurred in the LLMOperator workflow: {e}", exc_info=True)
            self._display(f"An unexpected error occurred during planning: {e}", "avm_error")
            self.event_bus.publish(StatusUpdate("FAIL", "An unexpected error occurred.", False))