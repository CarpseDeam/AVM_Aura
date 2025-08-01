"""
This module defines the LLMOperator, which is responsible for handling
prompts from the user, interacting with a language model provider,
and displaying the results.
"""
import logging
from rich.console import Console
from rich.markdown import Markdown
from rich.status import Status

from events import UserPromptEntered
from providers.base import LLMProvider

logger = logging.getLogger(__name__)


class LLMOperator:
    """Handles user-entered prompts destined for an LLM."""

    def __init__(self, console: Console, provider: LLMProvider):
        """
        Initializes the LLM operator.

        Args:
            console: The Rich Console object for printing output.
            provider: An instance of a class that adheres to the LLMProvider interface.
        """
        self.console = console
        self.provider = provider

    def handle(self, event: UserPromptEntered) -> None:
        """
        Handles the event for a user entering a standard prompt.

        This method displays a "thinking" status, sends the prompt to the
        injected LLM provider, and renders the Markdown response to the console.

        Args:
            event: The UserPromptEntered event instance.
        """
        logger.info(f"Handling UserPromptEntered event with text: '{event.prompt_text}'")

        try:
            # Use a status context manager to show a "thinking" message
            with self.console.status("[bold green]Thinking...[/bold green]", spinner="dots"):
                response_text = self.provider.get_response(event.prompt_text)

            logger.info("Successfully received response from LLM provider.")
            # Render the response as Markdown for better formatting
            self.console.print(Markdown(response_text, style="bright_magenta"), justify="left")
            self.console.print()  # Add a newline for spacing

        except Exception as e:
            # Log the full exception for debugging
            logger.error(f"An error occurred while processing the prompt: {e}", exc_info=True)
            # Show a user-friendly error message
            self.console.print(f"[bold red]Error:[/bold red] Could not get a response from the LLM provider.")
            self.console.print()