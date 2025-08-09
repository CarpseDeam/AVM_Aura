# core/managers/workflow_manager.py
from typing import Optional, Dict

from event_bus import EventBus
from core.app_state import AppState
from core.interaction_mode import InteractionMode
from core.managers.service_manager import ServiceManager
from core.managers.window_manager import WindowManager
from core.managers.task_manager import TaskManager
from events import UserPromptEntered


class WorkflowManager:
    """
    Orchestrates AI workflows based on the authoritative application state.
    """

    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.service_manager: ServiceManager = None
        self.window_manager: WindowManager = None
        self.task_manager: TaskManager = None
        self._last_error_report = None
        print("[WorkflowManager] Initialized")

    def set_managers(self, service_manager: ServiceManager, window_manager: WindowManager, task_manager: TaskManager):
        self.service_manager = service_manager
        self.window_manager = window_manager
        self.task_manager = task_manager
        self.event_bus.subscribe("execution_failed", self.handle_execution_failed)

    def handle_user_request(self, event: UserPromptEntered):
        """The central router for all user chat input."""
        # Unpack from event
        prompt = event.prompt_text
        conversation_history = event.conversation_history
        image_bytes = event.image_bytes
        image_media_type = event.image_media_type
        code_context = event.code_context

        stripped_prompt = prompt.strip()
        if not stripped_prompt and not image_bytes and not code_context:
            return

        app_state_service = self.service_manager.app_state_service
        interaction_mode = app_state_service.get_interaction_mode()
        app_state = app_state_service.get_app_state()

        dev_team_service = self.service_manager.get_development_team_service()

        workflow_coroutine = None
        if interaction_mode == InteractionMode.PLAN:
            workflow_coroutine = dev_team_service.run_chat_workflow(prompt, conversation_history, image_bytes,
                                                                    image_media_type)
        elif interaction_mode == InteractionMode.BUILD:
            if app_state == AppState.BOOTSTRAP:
                workflow_coroutine = dev_team_service.run_build_workflow(prompt, existing_files=None)
            elif app_state == AppState.MODIFY:
                existing_files = self.service_manager.project_manager.get_project_files()
                workflow_coroutine = dev_team_service.run_build_workflow(prompt, existing_files)

        if workflow_coroutine:
            self.task_manager.start_ai_workflow_task(workflow_coroutine)

    def handle_execution_failed(self, error_report: str):
        self._last_error_report = error_report
        # The GUI will listen for this and show the button
        # self.window_manager.get_code_viewer().show_fix_button()

    def log(self, level, message):
        self.event_bus.emit("log_message_received", "WorkflowManager", level, message)