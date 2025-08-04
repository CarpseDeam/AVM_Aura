# services/mission_manager.py
import logging
import threading
import time
from typing import Callable, Optional

from event_bus import EventBus
from events import MissionDispatchRequest, UserPromptEntered, AgentTaskCompleted, DirectToolInvocationRequest
from .mission_log_service import MissionLogService

logger = logging.getLogger(__name__)


class MissionManager:
    """
    Manages the autonomous execution of tasks from the Mission Log.
    """

    def __init__(self, event_bus: EventBus, mission_log_service: MissionLogService, display_callback: Callable):
        self.event_bus = event_bus
        self.mission_log_service = mission_log_service
        self.display_callback = display_callback

        self._is_mission_active = False
        self._mission_thread = None
        self._current_task_id = None
        self._task_completion_event = threading.Event()

        self.event_bus.subscribe(MissionDispatchRequest, self.handle_dispatch_request)
        self.event_bus.subscribe(AgentTaskCompleted, self.handle_task_completed)
        logger.info("MissionManager initialized.")

    def handle_dispatch_request(self, event: MissionDispatchRequest):
        """Starts the mission if one is not already active."""
        if self._is_mission_active:
            self.display_callback("Mission is already in progress.", "avm_error")
            logger.warning("Mission dispatch requested, but a mission is already active.")
            return

        self._is_mission_active = True
        self.display_callback("🚀 Mission dispatch acknowledged. Beginning autonomous execution...", "system_message")

        # Run the main mission loop in a separate thread to avoid blocking the GUI
        self._mission_thread = threading.Thread(target=self._run_mission, daemon=True)
        self._mission_thread.start()

    def handle_task_completed(self, event: AgentTaskCompleted):
        """Signals that the currently executing agentic task has finished."""
        if self._is_mission_active and event.task_id == self._current_task_id:
            logger.info(f"Received completion signal for task {event.task_id}. Unblocking mission loop.")
            self._task_completion_event.set()

    def _run_mission(self):
        """The main autonomous loop that executes tasks from the mission log."""
        try:
            tasks = self.mission_log_service.get_tasks()
            undone_tasks = [task for task in tasks if not task.get('done', False)]

            if not undone_tasks:
                self.display_callback("Mission log contains no pending tasks.", "system_message")
                return

            self.display_callback(f"Found {len(undone_tasks)} pending tasks in the mission log.", "avm_info")
            time.sleep(1)

            for task in undone_tasks:
                self._current_task_id = task['id']
                description = task['description']
                self.display_callback(f"▶️ Starting task {self._current_task_id}: {description}", "avm_executing")

                # Construct the prompt for the LLM
                prompt = (
                    f"My current high-level objective is: '{description}'. "
                    "Analyze this objective and formulate a precise, step-by-step plan to accomplish it using the available tools. "
                    "Then, execute that plan."
                )

                # Clear the event and dispatch the task
                self._task_completion_event.clear()
                self.event_bus.publish(
                    UserPromptEntered(
                        prompt_text=prompt,
                        auto_approve_plan=True,  # Ensure it runs in 'build' mode
                        task_id=self._current_task_id
                    )
                )

                # Wait here until the task is marked as complete by the executor
                logger.info(f"Mission loop is now waiting for task {self._current_task_id} to complete...")
                completed = self._task_completion_event.wait(timeout=600)  # 10-minute timeout per task

                if not completed:
                    self.display_callback(f"❌ Task {self._current_task_id} timed out. Aborting mission.", "avm_error")
                    logger.error(f"Timeout waiting for task {self._current_task_id} to complete.")
                    break  # Abort mission on timeout

                # Mark the task as done in the UI
                self.event_bus.publish(
                    DirectToolInvocationRequest('mark_task_as_done', {'task_id': self._current_task_id}))
                self.display_callback(f"✅ Task {self._current_task_id} completed successfully.", "avm_executing")
                time.sleep(2)  # A brief pause for readability

            self.display_callback("🎉 All mission tasks completed!", "system_message")

        except Exception as e:
            logger.error(f"An unexpected error occurred during mission execution: {e}", exc_info=True)
            self.display_callback(f"A critical error occurred in the mission loop: {e}", "avm_error")
        finally:
            self._is_mission_active = False
            self._current_task_id = None
            logger.info("Mission finished or aborted. MissionManager is now idle.")