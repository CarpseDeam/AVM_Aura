# gui/controller.py
import logging
import threading
import shlex
from typing import Optional

from PySide6.QtCore import QObject, Signal, Slot

from event_bus import EventBus
from events import UserPromptEntered, UserCommandEntered, DisplayFileInEditor, ProjectCreated
from services import ProjectManager, MissionLogService

from .code_viewer import CodeViewerWindow
from .node_viewer_placeholder import NodeViewerWindow
from .mission_log_window import MissionLogWindow
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
    def __init__(self, main_window, event_bus: EventBus):
        self.main_window = main_window
        self.event_bus = event_bus
        self.project_manager: Optional[ProjectManager] = None
        self.mission_log_service: Optional[MissionLogService] = None

        self.node_viewer_window = None
        self.code_viewer_window = None
        self.mission_log_window = None

        # UI elements will be registered after they are created
        self.output_log = None
        self.command_input = None
        self.display_bridge = None

        self.event_bus.subscribe(DisplayFileInEditor, self.handle_display_file)
        self.event_bus.subscribe(ProjectCreated, self.on_project_created)

    def register_ui_elements(self, output_log, command_input):
        """Connects the controller to the main window's widgets after they exist."""
        self.output_log = output_log
        self.command_input = command_input
        self.display_bridge = DisplayBridge(self.output_log)

    def set_project_manager(self, pm: ProjectManager):
        self.project_manager = pm

    def set_mission_log_service(self, mls: MissionLogService):
        self.mission_log_service = mls

    def get_display_callback(self):
        return self.display_bridge.message_received.emit

    def submit_input(self):
        input_text = self.command_input.toPlainText().strip()
        if not input_text: return
        self.output_log.append(f"👤 {input_text}")
        self.command_input.clear()
        if input_text.startswith("/"):
            try:
                parts = shlex.split(input_text[1:])
                command, args = parts[0], parts[1:]
                self.event_bus.publish(UserCommandEntered(command=command, args=args))
            except Exception as e:
                self.get_display_callback()(f"Error parsing command: {e}", "avm_error")
        else:
            is_build_mode = self.main_window.is_build_mode()
            if is_build_mode:
                logger.info("Input submitted in 'Build' mode (auto-approve plan).")
            else:
                logger.info("Input submitted in 'Plan' mode (interactive plan approval).")

            event = UserPromptEntered(
                prompt_text=input_text,
                auto_approve_plan=is_build_mode
            )
            threading.Thread(target=self.event_bus.publish, args=(event,),
                             daemon=True).start()

    def post_welcome_message(self):
        banner = get_aura_banner()
        self.output_log.setText(f"{banner}\nSystem online. Waiting for command...")

    @Slot(DisplayFileInEditor)
    def handle_display_file(self, event: DisplayFileInEditor):
        self.toggle_code_viewer()
        if self.code_viewer_window:
            self.code_viewer_window.display_file(path_str=event.file_path, content=event.file_content)

    @Slot(ProjectCreated)
    def on_project_created(self, event: ProjectCreated):
        self.toggle_code_viewer()
        if self.code_viewer_window:
            self.code_viewer_window.load_project(event.project_path)
        if self.mission_log_service:
            self.mission_log_service.load_log_for_active_project()

    def toggle_node_viewer(self):
        if self.node_viewer_window is None or not self.node_viewer_window.isVisible():
            self.node_viewer_window = NodeViewerWindow()
            self.node_viewer_window.show()
        else:
            self.node_viewer_window.activateWindow()

    def toggle_code_viewer(self):
        if self.project_manager is None:
            self.get_display_callback()("Project system is not ready yet.", "avm_error")
            return
        if self.code_viewer_window is None or not self.code_viewer_window.isVisible():
            self.code_viewer_window = CodeViewerWindow(project_manager=self.project_manager, event_bus=self.event_bus)
            self.code_viewer_window.show()
        else:
            self.code_viewer_window.activateWindow()

    def toggle_mission_log(self):
        if self.mission_log_service is None:
            self.get_display_callback()("Mission Log system is not ready yet.", "avm_error")
            return
        if self.mission_log_window is None or not self.mission_log_window.isVisible():
            self.mission_log_window = MissionLogWindow(event_bus=self.event_bus)
            # Trigger an initial load of tasks
            self.mission_log_service.load_log_for_active_project()
        self.mission_log_window.show_window()