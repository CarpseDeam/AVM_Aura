"""
Establish the main, interactive command-line entry point for the application,
handling user input, event publishing, and LLM provider configuration.
"""
import logging
import os
import sys
from typing import List

# External dependencies are assumed to be installed via pip
from prompt_toolkit import prompt
from prompt_toolkit.history import InMemoryHistory
from rich.console import Console

from event_bus import EventBus
from events import UserCommandEntered, UserPromptEntered
from foundry.foundry_manager import FoundryManager
from providers.base import LLMProvider
from providers.gemini_provider import GeminiProvider
from providers.ollama_provider import OllamaProvider
from services.command_handler import CommandHandler
from services.executor import ExecutorService
from services.llm_operator import LLMOperator

# Setup logger for this module
logger = logging.getLogger(__name__)


def _configure_llm_provider() -> LLMProvider:
    """
    Configures and returns an LLM provider based on environment variables.

    This function reads the `LLM_PROVIDER` environment variable to determine
    which provider to instantiate. It supports "ollama" and "gemini".
    It will exit the application if the required configuration is missing
    or invalid.

    Returns:
        An instance of a class that conforms to the LLMProvider interface.
    """
    provider_name = os.getenv("LLM_PROVIDER")

    if not provider_name:
        logger.critical("FATAL: LLM_PROVIDER environment variable not set. Please set it to 'ollama' or 'gemini'.")
        sys.exit(1)

    provider_name = provider_name.lower()
    logger.info(f"Attempting to configure LLM provider: '{provider_name}'")

    if provider_name == "ollama":
        model = os.getenv("OLLAMA_MODEL", "Qwen3-coder")
        logger.info(f"Using Ollama provider with model: '{model}'")
        return OllamaProvider(model_name=model)  # Corrected to use model_name

    elif provider_name == "gemini":
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.critical(
                "FATAL: GEMINI_API_KEY environment variable is not set. It is required for the Gemini provider.")
            sys.exit(1)

        # --- THIS IS THE NEW LOGIC ---
        # Look for a specific Gemini model, or default to 1.5 Pro.
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
        logger.info(f"Using Gemini provider with model: '{model_name}'")
        return GeminiProvider(api_key=api_key, model_name=model_name)
        # --- END NEW LOGIC ---

    else:
        logger.critical(f"FATAL: Invalid LLM_PROVIDER: '{provider_name}'. Supported values are 'ollama' or 'gemini'.")
        sys.exit(1)


def main() -> None:
    """
    The main entry point for the interactive command-line application.

    Configures the LLM provider, initializes components, wires them together
    via the event bus, and runs the main input loop. The loop is driven by
    the CommandHandler's state. It parses user input, publishes all actions
    as events, and checks the handler's state to determine when to exit.
    """
    # --- Provider Configuration ---
    # This function will exit the application if configuration is invalid.
    provider = _configure_llm_provider()

    # --- Initialization ---
    event_bus = EventBus()
    console = Console()
    history = InMemoryHistory()
    foundry_manager = FoundryManager()
    cmd_handler = CommandHandler(console=console)
    # The ExecutorService subscribes to events upon initialization.
    executor = ExecutorService(event_bus=event_bus)
    # Inject the provider, event bus, and foundry manager into the LLMOperator.
    llm_operator = LLMOperator(
        console=console,
        provider=provider,
        event_bus=event_bus,
        foundry_manager=foundry_manager,
    )

    # --- Wiring (Subscription) ---
    event_bus.subscribe(UserCommandEntered, cmd_handler.handle)
    event_bus.subscribe(UserPromptEntered, llm_operator.handle)

    # --- Application Start ---
    console.print("[bold green]Welcome to the Interactive Application CLI![/bold green]")
    console.print("Type a prompt or use '/' for commands (e.g., /exit, /quit).")

    while not cmd_handler.should_exit:
        try:
            user_input = prompt(">>> ", history=history).strip()

            if not user_input:
                continue

            if user_input.startswith('/'):
                parts: List[str] = user_input[1:].split()
                if not parts:
                    console.print("[yellow]Please enter a command after '/'.[/yellow]")
                    continue
                command = parts[0]
                args = parts[1:]
                event = UserCommandEntered(command=command, args=args)
                event_bus.publish(event)
            else:
                event = UserPromptEntered(prompt_text=user_input)
                event_bus.publish(event)

        except (KeyboardInterrupt, EOFError):
            logger.info("Exit signal (Ctrl+C or Ctrl+D) detected.")
            console.print("\n[bold red]Exit signal detected. Shutting down.[/bold red]")
            break
        except Exception as e:
            logger.error(f"An unexpected error occurred in the main loop: {e}", exc_info=True)
            console.print(f"[bold red]An unexpected error occurred: {e}[/bold red]")
            break

    logger.info("Application main loop finished. Exiting.")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)-25s - %(levelname)-8s - %(message)s',
        stream=sys.stdout,
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    main()
    print("Application has terminated.")