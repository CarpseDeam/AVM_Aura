# services/executor.py
import logging
import ast
from pathlib import Path
from typing import Callable, Optional, List, Any, Dict

from event_bus import EventBus
from events import (
    ActionReadyForExecution, BlueprintInvocation, PauseExecutionForUserInput,
    PlanApproved, ProjectCreated, DisplayFileInEditor, DirectToolInvocationRequest,
    RefreshFileTreeRequest, AgentTaskCompleted
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
        self.active_agent_task_id: Optional[int] = None

        self.PATH_PARAM_KEYS = [
            'path', 'source_path', 'destination_path', 'requirements_path'
        ]
        self.FS_MODIFYING_ACTIONS = {'write_file', 'delete_file', 'delete_directory', 'move_file', 'create_directory',
                                     'copy_file'}
        self.CONTEXT_AWARE_ACTIONS = {'run_shell_command', 'run_tests', 'pip_install'}

        logger.info("ExecutorService initialized with a blank AST root and project awareness.")
        self._register_handlers()

    def _register_handlers(self) -> None:
        self.event_bus.subscribe(ActionReadyForExecution, self._handle_action_ready)
        self.event_bus.subscribe(PlanApproved, self._handle_plan_approved)
        self.event_bus.subscribe(DirectToolInvocationRequest, self._handle_direct_tool_invocation)
        self.event_bus.subscribe(ProjectCreated, self._handle_project_created)

    def _display(self, message: str, tag: str) -> None:
        if self.display_callback:
            self.display_callback(message, tag)

    def _prepare_parameters(self, action_id: str, action_params: dict) -> dict:
        """Resolves file paths and injects project context for aware tools."""
        resolved_params = action_params.copy()

        # Resolve any path-like parameters to be absolute
        for key in self.PATH_PARAM_KEYS:
            if key in resolved_params and isinstance(resolved_params.get(key), str):
                resolved_params[key] = str(self.project_manager.resolve_path(resolved_params[key]))

        # Inject the project context object for tools that need it
        if action_id in self.CONTEXT_AWARE_ACTIONS:
            resolved_params['project_context'] = self.project_manager.active_project_context

        return resolved_params

    def _execute_plan(self, plan: List[BlueprintInvocation]) -> None:
        self._display(f"▶️ Executing {len(plan)}-step plan...", "avm_executing")
        plan_results: Dict[str, Any] = {"run_tests": None, "file_paths": {}}
        final_result_for_agent = None

        for i, step in enumerate(plan):
            self._display(f"--- Step {i + 1}/{len(plan)} ---", "avm_executing")
            result = self._execute_blueprint(step)
            final_result_for_agent = result

            if isinstance(result, str) and (
                    "Error executing command" in result or "An unexpected error occurred" in result or "Error installing dependencies" in result):
                self._display(f"❌ Step failed. Aborting plan.", "avm_error")
                break

            if self.active_agent_task_id is not None:
                if step.blueprint.id == 'run_tests':
                    plan_results['run_tests'] = result
                elif step.blueprint.id == 'write_file':
                    # ** THE FIX IS HERE **
                    # We need to get the resolved path for the file_paths dictionary
                    prepared_params = self._prepare_parameters(step.blueprint.id, step.parameters)
                    path_str = prepared_params.get("path", "")
                    key = 'test' if 'test' in path_str else 'code'
                    plan_results['file_paths'][key] = self.project_manager.get_relative_path_str(path_str)
        else:
            self._display("✅ Plan execution complete.", "avm_executing")

        if self.active_agent_task_id is not None:
            logger.info(f"Signaling completion for agentic task {self.active_agent_task_id} with results.")
            self.event_bus.publish(AgentTaskCompleted(
                task_id=self.active_agent_task_id,
                result=plan_results.get('run_tests') or final_result_for_agent,
                file_paths=plan_results.get('file_paths', {})
            ))
            self.active_agent_task_id = None

    def _execute_blueprint(self, invocation: BlueprintInvocation) -> Optional[Any]:
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
            elif action_id.startswith(("add_task", "mark_task", "get_mission")):
                prepared_params['mission_log_service'] = self.mission_log_service

            result = action_function(**prepared_params)

            if isinstance(result, str):
                self._display(f"✅ Result from {action_id}:\n{result}", "avm_output")
                if "Successfully" in result and action_id in self.FS_MODIFYING_ACTIONS:
                    self.event_bus.publish(RefreshFileTreeRequest())
                if action_id == "create_project" and "Successfully created" in result:
                    project_name = prepared_params['project_name']
                    project_path = str(self.project_manager.active_project_path)
                    self.project_manager._update_project_context()
                    self.event_bus.publish(ProjectCreated(project_name=project_name, project_path=project_path))
                elif action_id == "run_shell_command" and prepared_params.get('command') == 'python -m venv venv':
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
            elif isinstance(result, ast.AST):
                self.ast_root.body.append(result)
            elif isinstance(result, UserInputRequest):
                self.event_bus.publish(PauseExecutionForUserInput(question=result.question))
            else:
                self._display(f"Blueprint '{action_id}' returned an unexpected type: {type(result)}", "avm_error")

            return result

        except Exception as e:
            logger.exception("An exception occurred while executing blueprint '%s'.", action_id)
            error_msg = f"❌ Error executing Blueprint '{action_id}': {e}"
            self._display(error_msg, "avm_error")
            return error_msg

    def _execute_raw_code(self, instruction: RawCodeInstruction) -> None:
        self._display("▶️ Executing Raw Code... Not yet implemented.", "avm_executing")

    def _handle_action_ready(self, event: ActionReadyForExecution) -> None:
        if event.task_id is not None:
            self.active_agent_task_id = event.task_id
            logger.info(f"Executor is now handling agentic task ID: {self.active_agent_task_id}")

        if isinstance(event.instruction, list):
            self._execute_plan(event.instruction)
        elif isinstance(event.instruction, BlueprintInvocation):
            result = self._execute_blueprint(event.instruction)
            if self.active_agent_task_id is not None:
                self.event_bus.publish(AgentTaskCompleted(task_id=self.active_agent_task_id, result=result))
                self.active_agent_task_id = None
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