# services/mission_manager.py
import logging
import threading
import time
from typing import Callable, Optional

from event_bus import EventBus
from events import MissionDispatchRequest, DirectToolInvocationRequest, UserPromptEntered, AgentTaskCompleted
from .mission_log_service import MissionLogService
from .project_manager import ProjectManager
from .task_agent import TaskAgent
from .prompt_engine import PromptEngine

logger = logging.getLogger(__name__)


class MissionManager:
    """
    Manages the high-level execution of tasks from the Mission Log by dispatching
    individual TaskAgents and maintaining context throughout the mission.
    """

    def __init__(self, event_bus: EventBus, mission_log_service: MissionLogService,
                 project_manager: ProjectManager, display_callback: Callable,
                 prompt_engine: PromptEngine):
        self.event_bus = event_bus
        self.mission_log_service = mission_log_service
        self.project_manager = project_manager
        self.display_callback = display_callback
        self.prompt_engine = prompt_engine

        self._is_mission_active = False
        self._mission_thread = None
        self._last_user_prompt: str = ""

        self.event_bus.subscribe(MissionDispatchRequest, self.handle_dispatch_request)
        self.event_bus.subscribe(UserPromptEntered, self.handle_user_prompt)
        logger.info("MissionManager (Conductor) initialized.")

    def handle_user_prompt(self, event: UserPromptEntered):
        if event.task_id is None:
            self._last_user_prompt = event.prompt_text
            logger.info(f"Captured user prompt for potential mission goal: '{self._last_user_prompt[:100]}...'")

    def handle_dispatch_request(self, event: MissionDispatchRequest):
        if self._is_mission_active:
            self.display_callback("Mission is already in progress.", "avm_error")
            return

        overall_goal = self._last_user_prompt
        pending_tasks = [task for task in self.mission_log_service.get_tasks() if not task.get('done', False)]

        if not pending_tasks:
            self.display_callback("Mission log has no pending tasks. Nothing to dispatch.", "avm_warning")
            return

        if not overall_goal:
            logger.info("No Architect goal set. Using a generic goal based on mission log.")
            overall_goal = "Complete the tasks in the mission log to build the desired application."

        if not self.project_manager.is_project_active():
            self.display_callback("❌ Cannot dispatch mission. No active project.", "avm_error")
            return

        self._is_mission_active = True
        self.display_callback(f"🚀 Mission dispatch acknowledged. Goal: {overall_goal[:100]}...", "system_message")
        self._mission_thread = threading.Thread(target=self._run_mission, args=(overall_goal,), daemon=True)
        self._mission_thread.start()

    def _run_mission(self, overall_goal: str):
        try:
            while self._is_mission_active:
                undone_tasks = [task for task in self.mission_log_service.get_tasks() if not task.get('done', False)]
                if not undone_tasks:
                    break

                current_task = undone_tasks[0]

                agent = TaskAgent(
                    task_id=current_task['id'],
                    description=current_task['description'],
                    event_bus=self.event_bus,
                    display_callback=self.display_callback,
                    prompt_engine=self.prompt_engine
                )

                newly_generated_code_paths = agent.execute(overall_goal)

                if newly_generated_code_paths:
                    self.display_callback(f"Indexing new code from task {current_task['id']}...", "avm_info")
                    # The agent now returns absolute paths, which is what the indexer needs
                    for file_path in newly_generated_code_paths.values():
                        self.event_bus.publish(DirectToolInvocationRequest(
                            tool_id='index_project_context',
                            params={'path': file_path}
                        ))
                    time.sleep(1)

                    self.event_bus.publish(
                        DirectToolInvocationRequest('mark_task_as_done', {'task_id': current_task['id']})
                    )
                else:
                    self.display_callback(
                        f"💔 Conductor halting mission: Agent failed to complete task {current_task['id']}.",
                        "avm_error"
                    )
                    self._is_mission_active = False
                    return

                time.sleep(2)

            self.display_callback("🎉 All mission tasks completed successfully!", "system_message")
        except Exception as e:
            logger.error(f"A critical error occurred during mission execution: {e}", exc_info=True)
            self.display_callback(f"A critical error occurred in the MissionManager: {e}", "avm_error")
        finally:
            self._is_mission_active = False
            logger.info("Mission finished or aborted. MissionManager is now idle.")