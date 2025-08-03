# services/command_handler.py
import logging
from foundry import FoundryManager
from .view_formatter import format_as_box

logger = logging.getLogger(__name__)


class CommandHandler:
    """
    Handles direct, CLI-style slash commands from the user. It provides a fast,
    deterministic path for actions that don't require LLM reasoning.
    """

    def __init__(self, foundry_manager: FoundryManager, display_callback):
        """
        Initializes the CommandHandler.

        Args:
            foundry_manager: An instance of FoundryManager to access tools.
            display_callback: A thread-safe function to send output to the GUI.
        """
        self.foundry = foundry_manager
        self.display = display_callback
        logger.info("CommandHandler initialized and ready.")

    def handle(self, event):  # event is a UserCommandEntered event
        """
        Receives a command event and routes it to the correct handler method.
        """
        command = event.command.lower()
        args = event.args
        logger.info(f"Handling command '/{command}' with args: {args}")

        try:
            if command == "list_files":
                self._handle_list_files(args)
            elif command == "read":
                self._handle_read_file(args)
            elif command == "lint":
                self._handle_lint(args)
            elif command == "help":
                self._handle_help()
            else:
                error_text = f"Unknown command: /{command}\nType /help to see a list of available commands."
                self.display(format_as_box(f"Error: Unknown Command", error_text), "avm_error")
        except Exception as e:
            error_message = f"An unexpected error occurred while executing '/{command}': {e}"
            logger.error(error_message, exc_info=True)
            self.display(format_as_box(f"Error: {command}", error_message), "avm_error")

    def _handle_list_files(self, args: list):
        """Handler for the /list_files command."""
        list_files_action = self.foundry.get_action("list_files")
        path = args[0] if args else "."
        result = list_files_action(path=path)
        formatted_output = format_as_box(f"Directory Listing: {path}", result)
        self.display(formatted_output, "avm_output")

    def _handle_read_file(self, args: list):
        """Handler for the /read command. Will add content to Code Viewer."""
        if not args:
            self.display(format_as_box("Usage Error", "Please provide a file path.\nUsage: /read <path/to/file>"),
                         "avm_error")
            return

        read_file_action = self.foundry.get_action("read_file")
        path = args[0]
        content = read_file_action(path=path)

        # In the future, this will publish an event to open the code viewer.
        # For now, we'll display it in an ASCII box.
        # This is a great placeholder for our next integration step!
        title = f"Contents: {path}"
        # Truncate content for display if it's too long
        display_content = (content[:1000] + '...') if len(content) > 1000 else content
        formatted_output = format_as_box(title, display_content)
        self.display(formatted_output, "avm_output")

    def _handle_lint(self, args: list):
        """Handler for the /lint command."""
        if not args:
            self.display(format_as_box("Usage Error", "Please provide a file path.\nUsage: /lint <path/to/file>"),
                         "avm_error")
            return

        lint_action = self.foundry.get_action("lint_file")
        path = args[0]
        result = lint_action(path=path)
        formatted_output = format_as_box(f"Lint Report: {path}", result)
        self.display(formatted_output, "avm_output")

    def _handle_help(self):
        """Displays a help message with available commands."""
        help_text = (
            "Aura Direct Commands:\n\n"
            "/help                 - Shows this help message.\n"
            "/list_files [path]    - Lists files in the specified directory.\n"
            "/read <path>          - Reads the content of a file.\n"
            "/lint <path>          - Lints a Python file for style errors."
        )
        self.display(format_as_box("Aura Help", help_text), "system_message")