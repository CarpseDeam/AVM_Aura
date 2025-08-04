# services/command_handler.py
import logging
from foundry import FoundryManager
from .view_formatter import format_as_box
from events import DisplayFileInEditor, DirectToolInvocationRequest
from event_bus import EventBus
from .project_manager import ProjectManager

logger = logging.getLogger(__name__)


class CommandHandler:
    """
    Handles direct, CLI-style slash commands from the user. It provides a fast,
    deterministic path for actions that don't require LLM reasoning.
    """

    def __init__(self, foundry_manager: FoundryManager, event_bus: EventBus,
                 project_manager: ProjectManager, display_callback):
        """
        Initializes the CommandHandler.

        Args:
            foundry_manager: An instance of FoundryManager to access tools.
            event_bus: The central event bus for publishing events.
            project_manager: The service for managing project contexts.
            display_callback: A thread-safe function to send output to the GUI.
        """
        self.foundry = foundry_manager
        self.event_bus = event_bus
        self.project_manager = project_manager
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
            elif command == "index":
                self._handle_index()
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
        relative_path = args[0] if args else "."
        resolved_path = self.project_manager.resolve_path(relative_path)
        result = list_files_action(path=str(resolved_path))

        display_path = self.project_manager.get_active_project_name() or "Current Directory"
        if relative_path != ".":
            display_path = f"{display_path}/{relative_path}"

        formatted_output = format_as_box(f"Directory Listing: {display_path}", result)
        self.display(formatted_output, "avm_output")

    def _handle_read_file(self, args: list):
        """
        Handler for the /read command. Now publishes an event for the Code Viewer.
        """
        if not args:
            self.display(format_as_box("Usage Error", "Please provide a file path.\nUsage: /read <path/to/file>"),
                         "avm_error")
            return

        read_file_action = self.foundry.get_action("read_file")
        relative_path = args[0]
        resolved_path = self.project_manager.resolve_path(relative_path)
        content = read_file_action(path=str(resolved_path))

        if content.strip().startswith("Error:"):
            self.display(format_as_box(f"Error reading file", content), "avm_error")
            return

        logger.info(f"Publishing DisplayFileInEditor event for path: {resolved_path}")
        self.event_bus.publish(DisplayFileInEditor(file_path=str(resolved_path), file_content=content))
        self.display(f"Opened `{relative_path}` in Code Viewer.", "system_message")

    def _handle_lint(self, args: list):
        """Handler for the /lint command."""
        if not args:
            self.display(format_as_box("Usage Error", "Please provide a file path.\nUsage: /lint <path/to/file>"),
                         "avm_error")
            return

        lint_action = self.foundry.get_action("lint_file")
        relative_path = args[0]
        resolved_path = self.project_manager.resolve_path(relative_path)
        result = lint_action(path=str(resolved_path))
        formatted_output = format_as_box(f"Lint Report: {relative_path}", result)
        self.display(formatted_output, "avm_output")

    def _handle_index(self):
        """Handler for the /index command to manually trigger project indexing."""
        if not self.project_manager.active_project_path:
            self.display(format_as_box("Error", "No active project. Please create or load a project first."), "avm_error")
            return

        self.display("Starting project re-indexing...", "system_message")
        self.event_bus.publish(DirectToolInvocationRequest(
            tool_id='index_project_context',
            params={'path': str(self.project_manager.active_project_path)}
        ))

    def _handle_help(self):
        """Displays a help message with available commands."""
        help_text = (
            "Aura Direct Commands:\n\n"
            "/help                 - Shows this help message.\n"
            "/index                - Manually re-indexes the entire project for the AI.\n"
            "/list_files [path]    - Lists files in the active project.\n"
            "/read <path>          - Reads a file from the active project into the Code Viewer.\n"
            "/lint <path>          - Lints a Python file in the active project."
        )
        self.display(format_as_box("Aura Help", help_text), "system_message")