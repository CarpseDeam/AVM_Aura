# services/executor.py
import logging
import ast
from pathlib import Path
from typing import Callable, Optional, List

from event_bus import EventBus
from events import (
    ActionReadyForExecution, BlueprintInvocation, PauseExecutionForUserInput,
    PlanApproved, ProjectCreated, DisplayFileInEditor, DirectToolInvocationRequest,
    RefreshFileTreeRequest
)
from foundry import FoundryManager
from foundry.blueprints import RawCodeInstruction, UserInputRequest
from .context_manager import ContextManager
from .vector_context_service import VectorContextService
from .project_manager import ProjectManager

logger = logging.getLogger(__name__)


class ExecutorService:
    def __init__(
            self,
            event_bus: EventBus,
            context_manager: ContextManager,
            foundry_manager: FoundryManager,
            vector_context_service: VectorContextService,
            project_manager: ProjectManager,
            display_callback: Optional[Callable[[str, str], None]] = None,
    ):
        self.event_bus = event_bus
        self.context_manager = context_manager
        self.foundry_manager = foundry_manager
        self.vector_context_service = vector_context_service
        self.project_manager = project_manager
        self.display_callback = display_callback
        self.ast_root = ast.Module(body=[], type_ignores=[])

        self.PATH_PARAM_KEYS = {
            'write_file': ['path'], 'read_file': ['path'], 'list_files': ['path'],
            'delete_file': ['path'], 'delete_directory': ['path'], 'lint_file': ['path'],
            'add_import': ['path'], 'add_method_to_class': ['path'], 'get_code_for': ['path'],
            'list_functions_in_file': ['path'], 'index_project_context': ['path'],
            'copy_file': ['source_path', 'destination_path'],
            'move_file': ['source_path', 'destination_path']
        }
        self.FS_MODIFYING_ACTIONS = {'write_file', 'delete_file', 'delete_directory', 'move_file', 'create_directory', 'copy_file'}

        logger.info("ExecutorService initialized with a blank AST root and project awareness.")
        self._register_handlers()

    def _register_handlers(self) -> None:
        self.event_bus.subscribe(ActionReadyForExecution, self._handle_action_ready)
        self.event_bus.subscribe(PlanApproved, self._handle_plan_approved)
        self.event_bus.subscribe(DirectToolInvocationRequest, self._handle_direct_tool_invocation)

    def _display(self, message: str, tag: str) -> None:
        if self.display_callback:
            self.display_callback(message, tag)

    def _resolve_action_paths(self, action_id: str, action_params: dict) -> dict:
        resolved_params = action_params.copy()
        path_keys = self.PATH_PARAM_KEYS.get(action_id, [])
        if 'path' in path_keys and 'path' not in resolved_params:
            resolved_params['path'] = '.'
        for key in path_keys:
            if key in resolved_params and isinstance(resolved_params.get(key), str):
                # For direct invocations, path might already be resolved.
                if not Path(resolved_params[key]).is_absolute():
                     resolved_params[key] = str(self.project_manager.resolve_path(resolved_params[key]))
        return resolved_params

    def _execute_plan(self, plan: List[BlueprintInvocation]) -> None:
        self._display(f"▶️ Executing {len(plan)}-step plan...", "avm_executing")
        for i, step in enumerate(plan):
            self._display(f"--- Step {i + 1}/{len(plan)} ---", "avm_executing")
            if isinstance(step, BlueprintInvocation):
                self._execute_blueprint(step)
            else:
                self._display(f"Error: Plan step {i + 1} is not a valid BlueprintInvocation.", "avm_error")
                break
        self._display("✅ Plan execution complete.", "avm_executing")

    def _execute_blueprint(self, invocation: BlueprintInvocation) -> None:
        blueprint = invocation.blueprint
        action_id = blueprint.id
        self._display(f"▶️ Executing Blueprint: {action_id}", "avm_executing")

        action_function = self.foundry_manager.get_action(blueprint.action_function_name)
        if not action_function:
            self._display(f"Error: Action function '{blueprint.action_function_name}' not found.", "avm_error")
            return

        try:
            resolved_params = self._resolve_action_paths(action_id, invocation.parameters)

            if action_id == "get_generated_code":
                result = action_function(code_ast=self.ast_root)
            elif action_id == "index_project_context":
                result = action_function(vector_context_service=self.vector_context_service, **resolved_params)
            elif action_id == "create_project":
                result = action_function(project_manager=self.project_manager, **resolved_params)
            else:
                result = action_function(**resolved_params)

            if isinstance(result, str):
                self._display(f"✅ Result from {action_id}:\n{result}", "avm_output")
                is_successful_fs_op = "Successfully" in result and action_id in self.FS_MODIFYING_ACTIONS
                if is_successful_fs_op:
                    self.event_bus.publish(RefreshFileTreeRequest())

                if action_id == "create_project" and "Successfully created" in result:
                    project_name = resolved_params['project_name']
                    project_path = str(self.project_manager.active_project_path)
                    self.event_bus.publish(ProjectCreated(project_name=project_name, project_path=project_path))
                elif action_id == "write_file" and "Successfully wrote" in result:
                    file_path = resolved_params.get("path")
                    content = resolved_params.get("content", "")
                    if file_path:
                        self.event_bus.publish(DisplayFileInEditor(file_path=file_path, file_content=content))
                elif action_id == "read_file" and not result.strip().startswith("Error:"):
                    file_path = resolved_params.get("path")
                    if file_path:
                        self.context_manager.add_to_context(key=file_path, content=result)
                        self._display(f"📝 Content of '{Path(file_path).name}' added to context.", "avm_info")

            elif isinstance(result, ast.AST):
                self.ast_root.body.append(result)
            elif isinstance(result, UserInputRequest):
                self.event_bus.publish(PauseExecutionForUserInput(question=result.question))
            else:
                self._display(f"Blueprint '{action_id}' returned an unexpected type: {type(result)}", "avm_error")

        except Exception as e:
            logger.exception("An exception occurred while executing blueprint '%s'.", action_id)
            self._display(f"❌ Error executing Blueprint '{action_id}': {e}", "avm_error")

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
        invocation = BlueprintInvocation(blueprint=blueprint, parameters=event.params)
        self._execute_blueprint(invocation)