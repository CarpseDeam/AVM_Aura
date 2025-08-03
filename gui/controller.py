# gui/controller.py
import logging
import threading
import shlex
from PySide6.QtCore import QObject, Signal, Slot

from event_bus import EventBus
from events import UserPromptEntered, UserCommandEntered, DisplayFileInEditor, ProjectCreated
from services import ProjectManager

from .code_viewer import CodeViewerWindow
from .node_viewer_placeholder import NodeViewerWindow
from .utils import get_aura_banner

logger = logging.getLogger(__name__)


class DisplayBridge(QObject):
    """
    This class lives in the main GUI thread and receives signals from other
    threads to safely update the UI.
    """
    message_received = Signal(str, str)

    def __init__(self, output_log_widget):
        super().__init__()
        self.output_log = output_log_widget
        self.message_received.connect(self.append_message)

    @Slot(str, str)
    def append_message(self, message, tag):
        self.output_log.append(message)
        self.output_log.ensureCursorVisible()


class GUIController:
    """Manages the logic and state for the Aura Command Deck."""

    def __init__(self, main_window, event_bus: EventBus):
        self.main_window = main_window
        self.event_bus = event_bus
        self.output_log = main_window.output_log
        self.command_input = main_window.command_input
        self.project_manager: Optional[ProjectManager] = None

        self.node_viewer_window = None
        self.code_viewer_window = None
        self.display_bridge = DisplayBridge(self.output_log)

        self.event_bus.subscribe(DisplayFileInEditor, lambda event: self.handle_display_file(event))
        self.event_bus.subscribe(ProjectCreated, lambda event: self.on_project_created(event))

    def set_project_manager(self, pm: ProjectManager):
        """Receives the project manager instance from the backend setup."""
        self.project_manager = pm
        logger.info("GUIController has received the ProjectManager instance.")

    def get_display_callback(self):
        return self.display_bridge.message_received.emit

    def submit_input(self):
        input_text = self.command_input.toPlainText().strip()
        if not input_text:
            return

        self.output_log.append(f"👤 {input_text}")
        self.command_input.clear()

        if input_text.startswith("/"):
            try:
                parts = shlex.split(input_text[1:])
                command = parts[0]
                args = parts[1:]
                logger.info(f"Dispatching command: /{command} with args: {args}")
                self.event_bus.publish(UserCommandEntered(command=command, args=args))
            except Exception as e:
                self.get_display_callback()(f"Error parsing command: {e}", "avm_error")
        else:
            logger.info("Dispatching prompt to LLM.")
            threading.Thread(
                target=self.event_bus.publish,
                args=(UserPromptEntered(prompt_text=input_text),),
                daemon=True
            ).start()

    def post_welcome_message(self):
        banner = get_aura_banner()
        welcome_text = (
            f"{banner}\n"
            "System online. Waiting for command..."
        )
        self.output_log.setText(welcome_text)

    @Slot(DisplayFileInEditor)
    def handle_display_file(self, event: DisplayFileInEditor):
        logger.info(f"Controller received request to display file: {event.file_path}")
        self.toggle_code_viewer()
        if self.code_viewer_window:
            self.code_viewer_window.display_file(
                path_str=event.file_path,
                content=event.file_content
            )

    @Slot(ProjectCreated)
    def on_project_created(self, event: ProjectCreated):
        """When a project is created, tell the code viewer to load its file tree."""
        logger.info(f"Controller received ProjectCreated event for '{event.project_name}'")
        self.toggle_code_viewer()
        if self.code_viewer_window:
            # This needs to be thread-safe, let's assume direct call is fine for now
            # as Qt signals are queued across threads. But a dedicated signal might be better.
            self.code_viewer_window.load_project(event.project_path)

    def toggle_node_viewer(self):
        if self.node_viewer_window is None or not self.node_viewer_window.isVisible():
            logger.info("Launching Node Viewer window...")
            self.node_viewer_window = NodeViewerWindow()
            self.node_viewer_window.show()
        else:
            logger.info("Focusing existing Node Viewer window.")
            self.node_viewer_window.activateWindow()

    def toggle_code_viewer(self):
        if self.project_manager is None:
            self.get_display_callback()("Project system is not ready yet. Please wait a moment.", "avm_error")
            return

        if self.code_viewer_window is None or not self.code_viewer_window.isVisible():
            logger.info("Launching REAL Code Viewer window...")
            self.code_viewer_window = CodeViewerWindow(project_manager=self.project_manager)
            self.code_viewer_window.show()
        else:
            logger.info("Focusing existing Code Viewer window.")
            self.code_viewer_window.activateWindow()