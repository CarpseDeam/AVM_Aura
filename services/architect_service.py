# services/architect_service.py
import logging
import re
from typing import List, Tuple, Optional, Callable

from providers import LLMProvider
from .prompt_engine import PromptEngine
from event_bus import EventBus
from events import StatusUpdate
from prompts import ARCHITECT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class ArchitectService:
    """
    Manages the interaction with the Architect AI. Its sole responsibility
    is to take a user prompt and return a high-level, human-readable plan.
    """

    def __init__(
        self,
        provider: LLMProvider,
        prompt_engine: PromptEngine,
        event_bus: EventBus,
        display_callback: Optional[Callable[[str, str], None]] = None,
    ):
        self.provider = provider
        self.prompt_engine = prompt_engine
        self.event_bus = event_bus
        self.display_callback = display_callback
        logger.info("ArchitectService initialized.")

    def _display(self, message: str, tag: str) -> None:
        if self.display_callback:
            self.display_callback(message, tag)

    def get_plan(self, user_prompt: str) -> Optional[str]:
        """
        Takes a user prompt and returns the Architect's full, raw text response.
        The response contains reasoning and a plan.

        Args:
            user_prompt: The high-level goal from the user.

        Returns:
            The raw text response from the LLM, or None if it fails.
        """
        self.event_bus.publish(StatusUpdate("PLANNING", "Architect is formulating a plan...", True))

        architect_prompt = self.prompt_engine.create_architect_prompt(user_prompt)
        architect_response = self.provider.get_response(
            prompt=architect_prompt,
            mode='plan',
            tools=None,
            system_instruction_override=ARCHITECT_SYSTEM_PROMPT
        )
        architect_text = architect_response.get("text")

        if not architect_text:
            self._display("❌ Architect failed to provide a plan.", "avm_error")
            self.event_bus.publish(StatusUpdate("FAIL", "Architect failed to respond.", False))
            return None

        # Display the full, unmodified response for the user to see.
        # The PlanRefinerService will be responsible for parsing it.
        self._display(f"💬 Architect's Plan:\n{architect_text}", "avm_response")

        return architect_text