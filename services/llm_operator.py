import logging
from rich.console import Console
from events import UserPromptEntered

logger = logging.getLogger(__name__)

class LLMOperator:
    """Handles user-entered prompts destined for an LLM."""

    def __init__(self, console: Console):
        """
        Initializes the LLM operator.

        Args:
            console: The Rich Console object for printing output.
        """
        self.console = console

    def handle(self, event: UserPromptEntered) -> None:
        """
        Handles the event for a user entering a standard prompt.

        In a real application, this would trigger the LLM provider to get a response.
        For now, it just logs the event and prints a confirmation to the console.

        Args:
            event: The UserPromptEntered event instance.
        """
        logger.info(f"Handling UserPromptEntered event with text: '{event.prompt_text}'")
        self.console.print(f"[cyan]PROMPT RECEIVED:[/cyan] [italic]{event.prompt_text}[/italic]")
        self.console.print("[dim]... (In a real app, this would trigger LLM processing) ...[/dim]\\n")