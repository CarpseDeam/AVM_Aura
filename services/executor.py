# services/executor.py
import logging
import ast
from pathlib import Path
from typing import Callable, Optional, List, Any, Dict
import threading

from event_bus import EventBus
from events import (
    ActionReadyForExecution, BlueprintInvocation, PauseExecutionForUserInput,
    PlanApproved, ProjectCreated, DisplayFileInEditor, DirectToolInvocationRequest,
    RefreshFileTreeRequest, MissionDispatchRequest
)
from foundry import FoundryManager
from foundry.blueprints import RawCodeInstruction, UserInputRequest
from .context_manager import ContextManager
from .vector_context_service import VectorContextService
from .project_manager import ProjectManager
from .mission_log_service import MissionLogService

logger = logging.getLogger(__name__)


class ExecutorService:
    def __init__(
            self,
            event_bus: EventBus,
            context_manager: ContextManager,
            foundry_manager: FoundryManager,
            vector_context_service: VectorContextService,
            project_manager: ProjectManager,
            mission_log_service: MissionLogService,
            display_callback: Optional[Callable[[str, str], None]] = None,
    ):
        self.event_bus = event_bus
        self.context_manager = context_manager
        self.foundry_manager = foundry_manager
        self.vector_context_service = vector_context_service
        self.project_manager = project_manager
        self.mission_log_service = mission_log_service
        self.display_callback = display_callback
        self.ast_root = ast.Module(body=[], type_ignores=[])

        self.is_mission_active = False

        self.PATH_PARAM_KEYS = [
            'path', 'source_path', 'destination_path', 'requirements_path'
        ]
        self.FS_MODIFYING_ACTIONS = {'write_file', 'delete_file', 'delete_directory', 'move_file', 'create_directory',
                                     'copy_file'}
        self.CONTEXT_AWARE_ACTIONS = {'run_shell_command', 'run_tests', 'pip_install', 'run_with_debugger'}

        logger.info("ExecutorService initialized.")
        self._register_handlers()

    def _register_handlers(self) -> None:
        self.event_bus.subscribe(ActionReadyForExecution, self._handle_action_ready)
        self.event_bus.subscribe(PlanApproved, self._handle_plan_approved)
        self.event_bus.subscribe(DirectToolInvocationRequest, self._handle_direct_tool_invocation)
        self.event_bus.subscribe(ProjectCreated, self._handle_project_created)
        self.event_bus.subscribe(MissionDispatchRequest, self._handle_mission_dispatch)

    def _display(self, message: str, tag: str) -> None:
        if self.display_callback:
            self.display_callback(message, tag)

    def _prepare_parameters(self, action_id: str, action_params: dict) -> dict:
        """Resolves file paths and injects project context for aware tools."""
        resolved_params = action_params.copy()

        for key in self.PATH_PARAM_KEYS:
            if key in resolved_params and isinstance(resolved_params.get(key), str):
                resolved_params[key] = str(self.project_manager.resolve_path(resolved_params[key]))

        if action_id in self.CONTEXT_AWARE_ACTIONS:
            resolved_params['project_context'] = self.project_manager.active_project_context

        if action_id.startswith(("add_task", "mark_task", "get_mission")):
            resolved_params['mission_log_service'] = self.mission_log_service

        if action_id == 'create_new_tool':
            resolved_params['event_bus'] = self.event_bus

        return resolved_params

    def _execute_plan(self, plan: List[BlueprintInvocation]) -> None:
        """Executes a list of blueprint invocations (a plan)."""
        self._display(f"▶️ Executing {len(plan)}-step plan...", "avm_executing")
        for i, step in enumerate(plan):
            self._display(f"--- Step {i + 1}/{len(plan)} ---", "avm_executing")
            result = self._execute_blueprint(step)

            if isinstance(result, str) and ("Error" in result or "failed" in result):
                self._display(f"❌ Step failed. Aborting plan.", "avm_error")
                return  # Stop execution on failure

        self._display("✅ Plan execution complete.", "avm_executing")

    def _execute_blueprint(self, invocation: BlueprintInvocation) -> Optional[Any]:
        """Executes a single blueprint invocation."""
        blueprint = invocation.blueprint
        action_id = blueprint.id
        self._display(f"▶️ Executing Blueprint: {action_id}", "avm_executing")

        action_function = self.foundry_manager.get_action(blueprint.action_function_name)
        if not action_function:
            error_msg = f"Error: Action function '{blueprint.action_function_name}' not found."
            self._display(error_msg, "avm_error")
            return error_msg

        try:
            prepared_params = self._prepare_parameters(action_id, invocation.parameters)

            if action_id == "index_project_context":
                prepared_params['vector_context_service'] = self.vector_context_service
            elif action_id == "create_project":
                prepared_params['project_manager'] = self.project_manager

            result = action_function(**prepared_params)

            if isinstance(result, str):
                self.display_callback(f"✅ Result from {action_id}:\n{result}", "avm_output")
                if "Successfully" in result and action_id in self.FS_MODIFYING_ACTIONS:
                    self.event_bus.publish(RefreshFileTreeRequest())
                if action_id == "create_project" and "Successfully created" in result:
                    project_name = prepared_params['project_name']
                    project_path = str(self.project_manager.active_project_path)
                    self.project_manager._update_project_context()
                    self.event_bus.publish(ProjectCreated(project_name=project_name, project_path=project_path))
                elif action_id == "run_shell_command" and 'venv' in prepared_params.get('command', ''):
                    self.project_manager._update_project_context()
                elif action_id == "write_file" and "Successfully wrote" in result:
                    file_path = prepared_params.get("path")
                    content = prepared_params.get("content", "")
                    if file_path:
                        self.event_bus.publish(DisplayFileInEditor(file_path=file_path, file_content=content))
                elif action_id == "read_file" and not result.strip().startswith("Error:"):
                    file_path = prepared_params.get("path")
                    if file_path:
                        self.context_manager.add_to_context(key=file_path, content=result)
                        self._display(f"📝 Content of '{Path(file_path).name}' added to context.", "avm_info")
            elif isinstance(result, UserInputRequest):
                self.event_bus.publish(PauseExecutionForUserInput(question=result.question))
            elif result is not None:
                self._display(f"Blueprint '{action_id}' returned an object of type: {type(result)}", "avm_info")

            return result

        except Exception as e:
            logger.exception("An exception occurred while executing blueprint '%s'.", action_id)
            error_msg = f"❌ Error executing Blueprint '{action_id}': {e}"
            self._display(error_msg, "avm_error")
            return error_msg

    def _execute_raw_code(self, instruction: RawCodeInstruction) -> None:
        self._display("▶️ Executing Raw Code... Not yet implemented.", "avm_executing")

    def _handle_action_ready(self, event: ActionReadyForExecution) -> None:
        if isinstance(event.instruction, list):
            self._execute_plan(event.instruction)
        elif isinstance(event.instruction, BlueprintInvocation):
            self._execute_blueprint(event.instruction)
        elif isinstance(event.instruction, RawCodeInstruction):
            self._execute_raw_code(event.instruction)
        else:
            self._display("Error: Unknown instruction type received for execution.", "avm_error")

    def _handle_plan_approved(self, event: PlanApproved) -> None:
        logger.info(f"Received approved plan with {len(event.plan)} steps. Starting execution.")
        self._display("✅ Plan approved by user. Executing now...", "system_message")
        self._execute_plan(event.plan)

    def _handle_direct_tool_invocation(self, event: DirectToolInvocationRequest):
        logger.info(f"Handling direct tool invocation for '{event.tool_id}'")
        blueprint = self.foundry_manager.get_blueprint(event.tool_id)
        if not blueprint:
            self._display(f"Error: Could not find tool '{event.tool_id}' for direct invocation.", "avm_error")
            return
        self._execute_blueprint(BlueprintInvocation(blueprint=blueprint, parameters=event.params))

    def _handle_project_created(self, event: ProjectCreated):
        logger.info(f"ProjectCreated event caught. Automatically indexing '{event.project_path}'.")
        self._display(f"🚀 Project '{event.project_name}' created. Starting initial codebase indexing...",
                      "system_message")
        self.event_bus.publish(DirectToolInvocationRequest(tool_id='index_project_context', params={
            'path': str(self.project_manager.active_project_path)}))

    def _run_mission_thread(self):
        """The actual mission execution logic that runs in a thread."""
        try:
            tasks = self.mission_log_service.get_tasks()
            pending_tasks = [t for t in tasks if not t.get('done')]

            self._display(f"🚀 Mission dispatch acknowledged. Executing {len(pending_tasks)} tasks...", "system_message")

            for task in pending_tasks:
                tool_call_dict = task.get("tool_call")
                if not tool_call_dict:
                    self._display(
                        f"⚠️ Skipping task {task['id']} ('{task['description']}') as it has no executable tool call.",
                        "avm_warning")
                    continue

                self._display(f"--- Executing Task {task['id']}: {task['description']} ---", "avm_executing")

                blueprint = self.foundry_manager.get_blueprint(tool_call_dict['tool_name'])
                if not blueprint:
                    self._display(
                        f"❌ Aborting mission: Could not find blueprint for tool '{tool_call_dict['tool_name']}'.",
                        "avm_error")
                    return

                invocation = BlueprintInvocation(blueprint=blueprint, parameters=tool_call_dict.get('arguments', {}))
                result = self._execute_blueprint(invocation)

                if isinstance(result, str) and ("Error" in result or "failed" in result):
                    self._display(f"❌ Task {task['id']} failed. Aborting mission.", "avm_error")
                    return
                else:
                    # Mark task as done
                    self.event_bus.publish(
                        DirectToolInvocationRequest(tool_id='mark_task_as_done', params={'task_id': task['id']}))

            self._display("🎉 All mission tasks completed successfully!", "system_message")

        except Exception as e:
            logger.error(f"A critical error occurred during mission execution: {e}", exc_info=True)
            self._display(f"A critical error occurred during the mission: {e}", "avm_error")
        finally:
            self.is_mission_active = False
            logger.info("Mission finished or aborted. Executor is now idle.")

    def _handle_mission_dispatch(self, event: MissionDispatchRequest):
        if self.is_mission_active:
            self._display("Mission is already in progress.", "avm_error")
            return

        self.is_mission_active = True
        mission_thread = threading.Thread(target=self._run_mission_thread, daemon=True)
        mission_thread.start()