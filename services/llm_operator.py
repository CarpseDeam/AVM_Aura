"""
This module defines the LLMOperator, which is responsible for handling
prompts from the user, interacting with a language model provider,
parsing the structured JSON response, and publishing action events.
"""
import json
import logging
from typing import Any, Dict

from rich.console import Console
from rich.status import Status

from event_bus import EventBus
from events import ActionReadyForExecution, UserPromptEntered
from providers.base import LLMProvider

logger = logging.getLogger(__name__)


class LLMOperator:
    """
    Handles user prompts, gets structured JSON from an LLM, and publishes events.

    This operator transforms a user's text prompt into a structured action
    by querying an LLM that is expected to return JSON. It validates the
    structure of the JSON and, if valid, publishes an `ActionReadyForExecution`
    event to the event bus for other services to consume.
    """

    def __init__(self, console: Console, provider: LLMProvider, event_bus: EventBus):
        """
        Initializes the LLM operator.

        Args:
            console: The Rich Console object for printing status and errors.
            provider: An instance of a class that adheres to the LLMProvider interface.
            event_bus: The application's central event bus for publishing events.
        """
        self.console = console
        self.provider = provider
        self.event_bus = event_bus

    def _is_valid_action(self, data: Any) -> bool:
        """
        Validates if the provided data is a well-formed action dictionary.

        A valid action is a dictionary containing:
        - A non-empty "action" key with a string value.
        - A "parameters" key with a dictionary value.

        Args:
            data: The data parsed from the LLM's JSON response.

        Returns:
            True if the data represents a valid action, False otherwise.
        """
        if not isinstance(data, dict):
            logger.warning(
                "Validation failed: LLM output is not a dictionary. Data: %s", data
            )
            self.console.print(
                "[bold red]Error:[/bold red] LLM output was not a valid action structure (expected a JSON object)."
            )
            self.console.print()
            return False

        action = data.get("action")
        if not isinstance(action, str) or not action:
            logger.warning(
                "Validation failed: 'action' key is missing or not a non-empty string. Data: %s",
                data,
            )
            self.console.print(
                "[bold red]Error:[/bold red] LLM output is missing a valid 'action' name."
            )
            self.console.print()
            return False

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
            return False

        return True

    def handle(self, event: UserPromptEntered) -> None:
        """
        Handles the event for a user entering a standard prompt.

        This method displays a "thinking" status, sends the prompt to the
        injected LLM provider, attempts to parse the response as JSON,
        validates its structure, and publishes an `ActionReadyForExecution`
        event if successful.

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
                response_text = self.provider.get_response(event.prompt_text)
                logger.debug(f"Raw LLM response: {response_text}")

            try:
                action_data: Dict[str, Any] = json.loads(response_text)
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
                return

            if not self._is_valid_action(action_data):
                # The validation method handles logging and printing errors.
                return

            logger.info(
                f"Successfully parsed a valid action: {action_data.get('action')}"
            )
            action_event = ActionReadyForExecution(action=action_data)
            self.event_bus.publish(action_event)
            logger.info("Published ActionReadyForExecution event to the event bus.")

        except Exception as e:
            logger.error(
                f"An error occurred while processing the prompt: {e}", exc_info=True
            )
            self.console.print(
                f"[bold red]Error:[/bold red] Could not get a response from the LLM provider."
            )
            self.console.print()