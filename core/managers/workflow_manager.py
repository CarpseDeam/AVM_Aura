# core/managers/workflow_manager.py
from typing import Optional, Dict

from event_bus import EventBus
from core.app_state import AppState
from core.managers.service_manager import ServiceManager
from core.managers.window_manager import WindowManager
from core.managers.task_manager import TaskManager
from events import UserPromptEntered, PostChatMessage


class WorkflowManager:
    """
    Orchestrates AI workflows based on the authoritative application state.
    """
    MAX_FIX_ATTEMPTS = 2

    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.service_manager: ServiceManager = None
        self.window_manager: WindowManager = None
        self.task_manager: TaskManager = None
        self._last_error_report = None
        self._fix_attempt_count = 0
        print("[WorkflowManager] Initialized")

    def set_managers(self, service_manager: ServiceManager, window_manager: WindowManager, task_manager: TaskManager):
        self.service_manager = service_manager
        self.window_manager = window_manager
        self.task_manager = task_manager
        self.event_bus.subscribe("execution_failed", self.handle_execution_failed)

    def handle_user_request(self, event: UserPromptEntered):
        """
        The central router for all user chat input.
        This workflow always interprets user input as a request to create a high-level plan.
        """
        self._fix_attempt_count = 0
        prompt = event.prompt_text
        if not prompt.strip() and not event.image_bytes:
            return

        dev_team_service = self.service_manager.get_development_team_service()

        # The user's prompt is a direct instruction to have Aura create a plan.
        workflow_coroutine = dev_team_service.run_aura_planner_workflow(
            user_idea=prompt,
            conversation_history=event.conversation_history
        )

        if workflow_coroutine:
            self.task_manager.start_ai_workflow_task(workflow_coroutine)

    def handle_execution_failed(self, error_report: str):
        """
        This is the entry point for the self-correction loop.
        """
        self.event_bus.emit(
            "post_chat_message",
            PostChatMessage(
                sender="Aura",
                message="It looks like the execution failed. Don't worry, I'm starting the self-correction process to analyze and fix the problem.",
                is_error=True
            )
        )
        self._last_error_report = error_report
        self._fix_attempt_count += 1

        self.log("warning", f"Execution failed. Entering self-correction attempt #{self._fix_attempt_count}.")

        if self._fix_attempt_count > self.MAX_FIX_ATTEMPTS:
            self.log("error", "Maximum fix attempts reached. Aborting.")
            self.event_bus.emit("agent_status_changed", "Aura", "Could not fix the error. Aborting.", "fa5s.thumbs-down")
            self.event_bus.emit(
                "post_chat_message",
                PostChatMessage(
                    sender="Aura",
                    message="I've tried my best but was unable to automatically fix the issue. You may need to review the code and logs to resolve this one.",
                    is_error=True
                )
            )
            return

        dev_team_service = self.service_manager.get_development_team_service()
        project_manager = self.service_manager.get_project_manager()

        if not dev_team_service or not project_manager.active_project_path:
            self.log("error", "Cannot attempt fix: Services or active project not available.")
            return

        git_diff = project_manager.get_git_diff()
        full_code_context = project_manager.get_project_files()

        fix_coroutine = dev_team_service.run_review_and_fix_phase(
            error_report=error_report,
            git_diff=git_diff,
            full_code_context=full_code_context
        )
        self.task_manager.start_ai_workflow_task(fix_coroutine)


    def log(self, level, message):
        self.event_bus.emit("log_message_received", "WorkflowManager", level, message)