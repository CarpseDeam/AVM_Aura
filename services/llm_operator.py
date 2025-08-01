# services/llm_operator.py

"""
This module defines the LLMOperator, which is responsible for handling
prompts from the user, interacting with a language model provider using a
strict tool-based protocol, parsing the structured JSON response, and
publishing typed action events.
"""

import json
import logging
from typing import Any, Dict, Optional, Union

from rich.console import Console

from event_bus import EventBus
from events import ActionReadyForExecution, BlueprintInvocation, RawCodeInstruction
from foundry.foundry_manager import FoundryManager
from providers.base import LLMProvider

logger = logging.getLogger(__name__)


class LLMOperator:
    """
    Handles user prompts, gets structured JSON from an LLM, and publishes events.

    This operator transforms a user's text prompt into a structured, typed action
    by querying an LLM with a predefined set of tools. It validates the LLM's
    response to ensure it corresponds to a known tool and, if valid, publishes
    an `ActionReadyForExecution` event containing a `BlueprintInvocation` or
    `RawCodeInstruction` object.
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
        self, llm_response: Union[str, Dict[str, Any]]
    ) -> Optional[Union[BlueprintInvocation, RawCodeInstruction]]:
        """
        Parses the LLM's response and validates it against known blueprints.

        This method handles two cases:
        1. If the response is a dictionary (a native tool call), it validates it.
        2. If the response is a string, it attempts to parse it as JSON.

        Args:
            llm_response: The raw response from the LLM provider.

        Returns:
            A `BlueprintInvocation` or `RawCodeInstruction` if valid, otherwise `None`.
        """
        if isinstance(llm_response, str):
            try:
                data: Dict[str, Any] = json.loads(llm_response)
            except json.JSONDecodeError:
                logger.error(
                    "Failed to decode LLM response as JSON: %s",
                    llm_response,
                    exc_info=True,
                )
                self.console.print(
                    "[bold red]Error:[/bold red] The LLM response was not valid JSON."
                )
                self.console.print()
                return None
        elif isinstance(llm_response, dict):
            data = llm_response
        else:
            logger.error("Received unexpected response type from provider: %s", type(llm_response).__name__)
            return None


        # --- VALIDATION LOGIC ---
        # The provider returns a dictionary with 'tool_name' and 'arguments'.
        tool_name = data.get("tool_name")
        if not isinstance(tool_name, str) or not tool_name:
            logger.warning(
                "Validation failed: 'tool_name' key is missing or not a non-empty string. Data: %s",
                data,
            )
            self.console.print(
                "[bold red]Error:[/bold red] LLM output is missing a valid 'tool_name'."
            )
            self.console.print()
            return None

        arguments = data.get("arguments")
        if not isinstance(arguments, dict):
            logger.warning(
                "Validation failed: 'arguments' key is missing or not a dictionary. Data: %s",
                data,
            )
            self.console.print(
                "[bold red]Error:[/bold red] LLM output is missing valid 'arguments'."
            )
            self.console.print()
            return None
            
        # --- End Validation ---


        # Look up the blueprint corresponding to the tool name.
        blueprint = self.foundry_manager.get_blueprint(tool_name)
        if not blueprint:
            logger.warning("LLM requested an unknown tool: '%s'", tool_name)
            self.console.print(
                f"[bold red]Error:[/bold red] The LLM requested a tool ('{tool_name}') that does not exist."
            )
            self.console.print()
            return None

        logger.info("Successfully validated tool call for blueprint: %s", tool_name)
        # Create the strongly-typed invocation object.
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

        try:
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
            # If instruction is None, the parsing method has already logged and printed errors.

        except Exception as e:
            logger.error(
                f"An error occurred while processing the prompt: {e}", exc_info=True
            )
            self.console.print(
                f"[bold red]Error:[/bold red] Could not get a response from the LLM provider."
            )
            self.console.print()