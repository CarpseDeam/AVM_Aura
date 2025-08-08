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

    def _extract_plan_from_text(self, text: str) -> Tuple[str, List[str]]:
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

    def get_plan(self, user_prompt: str) -> Tuple[Optional[str], Optional[List[str]]]:
        """
        Takes a user prompt and returns the Architect's reasoning and plan.

        Args:
            user_prompt: The high-level goal from the user.

        Returns:
            A tuple containing the reasoning string and the list of plan steps,
            or (None, None) if the plan generation fails.
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
            return None, None

        reasoning, plan_steps = self._extract_plan_from_text(architect_text)

        if reasoning:
            self._display(f"💬 Architect's Plan:\n{reasoning}", "avm_response")

        if not plan_steps:
            self._display("⚠️ Architect provided reasoning but no actionable plan.", "avm_warning")
            self.event_bus.publish(StatusUpdate("IDLE", "Ready for input.", False))
            return reasoning, None

        return reasoning, plan_steps