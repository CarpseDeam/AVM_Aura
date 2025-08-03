# gui/controller.py
import logging
import threading
import shlex
from PySide6.QtCore import QObject, Signal, Slot

from event_bus import EventBus
from events import UserPromptEntered, UserCommandEntered, DisplayFileInEditor

from .code_viewer import CodeViewerWindow
from .node_viewer_placeholder import NodeViewerWindow
from .utils import get_aura_banner

logger = logging.getLogger(__name__)


class DisplayBridge(QObject):
    """
    This class lives in the main GUI thread and receives signals from other
    threads to safely update the UI.
    """
    message_received = Signal(str, str)  # Signal to emit with (message, tag)

    def __init__(self, output_log_widget):
        super().__init__()
        self.output_log = output_log_widget
        # Connect the signal to the slot that updates the QTextEdit
        self.message_received.connect(self.append_message)

    @Slot(str, str)
    def append_message(self, message, tag):
        """Safely appends a message to the output log from any thread."""
        self.output_log.append(message)
        self.output_log.ensureCursorVisible()


class GUIController:
    """Manages the logic and state for the Aura Command Deck."""

    def __init__(self, main_window, event_bus: EventBus):
        self.main_window = main_window
        self.event_bus = event_bus
        self.output_log = main_window.output_log
        self.command_input = main_window.command_input

        # State to track open windows
        self.node_viewer_window = None
        self.code_viewer_window = None

        self.display_bridge = DisplayBridge(self.output_log)

        # Subscribe to the event from the command handler
        # We need to use a lambda to pass the event object to the slot
        self.event_bus.subscribe(DisplayFileInEditor, lambda event: self.handle_display_file(event))

    def get_display_callback(self):
        """Returns the thread-safe callback for the backend services to use."""
        return self.display_bridge.message_received.emit

    def submit_input(self):
        """Handles when the user clicks the Send button or presses a shortcut."""
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
        """Displays the initial welcome message in the log."""
        banner = get_aura_banner()
        welcome_text = (
            f"{banner}\n"
            "System online. Waiting for command..."
        )
        self.output_log.setText(welcome_text)

    @Slot(DisplayFileInEditor)
    def handle_display_file(self, event: DisplayFileInEditor):
        """Receives file data and tells the Code Viewer to display it."""
        logger.info(f"Controller received request to display file: {event.file_path}")
        # Ensure the viewer is open
        self.toggle_code_viewer()
        # Call the viewer's public method to show the content
        if self.code_viewer_window:
            self.code_viewer_window.display_file(
                path_str=event.file_path,
                content=event.file_content
            )

    def toggle_node_viewer(self):
        """Shows or focuses the Node Viewer window."""
        if self.node_viewer_window is None or not self.node_viewer_window.isVisible():
            logger.info("Launching Node Viewer window...")
            self.node_viewer_window = NodeViewerWindow()
            self.node_viewer_window.show()
        else:
            logger.info("Focusing existing Node Viewer window.")
            self.node_viewer_window.activateWindow()

    def toggle_code_viewer(self):
        """Shows or focuses the REAL Code Viewer window."""
        if self.code_viewer_window is None or not self.code_viewer_window.isVisible():
            logger.info("Launching REAL Code Viewer window...")
            self.code_viewer_window = CodeViewerWindow()
            self.code_viewer_window.show()
        else:
            logger.info("Focusing existing Code Viewer window.")
            self.code_viewer_window.activateWindow()