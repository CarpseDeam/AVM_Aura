"""
Establish the main, interactive command-line entry point for the application,
handling user input and event publishing.
"""
import logging
import sys
from typing import List

# External dependencies are assumed to be installed via pip
from prompt_toolkit import prompt
from prompt_toolkit.history import InMemoryHistory
from rich.console import Console

from event_bus import EventBus
from events import UserCommandEntered, UserPromptEntered
from services.command_handler import CommandHandler
from services.llm_operator import LLMOperator

# Setup logger for this module
logger = logging.getLogger(__name__)


def main() -> None:
    """
    The main entry point for the interactive command-line application.

    Initializes components, wires them together via the event bus, and runs
    the main input loop. The loop is driven by the CommandHandler's state.
    It parses user input, publishes all actions as events, and checks the
    handler's state to determine when to exit.
    """
    # --- Initialization ---
    event_bus = EventBus()
    console = Console()
    history = InMemoryHistory()
    cmd_handler = CommandHandler(console=console)
    llm_operator = LLMOperator(console=console)

    # --- Wiring (Subscription) ---
    # The command handler is subscribed to command events. It will update its
    # internal state (e.g., `should_exit`) when it processes an exit command.
    event_bus.subscribe(UserCommandEntered, cmd_handler.handle)
    event_bus.subscribe(UserPromptEntered, llm_operator.handle)

    # --- Application Start ---
    console.print("[bold green]Welcome to the Interactive Application CLI![/bold green]")
    console.print("Type a prompt or use '/' for commands (e.g., /exit, /quit).")

    # The main loop is now driven by the command handler's `should_exit` property.
    # This property will be flipped to True when the handler processes an exit command.
    while not cmd_handler.should_exit:
        try:
            user_input = prompt(">>> ", history=history).strip()

            if not user_input:
                continue

            if user_input.startswith('/'):
                parts: List[str] = user_input[1:].split()
                if not parts:
                    # User just typed "/" with no command
                    console.print("[yellow]Please enter a command after '/'.[/yellow]")
                    continue
                command = parts[0]
                args = parts[1:]
                event = UserCommandEntered(command=command, args=args)
                # All events, including commands, are published to the event bus.
                # The direct call to the handler is removed.
                event_bus.publish(event)
            else:
                event = UserPromptEntered(prompt_text=user_input)
                event_bus.publish(event)

        except (KeyboardInterrupt, EOFError):
            logger.info("Exit signal (Ctrl+C or Ctrl+D) detected.")
            console.print("\n[bold red]Exit signal detected. Shutting down.[/bold red]")
            # Gracefully exit the loop on user interrupt.
            break
        except Exception as e:
            logger.error(f"An unexpected error occurred in the main loop: {e}", exc_info=True)
            console.print(f"[bold red]An unexpected error occurred: {e}[/bold red]")
            # Force exit on unexpected errors.
            break

    logger.info("Application main loop finished. Exiting.")


if __name__ == "__main__":
    # Configure basic logging for the entire application
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)-12s - %(levelname)-8s - %(message)s',
        stream=sys.stdout,
    )
    # Suppress overly verbose loggers from dependencies to keep output clean
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    main()
    print("Application has terminated.")