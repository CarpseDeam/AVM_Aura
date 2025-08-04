# gui/controller.py
import logging
import threading
import shlex
from typing import Optional, Callable

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QLabel

from event_bus import EventBus
from events import UserPromptEntered, UserCommandEntered
from services import ProjectManager, MissionLogService
from .code_viewer import CodeViewerWindow
from .node_viewer_placeholder import NodeViewerWindow
from .mission_log_window import MissionLogWindow
from .utils import get_aura_banner
from .chat_widgets import UserMessageWidget, AIMessageWidget, ThinkingWidget

logger = logging.getLogger(__name__)


class GUIController(QObject):
    """Manages the UI logic, message display, and backend communication."""

    # Signals for thread-safe UI updates
    add_user_message_signal = Signal(str)
    add_ai_message_signal = Signal(str)
    show_thinking_signal = Signal()
    hide_thinking_signal = Signal()
    add_system_message_signal = Signal(str)

    def __init__(self, main_window, event_bus: EventBus, chat_layout: QVBoxLayout, scroll_area: QScrollArea):
        super().__init__()
        self.main_window = main_window
        self.event_bus = event_bus
        self.chat_layout = chat_layout
        self.scroll_area = scroll_area

        self.project_manager: Optional[ProjectManager] = None
        self.mission_log_service: Optional[MissionLogService] = None

        self.node_viewer_window = None
        self.code_viewer_window = None
        self.mission_log_window = None
        self.thinking_widget: Optional[ThinkingWidget] = None

        self.command_input = None

        # Connect signals to their corresponding slots
        self.add_user_message_signal.connect(self._add_user_message)
        self.add_ai_message_signal.connect(self._add_ai_message)
        self.show_thinking_signal.connect(self._show_thinking)
        self.hide_thinking_signal.connect(self._hide_thinking)
        self.add_system_message_signal.connect(self._add_system_message)

        # We no longer subscribe to UI events here; they are handled by the llm_operator/factory

    def register_ui_elements(self, command_input):
        self.command_input = command_input

    def set_project_manager(self, pm: ProjectManager):
        self.project_manager = pm

    def set_mission_log_service(self, mls: MissionLogService):
        self.mission_log_service = mls

    def get_display_callback(self) -> Callable[[str, str], None]:
        """Provides a thread-safe callback for backend services to send messages to the UI."""

        def callback(message: str, tag: str):
            # This function will be called from backend threads
            if tag == "avm_response":
                self.add_ai_message_signal.emit(message)
            else:
                # For simplicity, other tags can be handled as system messages
                # We can differentiate them later if needed
                formatted_message = f"[{tag.replace('_', ' ').upper()}] {message}"
                self.add_system_message_signal.emit(formatted_message)

        return callback

    def submit_input(self):
        input_text = self.command_input.toPlainText().strip()
        if not input_text: return

        self.add_user_message_signal.emit(input_text)
        self.command_input.clear()

        if input_text.startswith("/"):
            self.show_thinking_signal.emit()  # Show thinking for commands too
            try:
                parts = shlex.split(input_text[1:])
                command, args = parts[0], parts[1:]
                self.event_bus.publish(UserCommandEntered(command=command, args=args))
            except Exception as e:
                self.add_system_message_signal.emit(f"Error parsing command: {e}")
            finally:
                self.hide_thinking_signal.emit()
        else:
            self.show_thinking_signal.emit()
            is_build_mode = self.main_window.is_build_mode()

            event = UserPromptEntered(
                prompt_text=input_text,
                auto_approve_plan=is_build_mode
            )
            # Run the LLM call in a separate thread
            threading.Thread(target=self._process_prompt_async, args=(event,), daemon=True).start()

    def _process_prompt_async(self, event: UserPromptEntered):
        """Worker function to handle LLM interaction without blocking the GUI."""
        try:
            self.event_bus.publish(event)
        finally:
            # Ensure the thinking indicator is always hidden after the operation
            self.hide_thinking_signal.emit()

    def post_welcome_message(self):
        """Adds the initial welcome message to the chat."""
        # This is a bit of a hack to show the banner correctly.
        # A proper WelcomeWidget would be better in the future.
        banner_widget = QLabel(f"<pre>{get_aura_banner()}</pre>System online. Waiting for command...")
        banner_widget.setObjectName("WelcomeBanner")
        self._insert_widget(banner_widget)

    @Slot(str)
    def _add_system_message(self, message: str):
        # A simple QLabel for system messages
        widget = QLabel(message)
        widget.setWordWrap(True)
        widget.setObjectName("SystemMessage")
        self._insert_widget(widget)

    @Slot(str)
    def _add_user_message(self, text: str):
        widget = UserMessageWidget(text)
        self._insert_widget(widget)

    @Slot(str)
    def _add_ai_message(self, text: str):
        widget = AIMessageWidget(text)
        self._insert_widget(widget)

    @Slot()
    def _show_thinking(self):
        if self.thinking_widget: return  # Already showing
        self.thinking_widget = ThinkingWidget()
        self._insert_widget(self.thinking_widget)
        self.thinking_widget.start_animation()

    @Slot()
    def _hide_thinking(self):
        if self.thinking_widget:
            self.thinking_widget.stop_animation()
            self.thinking_widget.deleteLater()
            self.thinking_widget = None

    def _insert_widget(self, widget: QWidget):
        """Inserts a widget at the end of the chat layout."""
        # The layout has a stretch at the end, so we insert before it.
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, widget)
        # Ensure the scroll area scrolls to the bottom to show the new widget
        self.scroll_area.verticalScrollBar().setValue(self.scroll_area.verticalScrollBar().maximum())

    def get_full_chat_text(self) -> str:
        """Retrieves all text from the chat log for the /build command."""
        text_parts = []
        for i in range(self.chat_layout.count()):
            widget = self.chat_layout.itemAt(i).widget()
            if isinstance(widget, (UserMessageWidget, AIMessageWidget)):
                text_parts.append(widget.message_label.text())
        return "\n".join(text_parts)

    # --- Window Toggling Methods (no significant changes) ---
    def toggle_node_viewer(self):
        if self.node_viewer_window is None or not self.node_viewer_window.isVisible():
            self.node_viewer_window = NodeViewerWindow()
            self.node_viewer_window.show()
        else:
            self.node_viewer_window.activateWindow()

    def toggle_code_viewer(self):
        if self.project_manager is None:
            self.add_system_message_signal.emit("Project system is not ready yet.")
            return
        if self.code_viewer_window is None or not self.code_viewer_window.isVisible():
            self.code_viewer_window = CodeViewerWindow(project_manager=self.project_manager, event_bus=self.event_bus)
        self.code_viewer_window.show()
        self.code_viewer_window.activateWindow()

    def toggle_mission_log(self):
        if self.mission_log_service is None:
            self.add_system_message_signal.emit("Mission Log system is not ready yet.")
            return
        if self.mission_log_window is None or not self.mission_log_window.isVisible():
            self.mission_log_window = MissionLogWindow(event_bus=self.event_bus)
        self.mission_log_service.load_log_for_active_project()
        self.mission_log_window.show_window()