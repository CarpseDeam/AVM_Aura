# services/mission_manager.py
import logging
import threading
import time
from typing import Callable

from event_bus import EventBus
from events import MissionDispatchRequest, DirectToolInvocationRequest
from .mission_log_service import MissionLogService
from .project_manager import ProjectManager
from .task_agent import TaskAgent

logger = logging.getLogger(__name__)


class MissionManager:
    """
    Manages the high-level execution of tasks from the Mission Log by dispatching
    individual TaskAgents to handle the TDD loop for each task.
    """

    def __init__(self, event_bus: EventBus, mission_log_service: MissionLogService,
                 project_manager: ProjectManager, display_callback: Callable):
        self.event_bus = event_bus
        self.mission_log_service = mission_log_service
        self.project_manager = project_manager
        self.display_callback = display_callback

        self._is_mission_active = False
        self._mission_thread = None

        self.event_bus.subscribe(MissionDispatchRequest, self.handle_dispatch_request)
        logger.info("MissionManager (Conductor) initialized.")

    def handle_dispatch_request(self, event: MissionDispatchRequest):
        if self._is_mission_active:
            self.display_callback("Mission is already in progress.", "avm_error")
            return

        if not self.project_manager.is_project_active():
            self.display_callback("❌ Cannot dispatch mission. No active project.", "avm_error")
            return

        self._is_mission_active = True
        self.display_callback("🚀 Mission dispatch acknowledged. Beginning autonomous execution...", "system_message")
        self._mission_thread = threading.Thread(target=self._run_mission, daemon=True)
        self._mission_thread.start()

    def _run_mission(self):
        try:
            undone_tasks = [task for task in self.mission_log_service.get_tasks() if not task.get('done', False)]
            if not undone_tasks:
                self.display_callback("Mission log contains no pending tasks.", "system_message")
                return

            self.display_callback(f"Conductor overseeing {len(undone_tasks)} pending tasks.", "avm_info")
            time.sleep(1)

            for task in undone_tasks:
                agent = TaskAgent(
                    task_id=task['id'],
                    task_description=task['description'],
                    event_bus=self.event_bus,
                    display_callback=self.display_callback
                )

                task_successful = agent.execute()

                if task_successful:
                    self.event_bus.publish(
                        DirectToolInvocationRequest('mark_task_as_done', {'task_id': task['id']})
                    )
                else:
                    self.display_callback(
                        f"💔 Conductor halting mission: Agent failed to complete task {task['id']}. "
                        "Please review the log, fix any issues, and dispatch again.",
                        "avm_error"
                    )
                    break

                time.sleep(2)
            else:
                self.display_callback("🎉 All mission tasks completed successfully!", "system_message")

        except Exception as e:
            logger.error(f"A critical error occurred during mission execution: {e}", exc_info=True)
            self.display_callback(f"A critical error occurred in the MissionManager: {e}", "avm_error")
        finally:
            self._is_mission_active = False
            logger.info("Mission finished or aborted. MissionManager is now idle.")