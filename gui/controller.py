# gui/controller.py
import logging
import shlex
from typing import Optional, Callable, TYPE_CHECKING, List, Dict, Any

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import QWidget, QLabel, QInputDialog

from core.models.messages import AuraMessage, MessageType
from event_bus import EventBus
from events import (
    UserPromptEntered, UserCommandEntered, PostChatMessage, ToolCallInitiated, ToolCallCompleted, MissionAccomplished
)
from services import MissionLogService, CommandHandler
from .chat_widgets import (
    ToolCallWidget, MissionAccomplishedWidget
)
from .command_input_widget import CommandInputWidget
from .mission_log_window import MissionLogWindow
from .node_viewer_placeholder import NodeViewerWindow
from .widgets.message_renderer_widget import MessageRendererWidget

if TYPE_CHECKING:
    from core.managers import ProjectManager

logger = logging.getLogger(__name__)


class GUIController(QObject):
    """Manages the UI logic, message display, and backend communication."""

    def __init__(self, main_window, event_bus: EventBus, message_renderer: MessageRendererWidget):
        super().__init__()
        self.main_window = main_window
        self.event_bus = event_bus
        self.message_renderer = message_renderer

        # Subscribe to event bus events
        self.event_bus.subscribe("post_chat_message", self.on_post_chat_message)
        self.event_bus.subscribe("post_structured_message", self.on_post_structured_message)
        self.event_bus.subscribe("tool_call_initiated", self.on_tool_call_initiated)
        self.event_bus.subscribe("tool_call_completed", self.on_tool_call_completed)
        self.event_bus.subscribe("mission_accomplished", self.on_mission_accomplished)

        self.project_manager: Optional["ProjectManager"] = None
        self.mission_log_service: Optional[MissionLogService] = None
        self.command_handler: Optional[CommandHandler] = None

        self.node_viewer_window = None
        self.code_viewer_window = None

        self.active_tool_widgets: Dict[int, ToolCallWidget] = {}

        self.command_input: Optional[CommandInputWidget] = None
        self.autocomplete_popup: Optional[QLabel] = None

    def register_ui_elements(self, command_input, autocomplete_popup):
        self.command_input = command_input
        self.autocomplete_popup = autocomplete_popup

    def on_mission_accomplished(self, event: MissionAccomplished):
        widget = MissionAccomplishedWidget()
        self.message_renderer.add_widget(widget)

    def on_tool_call_initiated(self, event: ToolCallInitiated):
        widget = ToolCallWidget(tool_name=event.tool_name, params=event.params)
        self.active_tool_widgets[event.widget_id] = widget
        self.message_renderer.add_widget(widget)

    def on_tool_call_completed(self, event: ToolCallCompleted):
        if event.widget_id in self.active_tool_widgets:
            widget = self.active_tool_widgets.pop(event.widget_id)
            widget.update_status(event.status, event.result)
        else:
            logger.warning(f"Received ToolCallCompleted for unknown widget_id: {event.widget_id}")

    def on_post_chat_message(self, event: PostChatMessage):
        if event.is_error:
            message = AuraMessage.error(event.message)
        else:
            message = AuraMessage.agent_response(event.message)
        self.message_renderer.add_message(message)

    def on_post_structured_message(self, message: AuraMessage):
        self.message_renderer.add_message(message)

    def wire_up_command_handler(self, handler: CommandHandler):
        self.command_handler = handler
        if self.command_input:
            self.command_input.textChanged.connect(self.on_text_changed)

    def set_project_manager(self, pm: "ProjectManager"):
        self.project_manager = pm

    def set_mission_log_service(self, mls: MissionLogService):
        self.mission_log_service = mls

    def submit_input(self):
        if not self.command_input: return
        input_text = self.command_input.toPlainText().strip()
        if not input_text: return

        self.message_renderer.add_message(AuraMessage.user_input(input_text))
        self.command_input.clear()

        if input_text.startswith("/"):
            try:
                parts = shlex.split(input_text[1:])
                command, args = parts[0], parts[1:]
                event = UserCommandEntered(command=command, args=args)
                self.event_bus.emit("user_command_entered", event)
            except Exception as e:
                self.message_renderer.add_message(AuraMessage.error(f"Error parsing command: {e}"))
        else:
            event = UserPromptEntered(
                prompt_text=input_text,
                conversation_history=self.get_conversation_history()
            )
            self.event_bus.emit("user_prompt_entered", event)

    def post_welcome_message(self):
        welcome_msg = """AURA Command Deck Initialized\n\nStatus: READY\nSystem: Online\nMode: Interactive\n\nEnter your commands or describe what you want to build..."""
        self.message_renderer.add_message(AuraMessage.system(welcome_msg))

    def get_conversation_history(self) -> List[Dict[str, Any]]:
        history = []
        for msg in self.message_renderer.get_messages():
            if msg.type in [MessageType.USER_INPUT, MessageType.AGENT_RESPONSE]:
                role = "user" if msg.type == MessageType.USER_INPUT else "model"
                history.append({"role": role, "content": msg.content})
        return history

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
