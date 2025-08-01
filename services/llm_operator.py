# services/llm_operator.py

"""
This module defines the LLMOperator, which is responsible for handling
prompts from the user, interacting with a language model provider using a
strict tool-based protocol, parsing the structured JSON response, and
publishing typed action events.
"""

import json
import logging
from typing import Any, Dict, Optional

from rich.console import Console

from event_bus import EventBus
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
    """

    def __init__(
        self,
        console: Console,
        provider: LLMProvider,
        event_bus: EventBus,
        foundry_manager: FoundryManager,
    ):
        """
        Initializes the LLM operator.

        Args:
            console: The Rich Console object for printing status and errors.
            provider: An instance of a class that adheres to the LLMProvider interface.
            event_bus: The application's central event bus for publishing events.
            foundry_manager: The manager that provides tool blueprint definitions.
        """
        self.console = console
        self.provider = provider
        self.event_bus = event_bus
        self.foundry_manager = foundry_manager

    def _parse_and_validate_llm_response(
        self, response_text: str
    ) -> Optional[BlueprintInvocation]:
        """
        Parses the LLM's JSON response and validates it against known blueprints.

        This method performs the following steps:
        1. Decodes the JSON string.
        2. Validates that the top-level structure is a dictionary.
        3. Checks for the presence and type of 'action' and 'parameters' keys.
        4. Verifies that the 'action' name corresponds to a registered blueprint.
        5. Constructs a typed `BlueprintInvocation` object if validation succeeds.

        Args:
            response_text: The raw string response from the LLM.

        Returns:
            A `BlueprintInvocation` object if the response is valid, otherwise `None`.
        """
        try:
            data: Dict[str, Any] = json.loads(response_text)
        except json.JSONDecodeError:
            logger.error(
                "Failed to decode LLM response as JSON: %s",
                response_text,
                exc_info=True,
            )
            self.console.print(
                "[bold red]Error:[/bold red] The LLM response was not valid JSON."
            )
            self.console.print()
            return None

        if not isinstance(data, dict):
            logger.warning(
                "Validation failed: LLM output is not a dictionary. Data: %s", data
            )
            self.console.print(
                "[bold red]Error:[/bold red] LLM output was not a valid action structure (expected a JSON object)."
            )
            self.console.print()
            return None

        action_name = data.get("action")
        if not isinstance(action_name, str) or not action_name:
            logger.warning(
                "Validation failed: 'action' key is missing or not a non-empty string. Data: %s",
                data,
            )
            self.console.print(
                "[bold red]Error:[/bold red] LLM output is missing a valid 'action' name."
            )
            self.console.print()
            return None

        parameters = data.get("parameters")
        if not isinstance(parameters, dict):
            logger.warning(
                "Validation failed: 'parameters' key is missing or not a dictionary. Data: %s",
                data,
            )
            self.console.print(
                "[bold red]Error:[/bold red] LLM output is missing valid 'parameters'."
            )
            self.console.print()
            return None

        blueprint = self.foundry_manager.get_blueprint(action_name)
        if not blueprint:
            logger.warning("LLM requested an unknown tool: '%s'", action_name)
            self.console.print(
                f"[bold red]Error:[/bold red] The LLM requested a tool ('{action_name}') that does not exist."
            )
            self.console.print()
            return None

        logger.info("Successfully validated tool call for blueprint: %s", action_name)
        return BlueprintInvocation(blueprint=blueprint, parameters=parameters)

    def handle(self, event: UserPromptEntered) -> None:
        """
        Handles the event for a user entering a standard prompt.

        This method displays a "thinking" status, sends the prompt and available
        tool definitions to the LLM provider, attempts to parse and validate
        the response, and publishes an `ActionReadyForExecution` event with a
        typed `BlueprintInvocation` if successful.

        Args:
            event: The UserPromptEntered event instance.
        """
        logger.info(
            f"Handling UserPromptEntered event with text: '{event.prompt_text}'"
        )

        try:
            with self.console.status(
                "[bold green]Thinking...[/bold green]", spinner="dots"
            ):
                tool_definitions = self.foundry_manager.get_llm_tool_definitions()
                # We assume the provider's get_response method can accept a 'tools'
                # argument to enable tool-calling mode.
                response_text = self.provider.get_response(
                    event.prompt_text, tools=tool_definitions
                )
                logger.debug(f"Raw LLM response: {response_text}")

            invocation = self._parse_and_validate_llm_response(response_text)

            if invocation:
                logger.info(
                    "Successfully parsed a valid action: %s",
                    invocation.blueprint.name,
                )
                action_event = ActionReadyForExecution(instruction=invocation)
                self.event_bus.publish(action_event)
                logger.info("Published ActionReadyForExecution event to the event bus.")
            # If invocation is None, the parsing method has already logged and printed errors.

        except Exception as e:
            logger.error(
                f"An error occurred while processing the prompt: {e}", exc_info=True
            )
            self.console.print(
                f"[bold red]Error:[/bold red] Could not get a response from the LLM provider."
            )
            self.console.print()