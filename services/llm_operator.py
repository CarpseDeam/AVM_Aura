# services/llm_operator.py
import logging
from typing import Callable, Optional

from event_bus import EventBus
from events import ActionReadyForExecution, PlanReadyForApproval, UserPromptEntered
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

    def _display(self, message: str, tag: str) -> None:
        if self.display_callback:
            self.display_callback(message, tag)

    def handle(self, event: UserPromptEntered) -> None:
        mode = 'build' if event.auto_approve_plan else 'plan'
        self._display(f"🧠 Thinking ({mode} mode)...", "system_message")

        try:
            # 1. Create a context-rich prompt
            final_prompt = self.prompt_engine.create_prompt(event.prompt_text)

            # 2. Get a response from the LLM provider
            tool_definitions = self.foundry_manager.get_llm_tool_definitions()
            response = self.provider.get_response(
                prompt=final_prompt,
                mode=mode,
                tools=tool_definitions
            )

            # 3. Parse and validate the response into an instruction
            instruction = self.instruction_factory.create_instruction(response)

            if not instruction:
                # If instruction is None, it means the response was conversational
                # or an error, which the factory has already displayed.
                return

            # 4. Publish the appropriate event based on the instruction type
            if isinstance(instruction, list):  # It's a plan
                if event.auto_approve_plan:
                    logger.info("Auto-approving plan and publishing for execution.")
                    self._display("✅ Plan auto-approved. Executing now...", "system_message")
                    self.event_bus.publish(ActionReadyForExecution(instruction=instruction))
                else:
                    logger.info("Plan requires approval. Publishing for GUI.")
                    self.event_bus.publish(PlanReadyForApproval(plan=instruction))
            else:  # It's a single action, which is always "auto-approved"
                logger.info("Single action is ready. Publishing for execution.")
                self.event_bus.publish(ActionReadyForExecution(instruction=instruction))

        except Exception as e:
            logger.error(f"Error processing prompt in LLMOperator: {e}", exc_info=True)
            self._display(f"An unexpected error occurred: {e}", "avm_error")