# gui/controller.py
import logging
import threading
import shlex
from PySide6.QtCore import QObject, Signal, Slot
from event_bus import EventBus
from events import UserPromptEntered, UserCommandEntered

from .node_viewer_placeholder import NodeViewerWindow
from .code_viewer_placeholder import CodeViewerWindow
from .utils import get_aura_banner

logger = logging.getLogger(__name__)

class DisplayBridge(QObject):
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
        self.command_input = main_window.command_input # This is now a QTextEdit
        self.node_viewer_window = None
        self.code_viewer_window = None
        self.display_bridge = DisplayBridge(self.output_log)

    def get_display_callback(self):
        return self.display_bridge.message_received.emit

    def submit_input(self):
        """Handles when the user clicks the Send button or presses a shortcut."""
        # --- MODIFIED: Use toPlainText() for QTextEdit ---
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

    def toggle_node_viewer(self):
        if self.node_viewer_window is None or not self.node_viewer_window.isVisible():
            self.node_viewer_window = NodeViewerWindow()
            self.node_viewer_window.show()
        else:
            self.node_viewer_window.activateWindow()

    def toggle_code_viewer(self):
        if self.code_viewer_window is None or not self.code_viewer_window.isVisible():
            self.code_viewer_window = CodeViewerWindow()
            self.code_viewer_window.show()
        else:
            self.code_viewer_window.activateWindow()