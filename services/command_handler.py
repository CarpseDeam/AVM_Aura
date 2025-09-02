# services/command_handler.py
import logging
from typing import Callable, Dict, TYPE_CHECKING, List, Any

from core.models.messages import AuraMessage, MessageType
from events import DisplayFileInEditor, UserPromptEntered, UserCommandEntered, PostChatMessage
from event_bus import EventBus

if TYPE_CHECKING:
    from core.managers import ProjectManager
    from foundry import FoundryManager

logger = logging.getLogger(__name__)


class CommandHandler:
    """
    Handles direct, CLI-style slash commands from the user.
    """

    def __init__(self, foundry_manager: "FoundryManager", event_bus: EventBus,
                 project_manager: "ProjectManager", conversation_history_fetcher: Callable[[], List[Dict[str, Any]]]):
        self.foundry = foundry_manager
        self.event_bus = event_bus
        self.project_manager = project_manager
        self.conversation_history_fetcher = conversation_history_fetcher
        self.last_aura_response = ""

        self.commands = {
            "build": "Sends the last AI response to the main prompt workflow.",
            "help": "Shows the detailed help message.",
            "index": "Re-indexes the project for the AI.",
            "list_files": "Lists files in the active project.",
            "read": "Reads a file into the Code Viewer.",
        }
        logger.info("CommandHandler initialized and ready.")

    def get_available_commands(self) -> Dict[str, str]:
        return self.commands

    def _post_message(self, message: str, msg_type: MessageType = MessageType.SYSTEM):
        self.event_bus.emit("post_structured_message", AuraMessage(content=message, type=msg_type))

    def _update_last_aura_response(self):
        """Scan the conversation history to find the last message from the AI."""
        history = self.conversation_history_fetcher()
        # Iterate in reverse to find the most recent agent response
        for message in reversed(history):
            if message.get("role") == "model":
                self.last_aura_response = message.get("content", "").strip()
                logger.info(f"Captured last Aura response for /build command.")
                return
        self.last_aura_response = ""
        logger.warning("Could not find a previous 'Aura' response to use for /build.")

    def handle(self, event: UserCommandEntered):
        self._update_last_aura_response()

        command = event.command.lower()
        args = event.args
        logger.info(f"Handling command '/{command}' with args: {args}")

        try:
            if command == "build":
                self._handle_build()
            elif command == "list_files":
                self._handle_list_files(args)
            elif command == "read":
                self._handle_read_file(args)
            elif command == "index":
                self._handle_index()
            elif command == "help":
                self._handle_help()
            else:
                self._post_message(f"Unknown command: /{command}\nType /help to see a list of available commands.", MessageType.ERROR)
        except Exception as e:
            error_message = f"An unexpected error occurred while executing '/{command}': {e}"
            logger.error(error_message, exc_info=True)
            self._post_message(error_message, MessageType.ERROR)

    def _handle_build(self):
        if not self.last_aura_response:
            self._post_message("No previous response from Aura to build from.", MessageType.ERROR)
            return

        self._post_message(f"▶️ Sending last prompt to Build Mode...")
        event = UserPromptEntered(
            prompt_text=self.last_aura_response,
            conversation_history=[]  # Start a fresh context for the build
        )
        self.event_bus.emit("user_request_submitted", event)

    def _handle_list_files(self, args: list):
        list_files_action = self.foundry.get_action("list_files")
        relative_path = args[0] if args else "."
        if not self.project_manager.active_project_path:
            self._post_message("No active project.", MessageType.ERROR)
            return
        resolved_path = self.project_manager.active_project_path / relative_path
        result = list_files_action(path=str(resolved_path))
        self._post_message(f"Directory Listing: {resolved_path}\n\n{result}")

    def _handle_read_file(self, args: list):
        if not args:
            self._post_message("Usage: /read <path/to/file>", MessageType.ERROR)
            return
        read_file_action = self.foundry.get_action("read_file")
        relative_path = args[0]
        if not self.project_manager.active_project_path:
            self._post_message("No active project.", MessageType.ERROR)
            return
        resolved_path = self.project_manager.active_project_path / relative_path
        content = read_file_action(path=str(resolved_path))
        if content.strip().startswith("Error:"):
            self._post_message(f"Error reading file: {content}", MessageType.ERROR)
            return
        self.event_bus.emit("display_file_in_editor", DisplayFileInEditor(file_path=str(resolved_path), file_content=content))
        self._post_message(f"Opened `{relative_path}` in Code Viewer.")

    def _handle_index(self):
        if not self.project_manager.active_project_path:
            self._post_message("No active project. Please create or load a project first.", MessageType.ERROR)
            return
        self._post_message("Starting project re-indexing...")
        # This should probably be a direct tool invocation request
        # For now, we assume an event handles this.
        self.event_bus.emit("reindex_project_requested")

    def _handle_help(self):
        help_text = "Aura Direct Commands:\n\n"
        for cmd, desc in self.commands.items():
            help_text += f"/{cmd.ljust(18)} - {desc}\n"
        self._post_message(help_text)
