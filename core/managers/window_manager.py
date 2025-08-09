# core/managers/window_manager.py
from pathlib import Path
from typing import TYPE_CHECKING
from gui.main_window import AuraMainWindow
from gui.code_viewer import CodeViewerWindow
from gui.model_config_dialog import ModelConfigurationDialog
from gui.log_viewer import LogViewerWindow

from event_bus import EventBus
from core.llm_client import LLMClient
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

        # Main windows
        self.main_window: AuraMainWindow = None
        self.code_viewer: CodeViewerWindow = None
        self.log_viewer: LogViewerWindow = None

        # Dialogs
        self.model_config_dialog: ModelConfigurationDialog = None

        print("[WindowManager] Initialized")

    def initialize_windows(self, llm_client: LLMClient, service_manager: "ServiceManager", project_root: Path):
        """Initialize all GUI windows."""
        print("[WindowManager] Initializing windows...")

        self.main_window = AuraMainWindow(self.event_bus, project_root)
        self.code_viewer = CodeViewerWindow(self.event_bus, self.project_manager)
        self.log_viewer = LogViewerWindow(self.event_bus)

        self.model_config_dialog = ModelConfigurationDialog(llm_client, self.main_window)

        print("[WindowManager] Windows initialized")

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