# services/llm_operator.py
import logging
from typing import Callable, Optional, List

from event_bus import EventBus
from events import (
    ActionReadyForExecution, PlanReadyForApproval, UserPromptEntered, PlanApproved, PlanDenied, BlueprintInvocation
)
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
        is_agent_task = event.task_id is not None
        mode = 'build' if event.auto_approve_plan else 'plan'
        self._display(f"🧠 Thinking ({mode} mode)...", "system_message")

        try:
            # For agent tasks, the prompt is pre-built by the TaskAgent.
            # For user prompts, the engine adds general context.
            if is_agent_task:
                current_prompt = event.prompt_text
            else:
                current_prompt = self.prompt_engine.create_prompt(user_prompt=event.prompt_text)

            tool_definitions = None
            if mode == 'build':
                all_tools = self.foundry_manager.get_llm_tool_definitions()
                if "ERROR REPORT" in current_prompt or "DEBUGGER REPORT" in current_prompt:
                    logger.info("Debugger context detected. Filtering for only the 'write_file' tool.")
                    tool_definitions = [tool for tool in all_tools if tool.get("name") == "write_file"]
                else:
                    tool_definitions = [t for t in all_tools if 'mission_log' not in t.get("name")]

            response, instruction = None, None
            for attempt in range(self.max_retries + 1):
                if attempt > 0:
                    self._display(f"LLM response was invalid. Retrying ({attempt}/{self.max_retries})...", "avm_warning")
                response = self.provider.get_response(prompt=current_prompt, mode=mode, tools=tool_definitions)

                if mode == 'build':
                    instruction = self.instruction_factory.create_instruction(response)
                    if instruction:
                        logger.info(f"Successfully created instruction on attempt {attempt + 1}.")
                        break
                    else:
                        current_prompt = (
                            "Your previous response was not a valid JSON tool call or plan. You MUST respond with "
                            f"ONLY a single, valid JSON object. Original request: {event.prompt_text}"
                        )
                else:
                    break

            if mode == 'plan':
                self._display(f"💬 Aura:\n{response}", "avm_response")
                return

            if instruction:
                if not event.auto_approve_plan and isinstance(instruction, list):
                    self.event_bus.publish(PlanReadyForApproval(plan=instruction))
                else:
                    self.event_bus.publish(ActionReadyForExecution(instruction=instruction, task_id=event.task_id))
            else:
                final_error = ("Aura failed to generate a valid plan after multiple attempts. "
                               f"The last response was:\n{response}")
                logger.error(final_error)
                self._display(f"❌ {final_error}", "avm_error")

        except Exception as e:
            logger.error(f"Error processing prompt in LLMOperator: {e}", exc_info=True)
            self._display(f"An unexpected error occurred: {e}", "avm_error")

    def handle_plan_approved(self, event: PlanApproved):
        logger.info(f"Plan approved by user with {len(event.plan)} steps, publishing for execution.")
        self.event_bus.publish(ActionReadyForExecution(instruction=event.plan))

    def handle_plan_denied(self, event: PlanDenied):
        logger.info("Plan denied by user.")
        self._display("Plan denied. Awaiting new instructions.", "system_message")