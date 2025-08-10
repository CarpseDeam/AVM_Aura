# gui/controller.py
import logging
import shlex
from idlelib import history
from typing import Optional, Callable, TYPE_CHECKING, List, Dict, Any

from PySide6.QtCore import QObject, Signal, Slot, QPoint, QTimer, Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QLabel, QInputDialog

from event_bus import EventBus
from events import (
    UserPromptEntered, UserCommandEntered, PlanReadyForReview, AIWorkflowFinished, PostChatMessage,
    ToolCallInitiated, ToolCallCompleted, MissionAccomplished, SystemAlertTriggered
)
from services import MissionLogService, CommandHandler
from .code_viewer import CodeViewerWindow
from .node_viewer_placeholder import NodeViewerWindow
from .mission_log_window import MissionLogWindow
from .utils import get_aura_banner
from .chat_widgets import (
    UserMessageWidget, AIMessageWidget, AgentActivityWidget, ToolCallWidget, BootSequenceWidget,
    MissionAccomplishedWidget, SystemAlertWidget
)
from .command_input_widget import CommandInputWidget
from services import view_formatter

if TYPE_CHECKING:
    from core.managers import ProjectManager

logger = logging.getLogger(__name__)


class GUIController(QObject):
    """Manages the UI logic, message display, and backend communication."""

    add_user_message_signal = Signal(str)
    add_ai_message_signal = Signal(str, str)
    add_system_message_signal = Signal(str)
    update_status_signal = Signal(str, str, bool, object, object)

    def __init__(self, main_window, event_bus: EventBus, chat_layout: QVBoxLayout, scroll_area: QScrollArea):
        super().__init__()
        self.main_window = main_window
        self.event_bus = event_bus
        self.chat_layout = chat_layout
        self.scroll_area = scroll_area

        self.event_bus.subscribe("agent_status_changed", self.on_status_update)
        self.event_bus.subscribe("post_chat_message", self.on_post_chat_message)
        self.event_bus.subscribe("ai_workflow_finished", self._on_workflow_finished)
        self.event_bus.subscribe("plan_ready_for_review", self._on_workflow_finished)
        self.event_bus.subscribe("tool_call_initiated", self.on_tool_call_initiated)
        self.event_bus.subscribe("tool_call_completed", self.on_tool_call_completed)
        self.event_bus.subscribe("mission_accomplished", self.on_mission_accomplished)
        self.event_bus.subscribe("system_alert_triggered", self.on_system_alert_triggered)

        self.project_manager: Optional["ProjectManager"] = None
        self.mission_log_service: Optional[MissionLogService] = None
        self.command_handler: Optional[CommandHandler] = None

        self.node_viewer_window = None
        self.code_viewer_window = None

        self.current_activity_widget: Optional[AgentActivityWidget] = None
        self.active_tool_widgets: Dict[int, ToolCallWidget] = {}

        self.command_input: Optional[CommandInputWidget] = None
        self.autocomplete_popup: Optional[QLabel] = None

        self.add_user_message_signal.connect(self._add_user_message)
        self.add_ai_message_signal.connect(self._add_ai_message)
        self.add_system_message_signal.connect(self._add_system_message)
        self.update_status_signal.connect(self._on_update_status)

    def register_ui_elements(self, command_input, autocomplete_popup):
        self.command_input = command_input
        self.autocomplete_popup = autocomplete_popup

    def on_system_alert_triggered(self, event: SystemAlertTriggered):
        self._on_workflow_finished()
        widget = SystemAlertWidget()
        self._insert_widget(widget)

    def on_mission_accomplished(self, event: MissionAccomplished):
        self._on_workflow_finished()
        widget = MissionAccomplishedWidget()
        self._insert_widget(widget)

    def on_tool_call_initiated(self, event: ToolCallInitiated):
        self._on_workflow_finished()  # Finalize previous agent activity widget
        widget = ToolCallWidget(tool_name=event.tool_name, params=event.params)
        self.active_tool_widgets[event.widget_id] = widget
        self._insert_widget(widget)

    def on_tool_call_completed(self, event: ToolCallCompleted):
        if event.widget_id in self.active_tool_widgets:
            widget = self.active_tool_widgets.pop(event.widget_id)
            widget.update_status(event.status, event.result)
        else:
            logger.warning(f"Received ToolCallCompleted for unknown widget_id: {event.widget_id}")

    def on_post_chat_message(self, event: PostChatMessage):
        """Event handler to post a message from a service to the chat."""
        self.add_ai_message_signal.emit(event.message, event.sender)

    def on_status_update(self, agent_name: str, status_text: str, icon_name: str):
        """Event handler that receives status updates from any thread."""
        animate = "..." in status_text
        self.update_status_signal.emit(agent_name, status_text, animate, None, None)

    @Slot(str, str, bool, object, object)
    def _on_update_status(self, status: str, activity: str, animate: bool, progress: Optional[int],
                          total: Optional[int]):
        """This slot is guaranteed to run on the main UI thread."""
        art_map = {
            "AURA":      {"logo": "( O )", "name": "AURA"},
            "CONDUCTOR": {"logo": "⚙",     "name": "CONDUCTOR"},
            "CODER":     {"logo": "< >",   "name": "CODER"},
            "TESTER":    {"logo": "✓",     "name": "TESTER"},
            "REVIEWER":  {"logo": "⚲",     "name": "REVIEWER"},
            "ARCHITECT": {"logo": "¶",     "name": "ARCHITECT"},
            "FINALIZER": {"logo": "§",     "name": "FINALIZER"},
        }
        default_art = {"logo": "*", "name": "SYSTEM"}

        agent_name_key = status.upper().split(" ")[0]
        agent_art = art_map.get(agent_name_key, default_art)

        if not self.current_activity_widget:
            self.current_activity_widget = AgentActivityWidget()
            self._insert_widget(self.current_activity_widget)

        self.current_activity_widget.set_agent_status(
            logo=agent_art["logo"],
            agent_name=agent_art["name"],
            activity=activity
        )

    def wire_up_command_handler(self, handler: CommandHandler):
        self.command_handler = handler
        if self.command_input:
            self.command_input.textChanged.connect(self.on_text_changed)

    def set_project_manager(self, pm: "ProjectManager"):
        self.project_manager = pm

    def set_mission_log_service(self, mls: MissionLogService):
        self.mission_log_service = mls

    def get_display_callback(self) -> Callable[[str, str], None]:
        def callback(message: str, tag: str):
            if tag == "avm_response":
                self.add_ai_message_signal.emit(message, "Aura")
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

        # Finalize any previous widget before starting a new one
        self._on_workflow_finished()
        self.current_activity_widget = AgentActivityWidget()
        self.current_activity_widget.start_pulsing("Aura is processing your request...")
        self._insert_widget(self.current_activity_widget)

        if input_text.startswith("/"):
            try:
                parts = shlex.split(input_text[1:])
                command, args = parts[0], parts[1:]
                event = UserCommandEntered(command=command, args=args)
                self.event_bus.emit("user_command_entered", event)
            except Exception as e:
                self.add_system_message_signal.emit(f"Error parsing command: {e}")
        else:
            event = UserPromptEntered(
                prompt_text=input_text,
                conversation_history=self.get_conversation_history()
            )
            self.event_bus.emit("user_request_submitted", event)

    def post_welcome_message(self):
        boot_widget = BootSequenceWidget()
        # Add the widget with explicit left alignment to override layout centering.
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, boot_widget, 0, Qt.AlignmentFlag.AlignLeft)
        QTimer.singleShot(0, lambda: self.scroll_area.ensureWidgetVisible(boot_widget))


    @Slot()
    def _on_workflow_finished(self, event=None):
        """
        Handles the completion of any AI workflow.
        Stops all animations and updates the status bar to show the app is idle or waiting.
        """
        if self.current_activity_widget:
            self.current_activity_widget.stop_animation()
            self.current_activity_widget = None

    @Slot(str)
    def _add_system_message(self, message: str):
        self._on_workflow_finished()
        widget = QLabel(message)
        widget.setWordWrap(True)
        widget.setObjectName("SystemMessage")
        self._insert_widget(widget)

    @Slot(str)
    def _add_user_message(self, text: str):
        widget = UserMessageWidget(text)
        self._insert_widget(widget)

    @Slot(str, str)
    def _add_ai_message(self, text: str, author: str):
        self._on_workflow_finished()
        widget = AIMessageWidget(text, author=author)
        self._insert_widget(widget)

    def _insert_widget(self, widget: QWidget):
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, widget)
        QTimer.singleShot(0, lambda: self.scroll_area.ensureWidgetVisible(widget))

    def get_conversation_history(self) -> List[Dict[str, Any]]:
        history = []
        for i in range(self.chat_layout.count()):
            widget = self.chat_layout.itemAt(i).widget()
            if isinstance(widget, UserMessageWidget):
                history.append({"role": "user", "content": widget.message_label.text()})
            elif isinstance(widget, AIMessageWidget):
                history.append({"role": "model", "content": widget.message_label.text()})
        return history

    def get_full_chat_text(self) -> str:
        text_parts = []
        for i in range(self.chat_layout.count()):
            widget = self.chat_layout.itemAt(i).widget()
            if isinstance(widget, UserMessageWidget):
                text_parts.append(f"User: {widget.message_label.text()}")
            elif isinstance(widget, AIMessageWidget):
                history.append({"role": "model", "parts": [widget.message_label.text()]})
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
            self.event_bus.emit("new_project_requested", project_name)

    def handle_load_project_request(self):
        logger.info("User requested to load a project.")
        self.event_bus.emit("load_project_requested")

    def toggle_node_viewer(self):
        if self.node_viewer_window is None or not self.node_viewer_window.isVisible():
            self.node_viewer_window = NodeViewerWindow()
            self.node_viewer_window.show()
        else:
            self.node_viewer_window.activateWindow()

    def toggle_code_viewer(self):
        self.event_bus.emit("open_code_viewer_requested")

    def toggle_mission_log(self):
        self.event_bus.emit("show_mission_log_requested")