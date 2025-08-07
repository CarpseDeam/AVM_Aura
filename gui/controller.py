# gui/controller.py
import logging
import threading
import shlex
from typing import Optional, Callable

from PySide6.QtCore import QObject, Signal, Slot, QPoint, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QLabel, QInputDialog

from event_bus import EventBus
from events import (
    UserPromptEntered, UserCommandEntered, DirectToolInvocationRequest, StatusUpdate
)
from services import ProjectManager, MissionLogService, CommandHandler
from .code_viewer import CodeViewerWindow
from .node_viewer_placeholder import NodeViewerWindow
from .mission_log_window import MissionLogWindow
from .status_bar_widget import StatusBarWidget
from .utils import get_aura_banner
from .chat_widgets import UserMessageWidget, AIMessageWidget, ThinkingWidget
from .command_input_widget import CommandInputWidget

logger = logging.getLogger(__name__)


class GUIController(QObject):
    """Manages the UI logic, message display, and backend communication."""

    add_user_message_signal = Signal(str)
    add_ai_message_signal = Signal(str)
    add_system_message_signal = Signal(str)
    update_status_signal = Signal(str, str, bool, object, object)

    def __init__(self, main_window, event_bus: EventBus, chat_layout: QVBoxLayout, scroll_area: QScrollArea):
        super().__init__()
        self.main_window = main_window
        self.event_bus = event_bus
        self.chat_layout = chat_layout
        self.scroll_area = scroll_area

        # Subscribe to the new StatusUpdate event
        self.event_bus.subscribe(StatusUpdate, self.on_status_update)

        self.project_manager: Optional[ProjectManager] = None
        self.mission_log_service: Optional[MissionLogService] = None
        self.command_handler: Optional[CommandHandler] = None

        self.node_viewer_window = None
        self.code_viewer_window = None
        self.mission_log_window = None
        self.status_bar: Optional[StatusBarWidget] = None

        self.command_input: Optional[CommandInputWidget] = None
        self.autocomplete_popup: Optional[QLabel] = None

        self.add_user_message_signal.connect(self._add_user_message)
        self.add_ai_message_signal.connect(self._add_ai_message)
        self.add_system_message_signal.connect(self._add_system_message)
        self.update_status_signal.connect(self._on_update_status)


    def register_ui_elements(self, command_input, autocomplete_popup, status_bar):
        self.command_input = command_input
        self.autocomplete_popup = autocomplete_popup
        self.status_bar = status_bar

    def on_status_update(self, event: StatusUpdate):
        """Event handler that receives status updates from any thread."""
        # Emit the signal to pass the data to the main UI thread safely
        self.update_status_signal.emit(event.status, event.activity, event.animate, event.progress, event.total)

    @Slot(str, str, bool, object, object)
    def _on_update_status(self, status: str, activity: str, animate: bool, progress: Optional[int], total: Optional[int]):
        """This slot is guaranteed to run on the main UI thread."""
        if not self.status_bar:
            return

        # Format a progress string if progress data is available
        progress_text = ""
        if progress is not None and total is not None:
            progress_text = f"[{progress}/{total}] "

        full_activity_text = f"{progress_text}{activity}"
        self.status_bar.show_status(status, full_activity_text, animate)


    def wire_up_command_handler(self, handler: CommandHandler):
        self.command_handler = handler
        if self.command_input:
            self.command_input.textChanged.connect(self.on_text_changed)

    def set_project_manager(self, pm: ProjectManager):
        self.project_manager = pm

    def set_mission_log_service(self, mls: MissionLogService):
        self.mission_log_service = mls

    def get_display_callback(self) -> Callable[[str, str], None]:
        def callback(message: str, tag: str):
            if tag == "avm_response":
                self.add_ai_message_signal.emit(message)
            else:
                formatted_message = f"[{tag.replace('_', ' ').upper()}] {message}"
                self.add_system_message_signal.emit(formatted_message)
        return callback

    def submit_input(self):
        if not self.command_input: return
        input_text = self.command_input.toPlainText().strip()
        if not input_text: return

        self.add_user_message_signal.emit(input_text)
        self.command_input.clear()

        if input_text.startswith("/"):
            try:
                parts = shlex.split(input_text[1:])
                command, args = parts[0], parts[1:]
                self.event_bus.publish(UserCommandEntered(command=command, args=args))
            except Exception as e:
                self.add_system_message_signal.emit(f"Error parsing command: {e}")
        else:
            event = UserPromptEntered(
                prompt_text=input_text,
                auto_approve_plan=False
            )
            # We fire off the event immediately, no need for a separate thread here
            self.event_bus.publish(event)

    def post_welcome_message(self):
        banner_widget = QLabel(f"<pre>{get_aura_banner()}</pre>System online. Waiting for command...")
        banner_widget.setObjectName("WelcomeBanner")
        self._insert_widget(banner_widget)

    @Slot(str)
    def _add_system_message(self, message: str):
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

    def _insert_widget(self, widget: QWidget):
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, widget)
        QTimer.singleShot(0, lambda: self.scroll_area.verticalScrollBar().setValue(self.scroll_area.verticalScrollBar().maximum()))

    def get_full_chat_text(self) -> str:
        text_parts = []
        for i in range(self.chat_layout.count()):
            widget = self.chat_layout.itemAt(i).widget()
            if isinstance(widget, UserMessageWidget):
                text_parts.append(f"User: {widget.message_label.text()}")
            elif isinstance(widget, AIMessageWidget):
                text_parts.append(f"[ Aura ]\n{widget.message_label.text()}")
        return "\n".join(text_parts)

    def on_text_changed(self):
        if not self.command_handler or not self.command_input: return
        text = self.command_input.toPlainText()
        if text.strip() == "/":
            commands = self.command_handler.get_available_commands()
            popup_text = "<b>Available Commands:</b><br>"
            for cmd, desc in commands.items():
                popup_text += f"<b>/{cmd}</b> - {desc}<br>"
            self.autocomplete_popup.setText(popup_text)
            self.reposition_autocomplete_popup()
            self.autocomplete_popup.show()
        else:
            self.autocomplete_popup.hide()

    def reposition_autocomplete_popup(self):
        if not self.autocomplete_popup or not self.command_input or not self.autocomplete_popup.isVisible():
            return
        cursor_rect = self.command_input.cursorRect()
        popup_height = self.autocomplete_popup.sizeHint().height()
        x = cursor_rect.left()
        y = cursor_rect.top() - popup_height
        self.autocomplete_popup.move(x, y)
        self.autocomplete_popup.setFixedWidth(400)

    def handle_new_project_request(self):
        project_name, ok = QInputDialog.getText(
            self.main_window,
            "Create New Project",
            "Enter project name (use filesystem-friendly characters):"
        )
        if ok and project_name:
            logger.info(f"User requested to create a new project: '{project_name}'")
            self.event_bus.publish(DirectToolInvocationRequest(
                tool_id='create_project',
                params={'project_name': project_name}
            ))

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