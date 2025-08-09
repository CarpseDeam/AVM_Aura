# services/tool_runner_service.py
import logging
import os
from pathlib import Path
from typing import Callable, Optional, Any

from event_bus import EventBus
from events import (
    BlueprintInvocation,
    PauseExecutionForUserInput,
    DisplayFileInEditor, RefreshFileTreeRequest
)
from foundry import FoundryManager
from foundry.blueprints import UserInputRequest
from .context_manager import ContextManager
from .project_manager import ProjectManager
from .project_context import ProjectContext


logger = logging.getLogger(__name__)


class ToolRunnerService:
    """
    Handles the safe execution of a single BlueprintInvocation.
    This is the "Hands" of the execution system. It can operate either
    on the live project directory or within a provided sandbox.
    """

    def __init__(
            self,
            event_bus: EventBus,
            context_manager: ContextManager,
            foundry_manager: FoundryManager,
            project_manager: ProjectManager,
            display_callback: Optional[Callable[[str, str], None]] = None,
    ):
        self.event_bus = event_bus
        self.context_manager = context_manager
        self.foundry_manager = foundry_manager
        self.project_manager = project_manager
        self.display_callback = display_callback

        self.PATH_PARAM_KEYS = [
            'path', 'source_path', 'destination_path', 'requirements_path'
        ]
        self.TRANSACTIONAL_ACTIONS = {
            'write_file', 'copy_file', 'move_file', 'create_directory',
            'add_function_to_file', 'add_method_to_class', 'add_import', 'create_package_init',
            'add_class_to_file', 'append_to_function', 'rename_symbol_in_file',
            'add_decorator_to_function', 'add_attribute_to_init'
        }
        self.FS_MODIFYING_ACTIONS = self.TRANSACTIONAL_ACTIONS.union({
            'delete_file', 'delete_directory'
        })
        self.CONTEXT_AWARE_ACTIONS = {'run_shell_command', 'run_tests', 'pip_install', 'run_with_debugger'}
        logger.info("ToolRunnerService initialized.")

    def _display(self, message: str, tag: str) -> None:
        if self.display_callback:
            self.display_callback(message, tag)

    def _create_sandboxed_project_context(self, sandbox_root: Path) -> ProjectContext:
        """
        Scans a sandbox directory and builds a ProjectContext object for it.
        """
        venv_python = None
        venv_pip = None
        venv_path = sandbox_root / 'venv'

        if venv_path.is_dir():
            if os.name == 'nt':  # Windows
                py_path = venv_path / 'Scripts' / 'python.exe'
                pip_path = venv_path / 'Scripts' / 'pip.exe'
            else:  # Unix-like
                py_path = venv_path / 'bin' / 'python'
                pip_path = venv_path / 'bin' / 'pip'

            if py_path.exists(): venv_python = py_path
            if pip_path.exists(): venv_pip = pip_path

        return ProjectContext(
            project_root=sandbox_root,
            venv_python_path=venv_python,
            venv_pip_path=venv_pip
        )

    def _prepare_parameters(self, action_id: str, action_params: dict, sandbox_path: Optional[Path] = None) -> dict:
        """
        Resolves file paths and injects necessary context, respecting the sandbox.
        """
        resolved_params = action_params.copy()

        if action_id == 'create_project':
            resolved_params['project_manager'] = self.project_manager
            return resolved_params

        base_path: Optional[Path] = None
        current_project_context: Optional[ProjectContext] = None

        if sandbox_path:
            base_path = sandbox_path
            current_project_context = self._create_sandboxed_project_context(sandbox_path)
            logger.debug(f"Operating in sandbox. Base path: {base_path}")
        elif self.project_manager.is_project_active():
            base_path = self.project_manager.active_project_path
            current_project_context = self.project_manager.active_project_context
            logger.debug(f"Operating in live project. Base path: {base_path}")
        else:
            # This case handles actions like list_files run before a project exists.
            # It will likely fail if a path needs resolving, which is correct behavior.
            pass

        if base_path:
            for key in self.PATH_PARAM_KEYS:
                if key in resolved_params and isinstance(resolved_params.get(key), str):
                    resolved_params[key] = str((base_path / resolved_params[key]).resolve())

        if action_id in self.CONTEXT_AWARE_ACTIONS:
            if not current_project_context:
                raise RuntimeError(f"Action '{action_id}' requires an active project context, but none was found.")
            resolved_params['project_context'] = current_project_context

        if action_id == 'create_new_tool':
            resolved_params['event_bus'] = self.event_bus

        return resolved_params

    def run_tool(self, invocation: BlueprintInvocation, sandbox_path: Optional[Path] = None) -> Optional[Any]:
        """
        Executes a single blueprint invocation, potentially inside a sandbox.
        """
        blueprint = invocation.blueprint
        action_id = blueprint.id
        exec_env = f"in sandbox '{sandbox_path.name}'" if sandbox_path else "on live project"
        self._display(f"▶️ Executing: {action_id} ({exec_env})", "avm_executing")

        action_function = self.foundry_manager.get_action(blueprint.action_function_name)
        if not action_function:
            error_msg = f"Error: Action function '{blueprint.action_function_name}' not found."
            self._display(error_msg, "avm_error")
            return error_msg

        try:
            prepared_params = self._prepare_parameters(action_id, invocation.parameters, sandbox_path)
            result = action_function(**prepared_params)

            self._handle_post_execution(action_id, result, prepared_params, invocation)

            return result

        except Exception as e:
            logger.exception("An exception occurred while executing blueprint '%s'.", action_id)
            error_msg = f"❌ Error executing Blueprint '{action_id}': {e}"
            self._display(error_msg, "avm_error")
            return error_msg

    def _handle_post_execution(self, action_id: str, result: Any, prepared_params: dict,
                               invocation: BlueprintInvocation) -> None:
        """Handles the result of a tool execution, displaying output and firing events."""
        if isinstance(result, str):
            if "Error" in result or "failed" in result:
                self._display(f"❌ Result from {action_id}:\n{result}", "avm_error")
            else:
                self._display(f"✅ Result from {action_id}:\n{result}", "avm_output")

            if "Successfully" in result and action_id in self.FS_MODIFYING_ACTIONS:
                self.event_bus.publish(RefreshFileTreeRequest())

            # ProjectCreated event is now published by the ProjectManager itself
            # This simplifies the logic here.

            elif action_id == "run_shell_command" and 'venv' in invocation.parameters.get('command', ''):
                self.project_manager._update_project_context()

            elif action_id == "pip_install" and "Successfully installed" in result:
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