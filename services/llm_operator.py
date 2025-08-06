# services/llm_operator.py
import logging
from typing import Callable, Optional, List

from event_bus import EventBus
from events import (
    ActionReadyForExecution, PlanReadyForApproval, UserPromptEntered, PlanApproved, PlanDenied, BlueprintInvocation,
    DirectToolInvocationRequest
)
from providers import LLMProvider
from .prompt_engine import PromptEngine
from .instruction_factory import InstructionFactory
from foundry import FoundryManager

logger = logging.getLogger(__name__)


class LLMOperator:
    """
    Orchestrates LLM interactions by coordinating the prompt engine, LLM provider,
    and instruction factory.
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
            current_prompt = event.prompt_text if is_agent_task else self.prompt_engine.create_prompt(
                user_prompt=event.prompt_text)

            tool_definitions = None
            if mode == 'build':
                all_tools = self.foundry_manager.get_llm_tool_definitions()
                if "ERROR REPORT" in current_prompt or "DEBUGGER REPORT" in current_prompt or "LINTING ERRORS" in current_prompt:
                    tool_definitions = [t for t in all_tools if t.get("name") == "write_file"]
                else:
                    tool_definitions = [t for t in all_tools if 'mission_log' not in t.get("name")]
            elif mode == 'plan':
                architect_tools = ['add_task_to_mission_log', 'create_new_tool']
                tool_definitions = [t for t in self.foundry_manager.get_llm_tool_definitions() if
                                    t.get("name") in architect_tools]

            response, instruction = None, None
            for attempt in range(self.max_retries + 1):
                if attempt > 0:
                    self._display(f"LLM response was invalid. Retrying ({attempt}/{self.max_retries})...",
                                  "avm_warning")

                response = self.provider.get_response(prompt=current_prompt, mode=mode, tools=tool_definitions)

                if mode == 'build':
                    instruction = self.instruction_factory.create_instruction(response.get("tool_calls"))
                    if instruction:
                        break
                    current_prompt = f"Your previous response was not a valid JSON tool call. Please try again. Original request: {event.prompt_text}"
                else:
                    break

            if response.get("text"):
                self._display(f"💬 Aura:\n{response['text']}", "avm_response")

            if response.get("tool_calls"):
                if mode == 'plan':
                    for tool_call in response["tool_calls"]:
                        invocation = self.instruction_factory.create_single_invocation_from_data(tool_call)
                        if invocation:
                            self.event_bus.publish(DirectToolInvocationRequest(tool_id=invocation.blueprint.id,
                                                                               params=invocation.parameters))
                elif mode == 'build' and instruction:
                    if not event.auto_approve_plan and isinstance(instruction, list):
                        self.event_bus.publish(PlanReadyForApproval(plan=instruction))
                    else:
                        self.event_bus.publish(ActionReadyForExecution(instruction=instruction, task_id=event.task_id))

            if mode == 'build' and not instruction:
                self._display(f"❌ Aura failed to generate a valid plan. Last response: {response.get('text')}",
                              "avm_error")

        except Exception as e:
            logger.error(f"Error processing prompt in LLMOperator: {e}", exc_info=True)
            self._display(f"An unexpected error occurred: {e}", "avm_error")

    def handle_plan_approved(self, event: PlanApproved):
        logger.info(f"Plan approved by user with {len(event.plan)} steps, publishing for execution.")
        self.event_bus.publish(ActionReadyForExecution(instruction=event.plan))

    def handle_plan_denied(self, event: PlanDenied):
        logger.info("Plan denied by user.")
        self._display("Plan denied. Awaiting new instructions.", "system_message")