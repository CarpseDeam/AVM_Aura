import asyncio
from event_bus import EventBus
from core.managers.service_manager import ServiceManager
from core.managers.window_manager import WindowManager
from core.managers.task_manager import TaskManager
from core.managers.workflow_manager import WorkflowManager


class EventCoordinator:
    """
    Coordinates events between different components of the application.
    """

    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.service_manager: ServiceManager = None
        self.window_manager: WindowManager = None
        self.task_manager: TaskManager = None
        self.workflow_manager: WorkflowManager = None
        print("[EventCoordinator] Initialized")

    def set_managers(self, service_manager: ServiceManager, window_manager: WindowManager, task_manager: TaskManager,
                     workflow_manager: WorkflowManager):
        self.service_manager = service_manager
        self.window_manager = window_manager
        self.task_manager = task_manager
        self.workflow_manager = workflow_manager

    def wire_all_events(self):
        """Wire all events between components."""
        print("[EventCoordinator] Wiring all events...")
        self._wire_ui_events()
        self._wire_ai_workflow_events()
        self._wire_execution_events()
        self._wire_plugin_events()
        self._wire_chat_session_events()
        self._wire_status_bar_events()
        self._wire_lsp_events()
        print("[EventCoordinator] All events wired successfully.")

    def _wire_lsp_events(self):
        if not self.window_manager: return
        code_viewer = self.window_manager.get_code_viewer()
        if not code_viewer or not hasattr(code_viewer, 'editor_manager'): return

        editor_manager = code_viewer.editor_manager
        self.event_bus.subscribe("lsp_diagnostics_received", editor_manager.handle_diagnostics)
        print("[EventCoordinator] LSP events wired.")

    def _wire_status_bar_events(self):
        if not self.window_manager: return
        main_window = self.window_manager.get_main_window()
        if not main_window: return

        status_bar = main_window.statusBar()
        if status_bar and hasattr(status_bar, 'update_agent_status'):
            self.event_bus.subscribe("agent_status_changed", status_bar.update_agent_status)
        else:
            print("[EventCoordinator] Warning: StatusBar not found or is missing 'update_agent_status' method.")

    def _wire_chat_session_events(self):
        # This can be implemented later if needed
        pass

    def _wire_ui_events(self):
        action_service = self.service_manager.action_service
        if action_service:
            self.event_bus.subscribe("new_project_requested", action_service.handle_new_project)
            self.event_bus.subscribe("load_project_requested", action_service.handle_load_project)
            self.event_bus.subscribe("new_session_requested", action_service.handle_new_session)

        app_state_service = self.service_manager.app_state_service
        if app_state_service:
            self.event_bus.subscribe("interaction_mode_change_requested", app_state_service.set_interaction_mode)

        if self.window_manager:
            self.event_bus.subscribe("app_state_changed", self.window_manager.handle_app_state_change)

        self.event_bus.subscribe(
            "configure_models_requested",
            lambda: asyncio.create_task(self.window_manager.show_model_config_dialog())
        )

        rag_manager = self.service_manager.rag_manager
        if rag_manager:
            self.event_bus.subscribe("add_knowledge_requested", rag_manager.open_add_knowledge_dialog)
            self.event_bus.subscribe("add_active_project_to_rag_requested", rag_manager.ingest_active_project)
            self.event_bus.subscribe("add_global_knowledge_requested", rag_manager.open_add_global_knowledge_dialog)

        self.event_bus.subscribe("plugin_management_requested", self.window_manager.show_plugin_management_dialog)

        self.event_bus.subscribe("show_log_viewer_requested", self.window_manager.show_log_viewer)

    def _wire_ai_workflow_events(self):
        if self.workflow_manager:
            self.event_bus.subscribe("user_request_submitted", self.workflow_manager.handle_user_request)

        conductor_service = self.service_manager.conductor_service
        if conductor_service:
            self.event_bus.subscribe("mission_dispatch_requested", conductor_service.execute_mission_in_background)

    def _wire_execution_events(self):
        # Handled by services directly
        pass

    def _wire_plugin_events(self):
        # Can be implemented later
        pass