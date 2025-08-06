# services/llm_operator.py
import logging
from typing import Callable, Optional

from event_bus import EventBus
from events import ActionReadyForExecution, PlanReadyForApproval, UserPromptEntered, PlanApproved, PlanDenied
from providers import LLMProvider
from .prompt_engine import PromptEngine
from .instruction_factory import InstructionFactory
from foundry import FoundryManager

logger = logging.getLogger(__name__)


class LLMOperator:
    """
    Orchestrates LLM interactions by coordinating the prompt engine, LLM provider,
    and instruction factory. Includes retry logic for invalid responses.
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
        self.event_bus.subscribe(PlanApproved, self.handle_plan_approved)
        self.event_bus.subscribe(PlanDenied, self.handle_plan_denied)

    def _display(self, message: str, tag: str) -> None:
        if self.display_callback:
            self.display_callback(message, tag)

    def handle(self, event: UserPromptEntered) -> None:
        mode = 'build' if event.auto_approve_plan else 'plan'
        self._display(f"🧠 Thinking ({mode} mode)...", "system_message")

        try:
            current_prompt = self.prompt_engine.create_prompt(event.prompt_text)
            tool_definitions = None  # Default to no tools for plan mode

            if mode == 'build':
                # Get the full, PROCESSED list of tools from the manager first.
                all_tools = self.foundry_manager.get_llm_tool_definitions()

                # Check if we are in a debugging context.
                if "DEBUGGER REPORT" in current_prompt:
                    logger.info("Debugger context detected. Filtering for only the 'write_file' tool.")
                    # Filter the already-processed list.
                    tool_definitions = [tool for tool in all_tools if tool.get("name") == "write_file"]
                    if not tool_definitions:
                        logger.error("Could not find 'write_file' in the processed tool definitions. Falling back to all tools.")
                        tool_definitions = all_tools
                else:
                    # Otherwise, provide all available tools.
                    tool_definitions = all_tools

            response = None
            instruction = None

            for attempt in range(self.max_retries + 1):
                self._display(f"Calling LLM (Attempt {attempt + 1}/{self.max_retries + 1})...", "avm_info")
                response = self.provider.get_response(
                    prompt=current_prompt,
                    mode=mode,
                    tools=tool_definitions
                )

                if mode == 'build':
                    instruction = self.instruction_factory.create_instruction(response)
                    if instruction:
                        logger.info(f"Successfully created instruction on attempt {attempt + 1}.")
                        break  # Success! Exit the retry loop.
                    else:
                        logger.warning(f"Attempt {attempt + 1} failed. LLM did not return a valid instruction.")
                        current_prompt = (
                            "Your previous response was not a valid JSON tool call or plan. "
                            "You MUST respond with ONLY a single, valid JSON object and nothing else. "
                            f"Please try again to fulfill the original request:\n\n{event.prompt_text}"
                        )
                        if attempt < self.max_retries:
                            self._display(f"LLM response was invalid. Retrying...", "avm_warning")
                else:  # plan mode
                    break  # In plan mode, we don't retry, just accept the text response.

            if mode == 'plan':
                self._display(f"💬 Aura:\n{response}", "avm_response")
                return

            # --- Build Mode Final Handling ---
            if instruction:
                self.event_bus.publish(ActionReadyForExecution(instruction=instruction, task_id=event.task_id))
            else:
                logger.error(f"Failed to get a valid instruction from LLM after {self.max_retries + 1} attempts.")
                self._display(
                    "❌ Aura failed to generate a valid plan after multiple attempts. "
                    f"The last response was:\n{response}", "avm_error"
                )

        except Exception as e:
            logger.error(f"Error processing prompt in LLMOperator: {e}", exc_info=True)
            self._display(f"An unexpected error occurred: {e}", "avm_error")

    def handle_plan_approved(self, event: PlanApproved):
        logger.warning("handle_plan_approved called, but this flow is deprecated.")
        pass

    def handle_plan_denied(self, event: PlanDenied):
        logger.warning("handle_plan_denied called, but this flow is deprecated.")
        pass