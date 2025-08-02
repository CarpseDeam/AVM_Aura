# services/llm_operator.py

"""
This module defines the LLMOperator, which is responsible for handling
prompts from the user, interacting with a language model provider using a
strict tool-based protocol, parsing the structured JSON response, and
publishing typed action events. It can also display LLM responses in a GUI.
"""

import json
import logging
from typing import Any, Callable, Dict, Optional, Union

from rich.console import Console

from event_bus import EventBus
# This is the line we are fixing! Added UserPromptEntered here.
from events import ActionReadyForExecution, BlueprintInvocation, UserPromptEntered
from foundry.foundry_manager import FoundryManager
from providers.base import LLMProvider

logger = logging.getLogger(__name__)


class LLMOperator:
    """
    Handles user prompts, gets structured JSON from an LLM, and publishes events.

    This operator transforms a user's text prompt into a structured, typed action
    by querying an LLM with a predefined set of tools. It validates the LLM's
    response to ensure it corresponds to a known tool and, if valid, publishes
    an `ActionReadyForExecution` event containing a `BlueprintInvocation` object.
    It can be configured with a display callback to send status updates and LLM
    text responses to a UI.
    """

    def __init__(
        self,
        console: Console,
        provider: LLMProvider,
        event_bus: EventBus,
        foundry_manager: FoundryManager,
        display_callback: Optional[Callable[[str], None]] = None,
    ):
        """
        Initializes the LLM operator.

        Args:
            console: The Rich Console object for printing status and errors.
            provider: An instance of a class that adheres to the LLMProvider interface.
            event_bus: The application's central event bus for publishing events.
            foundry_manager: The manager that provides tool blueprint definitions.
            display_callback: An optional function to send status messages or LLM
                              text responses for display in a UI.
        """
        self.console = console
        self.provider = provider
        self.event_bus = event_bus
        self.foundry_manager = foundry_manager
        self.display_callback = display_callback

    def _display(self, message: str) -> None:
        """
        Sends a message to the registered display callback, if available.

        Args:
            message: The string message to display.
        """
        if self.display_callback:
            self.display_callback(message)

    def _parse_and_validate_llm_response(
        self, llm_response: Union[str, Dict[str, Any]]
    ) -> Optional[BlueprintInvocation]:
        """
        Parses the LLM's response and validates it against known blueprints.

        This method handles three cases:
        1. If the response is a dictionary (a native tool call), it validates it.
        2. If the response is a string that is valid JSON, it is parsed and validated.
        3. If the response is a string that is not valid JSON, it is treated as a
           plain text response from the LLM and displayed.

        Args:
            llm_response: The raw response from the LLM provider.

        Returns:
            A `BlueprintInvocation` object if a valid tool call was parsed,
            otherwise `None`.
        """
        if isinstance(llm_response, str):
            try:
                data: Dict[str, Any] = json.loads(llm_response)
            except json.JSONDecodeError:
                # This is not an error, but a text response from the LLM.
                logger.info("LLM returned a non-JSON string response. Displaying as text.")
                self._display(f"💬 LLM Response:\n---\n{llm_response}\n---")
                return None
        elif isinstance(llm_response, dict):
            data = llm_response
        else:
            logger.error("Received unexpected response type from provider: %s", type(llm_response).__name__)
            self._display(f"❌ Error: Received unexpected response type from provider: {type(llm_response).__name__}")
            return None


        # --- VALIDATION LOGIC ---
        tool_name = data.get("tool_name")
        if not isinstance(tool_name, str) or not tool_name:
            logger.warning(
                "Validation failed: 'tool_name' key is missing or not a non-empty string. Data: %s",
                data,
            )
            self._display("❌ Error: LLM output is missing a valid 'tool_name'.")
            return None

        arguments = data.get("arguments")
        if not isinstance(arguments, dict):
            logger.warning(
                "Validation failed: 'arguments' key is missing or not a dictionary. Data: %s",
                data,
            )
            self._display("❌ Error: LLM output is missing valid 'arguments'.")
            return None

        blueprint = self.foundry_manager.get_blueprint(tool_name)
        if not blueprint:
            logger.warning("LLM requested an unknown tool: '%s'", tool_name)
            self._display(f"❌ Error: The LLM requested a tool ('{tool_name}') that does not exist.")
            return None

        logger.info("Successfully validated tool call for blueprint: %s", tool_name)
        return BlueprintInvocation(blueprint=blueprint, parameters=arguments)


    def handle(self, event: UserPromptEntered) -> None:
        """
        Handles the event for a user entering a standard prompt.

        This method gets tool definitions, sends the prompt to the LLM provider,
        parses and validates the response, and publishes an `ActionReadyForExecution`
        event with a typed instruction object if successful.

        Args:
            event: The UserPromptEntered event instance.
        """
        logger.info(
            f"Handling UserPromptEntered event with text: '{event.prompt_text}'"
        )
        self._display("🧠 Thinking...")

        try:
            # The console.status is for the terminal UI, which can run in parallel.
            with self.console.status(
                "[bold green]Thinking...[/bold green]", spinner="dots"
            ):
                tool_definitions = self.foundry_manager.get_llm_tool_definitions()
                response = self.provider.get_response(
                    event.prompt_text, tools=tool_definitions
                )
                logger.debug(f"Raw LLM response: {response}")

            instruction = self._parse_and_validate_llm_response(response)

            if instruction:
                action_event = ActionReadyForExecution(instruction=instruction)
                self.event_bus.publish(action_event)
                logger.info("Published ActionReadyForExecution event to the event bus.")
            # If instruction is None, the parsing method has already logged,
            # and potentially displayed a message (either an error or a text response).

        except Exception as e:
            logger.error(
                f"An error occurred while processing the prompt: {e}", exc_info=True
            )
            self._display(f"❌ Error: Could not get a response from the LLM provider.")