# services/conductor_service.py
import logging
import threading
import json
from typing import Callable, Optional
from pathlib import Path

from event_bus import EventBus
from events import (
    BlueprintInvocation, StatusUpdate, UserPromptEntered, DirectToolInvocationRequest, RefreshFileTreeRequest
)
from foundry import FoundryManager
from .mission_log_service import MissionLogService
from .tool_runner_service import ToolRunnerService
from .sandbox_manager import SandboxManager
from .project_manager import ProjectManager

logger = logging.getLogger(__name__)


class ConductorService:
    """
    Orchestrates the execution of multi-step missions from the Mission Log
    inside a secure, transactional sandbox environment.
    """

    def __init__(
            self,
            event_bus: EventBus,
            foundry_manager: FoundryManager,
            mission_log_service: MissionLogService,
            tool_runner_service: ToolRunnerService,
            project_manager: ProjectManager,
            display_callback: Optional[Callable[[str, str], None]] = None,
    ):
        self.event_bus = event_bus
        self.foundry_manager = foundry_manager
        self.mission_log_service = mission_log_service
        self.tool_runner_service = tool_runner_service
        self.project_manager = project_manager
        self.display_callback = display_callback
        self.is_mission_active = False
        logger.info("ConductorService initialized.")

    def _display(self, message: str, tag: str) -> None:
        if self.display_callback:
            self.display_callback(message, tag)

    def _initiate_self_correction(self, failed_invocation: BlueprintInvocation, error_report: any) -> None:
        """
        Formats a context-rich prompt to fix a failure and starts the self-correction loop.
        """
        self.event_bus.publish(
            StatusUpdate("SELF-CORRECTION", "Error detected. Analyzing context to formulate a fix.", True))

        failed_tool_name = failed_invocation.blueprint.id
        failed_tool_args = failed_invocation.parameters

        # --- NEW: Context Injection Logic ---
        context_files = {}
        try:
            if self.project_manager.is_project_active():
                project_root = self.project_manager.active_project_path
                # Add context based on which tool failed
                if failed_tool_name in ['run_tests', 'run_with_debugger']:
                    # For test failures, grab all python files.
                    for py_file in project_root.rglob('*.py'):
                        relative_path = py_file.relative_to(project_root)
                        context_files[str(relative_path)] = py_file.read_text(encoding='utf-8')
                elif failed_tool_name == 'pip_install':
                    # For pip failures, the requirements file is key.
                    req_path = project_root / 'requirements.txt'
                    if req_path.exists():
                        context_files['requirements.txt'] = req_path.read_text(encoding='utf-8')

                # You could add more rules here for other tools as needed
        except Exception as e:
            logger.error(f"Error gathering context for self-correction: {e}")

        context_str = "\n\n".join(
            [f"--- Contents of `{path}` ---\n```\n{content}\n```" for path, content in context_files.items()]
        )

        error_context_str = json.dumps(error_report, indent=2) if isinstance(error_report, dict) else str(error_report)

        # --- FIX --- Add a more forceful instruction to the self-correction prompt.
        correction_prompt = f"""
Failure Report:
An attempt to execute the tool '{failed_tool_name}' with the arguments {json.dumps(failed_tool_args)} has failed.

--- ERROR CONTEXT ---
{error_context_str}
--- END ERROR CONTEXT ---

{context_str}

Your task is to analyze this failure and the relevant code context.
CRITICAL INSTRUCTION: The file paths listed in the ERROR CONTEXT (especially in the traceback or stack trace) are the source of the error. You MUST use these exact file paths in your plan. Do NOT invent or assume different file paths.

Create a new step-by-step plan to fix this bug. The plan must be comprehensive. For example, if a dependency is missing, you must modify the requirements file AND install it.
The plan must end with a step to verify the fix (e.g., by re-running the test that failed).
"""
        logger.info(f"Initiating self-correction with context-rich prompt:\n{correction_prompt}")

        self.event_bus.publish(
            UserPromptEntered(prompt_text=correction_prompt, auto_approve_plan=True)
        )

    def execute_mission_in_background(self):
        """Starts the mission execution in a new thread to avoid blocking the GUI."""
        if self.is_mission_active:
            self._display("Mission is already in progress.", "avm_error")
            return

        self.is_mission_active = True
        mission_thread = threading.Thread(target=self.execute_mission, daemon=True)
        mission_thread.start()

    def execute_mission(self):
        """The main logic for running a mission from the Mission Log."""
        if not self.project_manager.is_project_active():
            self._display("❌ Cannot start mission: No active project.", "avm_error")
            self.is_mission_active = False
            return

        sandbox_manager = None
        try:
            # --- FIX: Load all pending tasks into a local queue at the start ---
            all_tasks = self.mission_log_service.get_tasks()
            mission_task_queue = [t for t in all_tasks if not t.get('done')]
            mission_total_tasks = len(mission_task_queue)

            if mission_total_tasks == 0:
                self._display("✅ Mission Log is empty. Nothing to execute.", "system_message")
                return

            self._display(f"🚀 Mission dispatch acknowledged. Executing {mission_total_tasks} tasks...",
                          "system_message")
            self.event_bus.publish(
                StatusUpdate("EXECUTING", f"Mission started with {mission_total_tasks} tasks", True, progress=0,
                             total=mission_total_tasks))

            completed_in_run = 0
            # --- FIX: Loop over the local queue, not by polling the service ---
            while mission_task_queue:
                task = mission_task_queue.pop(0)
                completed_in_run += 1

                # Use the active project path at the time the step is executed
                current_project_path = self.project_manager.active_project_path
                if not current_project_path:
                    raise RuntimeError("Mission task requires an active project, but none is set.")

                sandbox_manager = SandboxManager(project_path=current_project_path)
                sandbox_path = sandbox_manager.create()
                self._display(f"--- Executing Task {completed_in_run}/{mission_total_tasks}: {task['description']} ---",
                              "avm_executing")
                self.event_bus.publish(
                    StatusUpdate("EXECUTING", f"Task: {task['description']}", True, progress=completed_in_run,
                                 total=mission_total_tasks))

                tool_call_dict = task.get("tool_call")
                if not tool_call_dict:
                    self._display(
                        f"⚠️ Skipping task {task['id']} ('{task['description']}') as it has no executable tool call.",
                        "avm_warning")
                    self.mission_log_service.mark_task_as_done(task['id'])
                    sandbox_manager.cleanup()
                    continue

                blueprint = self.foundry_manager.get_blueprint(tool_call_dict['tool_name'])
                if not blueprint:
                    raise RuntimeError(
                        f"Aborting mission: Could not find blueprint for tool '{tool_call_dict['tool_name']}'.")

                invocation = BlueprintInvocation(blueprint=blueprint, parameters=tool_call_dict.get('arguments', {}))
                result = self.tool_runner_service.run_tool(invocation, sandbox_path=sandbox_path)

                is_failure = (isinstance(result, str) and ("Error" in result or "failed" in result)) or \
                             (isinstance(result, dict) and result.get("status") in ["failure", "error"])

                if is_failure:
                    self.mission_log_service.clear_pending_tasks()
                    self._initiate_self_correction(invocation, result)
                    raise RuntimeError(f"Task {task['id']} failed. Self-correction initiated.")
                else:
                    self._display(f"✅ Step successful. Committing changes...", "avm_info")
                    sandbox_manager.commit()
                    self.mission_log_service.mark_task_as_done(task['id'])
                    self.event_bus.publish(RefreshFileTreeRequest())
                    sandbox_manager.cleanup()
                    sandbox_manager = None

            # This part is now reached only when the local queue is empty
            self._display("🎉 Mission Accomplished! All tasks completed successfully.", "system_message")


        except Exception as e:
            logger.error(f"A critical error occurred during mission execution: {e}", exc_info=True)
            self._display(f"❌ Mission aborted due to an error: {e}", "avm_error")
        finally:
            if sandbox_manager:
                sandbox_manager.cleanup()
            self.is_mission_active = False
            self.event_bus.publish(StatusUpdate("IDLE", "Ready for input.", False))
            logger.info("Mission finished or aborted. Conductor is now idle.")