# services/command_handler.py
"""
Handles user-entered commands and manages application state, such as exiting.

This module is responsible for processing command events, updating its internal
state based on those commands, and providing a way for the main application
loop to query that state (e.g., to determine if it should shut down).
"""

import logging
from rich.console import Console
from events import UserCommandEntered

logger = logging.getLogger(__name__)


class CommandHandler:
    """Handles user-entered commands and manages application state like exiting."""

    def __init__(self, console: Console):
        """
        Initializes the command handler.

        Args:
            console: The Rich Console object for printing user-facing output.
        """
        self.console = console
        self._should_exit = False

    @property
    def should_exit(self) -> bool:
        """
        Property to query if the application has been signaled to exit.

        Returns:
            True if an exit command has been processed, False otherwise.
        """
        return self._should_exit

    def handle(self, event: UserCommandEntered) -> None:
        """
        Processes a command event and updates internal state.

        This method processes specific commands like '/exit' by setting an
        internal flag and logs other commands. It does not return any value,
        aligning with a pure event-driven architecture.

        Args:
            event: The UserCommandEntered event instance.
        """
        logger.info(f"Handling UserCommandEntered event: '/{event.command}' with args: {event.args}")

        if event.command.lower() in ["exit", "quit"]:
            self.console.print("[bold red]Exit command received. Shutting down.[/bold red]")
            self._should_exit = True
        else:
            self.console.print(
                f"[yellow]COMMAND RECEIVED:[/yellow] [italic]/{event.command}[/italic] | Args: {event.args}"
            )
            self.console.print("[dim]... (In a real app, command-specific logic would run) ...[/dim]\n")