# services/llm_operator.py
"""
This module defines the LLMOperator, which is responsible for orchestrating the
interaction between user prompts, the context memory, the available tools (from
the Foundry), and the underlying LLM provider.
"""

import json
import logging
from typing import Any, Callable, Dict, Optional, Union

from rich.console import Console

from event_bus import EventBus
from events import ActionReadyForExecution, BlueprintInvocation, UserPromptEntered
from foundry.foundry_manager import FoundryManager
from providers.base import LLMProvider
from services.context_manager import ContextManager

logger = logging.getLogger(__name__)


class LLMOperator:
    """
    Orchestrates LLM interactions by managing context, tools, and responses.

    This class receives user prompts, retrieves the current working memory context,
    fetches available tool definitions, and passes all this information to the
    configured LLM provider. It then parses the provider's response, validating
    it and converting it into an executable action if a tool is invoked.
    """

    def __init__(
        self,
        console: Console,
        provider: LLMProvider,
        event_bus: EventBus,
        foundry_manager: FoundryManager,
        context_manager: ContextManager,
        display_callback: Optional[Callable[[str, str], None]] = None,
    ):
        """
        Initializes the LLMOperator.

        Args:
            console (Console): The Rich console for output.
            provider (LLMProvider): The concrete LLM provider to use for responses.
            event_bus (EventBus): The central event bus for communication.
            foundry_manager (FoundryManager): The manager for available tools.
            context_manager (ContextManager): The service for managing AVM context.
            display_callback (Optional[Callable[[str, str], None]]): A function
                to call to display output to the user.
        """
        self.console = console
        self.provider = provider
        self.event_bus = event_bus
        self.foundry_manager = foundry_manager
        self.context_manager = context_manager
        self.display_callback = display_callback

    def _display(self, message: str, tag: str) -> None:
        """
        Sends a message to the display callback, if one is configured.

        Args:
            message (str): The message to display.
            tag (str): A tag for classifying the message (e.g., 'system_message').
        """
        if self.display_callback:
            self.display_callback(message, tag)

    def _parse_and_validate_llm_response(
        self, llm_response: Union[str, Dict[str, Any]]
    ) -> Optional[BlueprintInvocation]:
        """
        Parses and validates the response from the LLM provider.

        If the response is a valid tool call, it's converted into a
        BlueprintInvocation. Otherwise, it's treated as a text response.

        Args:
            llm_response: The raw response from the LLM provider, which can be
                          a JSON string, a dictionary, or a plain text string.

        Returns:
            An Optional[BlueprintInvocation] if a valid tool call is found,
            otherwise None.
        """
        if isinstance(llm_response, str):
            try:
                data: Dict[str, Any] = json.loads(llm_response)
            except json.JSONDecodeError:
                logger.info("LLM returned a non-JSON string. Displaying as text.")
                self._display(f"💬 LLM Response:\n{llm_response}", "avm_response")
                return None
        elif isinstance(llm_response, dict):
            data = llm_response
        else:
            logger.error(
                "Received unexpected response type from provider: %s",
                type(llm_response).__name__,
            )
            self._display("Error: Unexpected response type from provider.", "avm_error")
            return None

        tool_name = data.get("tool_name")
        if not tool_name:
            self._display("Error: LLM output missing 'tool_name'.", "avm_error")
            return None

        arguments = data.get("arguments")
        if not isinstance(arguments, dict):
            self._display("Error: LLM output missing 'arguments'.", "avm_error")
            return None

        blueprint = self.foundry_manager.get_blueprint(tool_name)
        if not blueprint:
            self._display(
                f"Error: LLM requested unknown tool '{tool_name}'.", "avm_error"
            )
            return None

        return BlueprintInvocation(blueprint=blueprint, parameters=arguments)

    def handle(self, event: UserPromptEntered) -> None:
        """
        Handles a UserPromptEntered event.

        This method retrieves the current context, gets tool definitions, calls
        the LLM provider, and then processes the response. If the response is a
        valid tool invocation, it publishes an ActionReadyForExecution event.

        Args:
            event (UserPromptEntered): The event containing the user's prompt.
        """
        self._display("🧠 Thinking...", "system_message")
        try:
            tool_definitions = self.foundry_manager.get_llm_tool_definitions()
            current_context = self.context_manager.get_context()

            response = self.provider.get_response(
                event.prompt_text, context=current_context, tools=tool_definitions
            )

            instruction = self._parse_and_validate_llm_response(response)
            if instruction:
                action_event = ActionReadyForExecution(instruction=instruction)
                self.event_bus.publish(action_event)
        except Exception as e:
            logger.error(f"Error processing prompt: {e}", exc_info=True)
            self._display("Error getting response from provider.", "avm_error")