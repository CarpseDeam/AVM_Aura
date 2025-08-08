# services/technician_service.py
import logging
from typing import List, Optional

from events import BlueprintInvocation
from foundry import FoundryManager
from providers import LLMProvider
from .prompt_engine import PromptEngine
from .instruction_factory import InstructionFactory
from prompts.technician import TECHNICIAN_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class TechnicianService:
    """
    Manages the interaction with the Technician AI. Its sole responsibility
    is to take a single development task and convert it into a sequence of
    one or more tool calls.
    """

    def __init__(
        self,
        provider: LLMProvider,
        prompt_engine: PromptEngine,
        instruction_factory: InstructionFactory,
        foundry_manager: FoundryManager,
    ):
        self.provider = provider
        self.prompt_engine = prompt_engine
        self.instruction_factory = instruction_factory
        self.foundry_manager = foundry_manager
        logger.info("TechnicianService initialized.")

    def get_tool_invocations(self, task: str) -> Optional[List[BlueprintInvocation]]:
        """
        Takes a single task and returns a list of tool invocations to accomplish it.

        Args:
            task: A single, human-readable task from the Architect's plan.

        Returns:
            A list of BlueprintInvocation objects, or None if translation fails.
        """
        all_tools = self.foundry_manager.get_llm_tool_definitions()
        technician_prompt = self.prompt_engine.create_technician_prompt(task, all_tools)

        technician_response = self.provider.get_response(
            prompt=technician_prompt,
            mode='build',
            tools=all_tools,
            system_instruction_override=TECHNICIAN_SYSTEM_PROMPT
        )

        invocations = self.instruction_factory.create_invocations_from_plan_data(technician_response)

        if not invocations:
            logger.error(
                f"Technician failed to convert task: '{task}'. "
                f"Response: {technician_response.get('text', 'No text in response.')}"
            )
            return None

        return invocations