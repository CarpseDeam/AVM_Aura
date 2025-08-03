# gui/controller.py
import logging
import threading
import shlex
from PySide6.QtCore import QObject, Signal, Slot
from event_bus import EventBus
from events import UserPromptEntered, UserCommandEntered

from .node_viewer_placeholder import NodeViewerWindow
from .code_viewer_placeholder import CodeViewerWindow

logger = logging.getLogger(__name__)

# --- NEW: A helper class to bridge threading and PySide6's signal/slot system ---
class DisplayBridge(QObject):
    """
    This class lives in the main GUI thread and receives signals from other
    threads to safely update the UI.
    """
    message_received = Signal(str, str) # Signal to emit with (message, tag)

    def __init__(self, output_log_widget):
        super().__init__()
        self.output_log = output_log_widget
        # Connect the signal to the slot that updates the QTextEdit
        self.message_received.connect(self.append_message)

    @Slot(str, str)
    def append_message(self, message, tag):
        """Safely appends a message to the output log from any thread."""
        # For now, tags aren't used for styling, but we'll keep them for the future.
        # The ASCII boxes are pre-formatted, so we just append.
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

        # --- NEW: The thread-safe way to update the GUI ---
        self.display_bridge = DisplayBridge(self.output_log)

    def get_display_callback(self):
        """Returns the thread-safe callback for the backend services to use."""
        return self.display_bridge.message_received.emit

    def submit_input(self):
        """Handles when the user presses Enter in the command input."""
        input_text = self.command_input.text().strip()
        if not input_text:
            return

        # Display the user's input in the log
        self.output_log.append(f"👤 {input_text}")
        self.command_input.clear()

        # --- NEW: Full command dispatcher logic ---
        if input_text.startswith("/"):
            # This is a direct command, handle it immediately
            try:
                parts = shlex.split(input_text[1:])
                command = parts[0]
                args = parts[1:]
                logger.info(f"Dispatching command: /{command} with args: {args}")
                self.event_bus.publish(UserCommandEntered(command=command, args=args))
            except Exception as e:
                self.get_display_callback()(f"Error parsing command: {e}", "avm_error")
        else:
            # This is a natural language prompt for the LLM
            logger.info("Dispatching prompt to LLM.")
            # We run this in a thread so it doesn't freeze the GUI
            threading.Thread(
                target=self.event_bus.publish,
                args=(UserPromptEntered(prompt_text=input_text),),
                daemon=True
            ).start()

    def post_welcome_message(self):
        """Displays the initial welcome message in the log."""
        welcome_text = (
            "┌─ Welcome to Aura ─────────────────────────┐\n"
            "│                                           │\n"
            "│ System online. Waiting for command...     │\n"
            "└───────────────────────────────────────────┘"
        )
        self.output_log.setText(welcome_text)

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
        """Shows or focuses the Code Viewer window."""
        if self.code_viewer_window is None or not self.code_viewer_window.isVisible():
            logger.info("Launching Code Viewer window...")
            self.code_viewer_window = CodeViewerWindow()
            self.code_viewer_window.show()
        else:
            logger.info("Focusing existing Code Viewer window.")
            self.code_viewer_window.activateWindow()