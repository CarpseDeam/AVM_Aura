# core/managers/window_manager.py
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer

from core.llm_client import LLMClient
from gui.main_window import AuraMainWindow
from gui.code_viewer import CodeViewerWindow
from gui.model_config_dialog import ModelConfigurationDialog
from gui.log_viewer import LogViewerWindow
from gui.mission_log_window import MissionLogWindow

from event_bus import EventBus
from core.app_state import AppState

if TYPE_CHECKING:
    from core.managers import ProjectManager
    from core.managers.service_manager import ServiceManager


class WindowManager:
    """
    Creates and manages all GUI windows.
    Single responsibility: Window lifecycle and access management.
    """

    def __init__(self, event_bus: EventBus, project_manager: "ProjectManager"):
        self.event_bus = event_bus
        self.project_manager = project_manager
        self.service_manager: "ServiceManager" = None

        # Main windows
        self.main_window: AuraMainWindow = None
        self.code_viewer: CodeViewerWindow = None
        self.log_viewer: LogViewerWindow = None
        self.mission_log_window: MissionLogWindow = None

        # Dialogs
        self.model_config_dialog: ModelConfigurationDialog = None

        print("[WindowManager] Initialized")

    def initialize_windows(self, llm_client: LLMClient, service_manager: "ServiceManager", project_root: Path):
        """Initialize all GUI windows."""
        print("[WindowManager] Initializing windows...")
        self.service_manager = service_manager

        self.main_window = AuraMainWindow(self.event_bus, project_root)
        self.code_viewer = CodeViewerWindow(self.event_bus, self.project_manager)
        self.log_viewer = LogViewerWindow(self.event_bus)
        self.mission_log_window = MissionLogWindow(self.event_bus)

        self.model_config_dialog = ModelConfigurationDialog(llm_client, self.main_window)

        self.event_bus.subscribe("stream_code_chunk", self.handle_code_stream)

        print("[WindowManager] Windows initialized")

    def handle_code_stream(self, filename: str, chunk: str):
        """Handles a stream_code_chunk event by updating the code viewer."""
        if not self.code_viewer:
            return

        # Make sure the code viewer is visible
        if not self.code_viewer.isVisible():
            self.code_viewer.show_window()

        # We need to resolve the path relative to the active project
        full_path_str = filename
        if self.project_manager and self.project_manager.active_project_path:
            full_path_str = str(self.project_manager.active_project_path / filename)

        self.code_viewer.stream_to_tab(full_path_str, chunk)

    def handle_app_state_change(self, new_state: AppState, project_name: str | None):
        """
        Listens for global state changes and updates all relevant UI components.
        """
        self.update_project_display(project_name or "(none)")
        if new_state == AppState.MODIFY:
            if self.project_manager and self.project_manager.active_project_path:
                self.load_project_in_code_viewer(str(self.project_manager.active_project_path))
        else:  # BOOTSTRAP state
            self.prepare_code_viewer_for_new_project()

    # --- Window Getters ---
    def get_main_window(self) -> AuraMainWindow:
        return self.main_window

    def get_code_viewer(self) -> CodeViewerWindow:
        return self.code_viewer

    # --- Show Window Methods ---
    def show_main_window(self):
        if self.main_window: self.main_window.show()

    def show_mission_log(self, event=None):
        """Handles the request to show and position the mission log."""
        if not self.mission_log_window:
            return

        if self.service_manager and self.service_manager.mission_log_service:
            self.service_manager.mission_log_service.load_log_for_active_project()

        self.mission_log_window.show_window()
        # Use a short timer to ensure the main window has been painted before we query its geometry
        QTimer.singleShot(50, self._position_side_windows)

    def _position_side_windows(self):
        """Adjusts the MissionLog window to sit neatly beside the main window."""
        if not self.main_window or not self.main_window.isVisible():
            return

        main_geom = self.main_window.frameGeometry()

        if self.mission_log_window and self.mission_log_window.isVisible():
            self.mission_log_window.move(main_geom.right() + 5, main_geom.top())
            self.mission_log_window.resize(self.mission_log_window.width(), main_geom.height())

    def show_code_viewer(self):
        if self.code_viewer: self.code_viewer.show_window()

    async def show_model_config_dialog(self):
        """Asynchronously populates model data and then shows the dialog."""
        if self.model_config_dialog:
            if self.model_config_dialog.isVisible():
                self.model_config_dialog.activateWindow()
                self.model_config_dialog.raise_()
                return
            await self.model_config_dialog.populate_models_async()
            self.model_config_dialog.populate_settings()
            self.model_config_dialog.show()

    def show_log_viewer(self):
        if self.log_viewer: self.log_viewer.show()

    # --- UI Update Methods ---
    def update_project_display(self, project_name: str):
        if self.main_window and hasattr(self.main_window, 'sidebar'):
            self.main_window.sidebar.update_project_display(project_name)

    def prepare_code_viewer_for_new_project(self):
        if self.code_viewer: self.code_viewer.prepare_for_new_project_session()

    def load_project_in_code_viewer(self, project_path: str):
        if self.code_viewer:
            self.code_viewer.load_project(project_path)

    def is_fully_initialized(self) -> bool:
        return all([self.main_window, self.code_viewer, self.log_viewer])