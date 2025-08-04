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
    ):
        self.provider = provider
        self.event_bus = event_bus
        self.foundry_manager = foundry_manager
        self.prompt_engine = prompt_engine
        self.instruction_factory = instruction_factory
        self.display_callback = display_callback
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
            # 1. Create a context-rich prompt (RAG is now implicitly handled here)
            final_prompt = self.prompt_engine.create_prompt(event.prompt_text)

            # 2. Get a response from the LLM provider
            tool_definitions = self.foundry_manager.get_llm_tool_definitions() if mode == 'build' else None
            response = self.provider.get_response(
                prompt=final_prompt,
                mode=mode,
                tools=tool_definitions
            )

            # 3. If in 'plan' mode, just display the conversational response and stop.
            if mode == 'plan':
                self._display(f"💬 Aura:\n{response}", "avm_response")
                return

            # --- The rest of the logic is for 'build' mode only ---

            # 4. Parse and validate the response into an instruction
            instruction = self.instruction_factory.create_instruction(response)

            if not instruction:
                # Factory already displayed error or conversational fallback.
                return

            # 5. Publish the validated instruction for execution.
            # In build mode, all plans are executed immediately.
            self.event_bus.publish(ActionReadyForExecution(instruction=instruction, task_id=event.task_id))

        except Exception as e:
            logger.error(f"Error processing prompt in LLMOperator: {e}", exc_info=True)
            self._display(f"An unexpected error occurred: {e}", "avm_error")

    def handle_plan_approved(self, event: PlanApproved):
        # This handler is now unused but kept for potential future UI changes.
        logger.warning("handle_plan_approved called, but this flow is deprecated.")
        pass

    def handle_plan_denied(self, event: PlanDenied):
        # This handler is now unused but kept for potential future UI changes.
        logger.warning("handle_plan_denied called, but this flow is deprecated.")
        pass