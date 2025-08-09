import logging
from pathlib import Path
from typing import Optional, Any

from event_bus import EventBus
from foundry import FoundryManager, BlueprintInvocation
from core.project_manager import ProjectManager

logger = logging.getLogger(__name__)


class ToolRunnerService:
    """
    Handles the safe execution of a single BlueprintInvocation.
    It resolves paths and injects context before calling the action function.
    """

    def __init__(
            self,
            event_bus: EventBus,
            foundry_manager: FoundryManager,
            project_manager: ProjectManager,
    ):
        self.event_bus = event_bus
        self.foundry_manager = foundry_manager
        self.project_manager = project_manager
        self.PATH_PARAM_KEYS = ['path', 'source_path', 'destination_path', 'requirements_path']
        logger.info("ToolRunnerService initialized.")

    def run_tool_by_dict(self, tool_call_dict: dict) -> Optional[Any]:
        """Convenience method to run a tool from a dictionary."""
        tool_name = tool_call_dict.get("tool_name")
        blueprint = self.foundry_manager.get_blueprint(tool_name)
        if not blueprint:
            error_msg = f"Error: Blueprint '{tool_name}' not found in Foundry."
            print(error_msg)
            return error_msg

        invocation = BlueprintInvocation(blueprint=blueprint, parameters=tool_call_dict.get('arguments', {}))
        return self.run_tool(invocation)

    def run_tool(self, invocation: BlueprintInvocation) -> Optional[Any]:
        """Executes a single blueprint invocation."""
        blueprint = invocation.blueprint
        action_id = blueprint.id
        print(f"▶️  Executing: {action_id} with params {invocation.parameters}")

        action_function = self.foundry_manager.get_action(blueprint.action_function_name)
        if not action_function:
            error_msg = f"Error: Action function '{blueprint.action_function_name}' not found."
            print(error_msg)
            return error_msg

        try:
            prepared_params = self._prepare_parameters(action_id, invocation.parameters)
            result = action_function(**prepared_params)

            print(f"✅ Result from {action_id}: {result}")
            return result

        except Exception as e:
            logger.exception("An exception occurred while executing blueprint '%s'.", action_id)
            error_msg = f"❌ Error executing Blueprint '{action_id}': {e}"
            print(error_msg)
            return error_msg

    def _prepare_parameters(self, action_id: str, action_params: dict) -> dict:
        """Resolves file paths and injects necessary context."""
        resolved_params = action_params.copy()

        # Inject project manager for tools that need it
        if action_id == 'create_project':
            resolved_params['project_manager'] = self.project_manager
            return resolved_params

        base_path: Optional[Path] = None
        if self.project_manager.is_project_active():
            base_path = self.project_manager.active_project_path

        if base_path:
            for key in self.PATH_PARAM_KEYS:
                if key in resolved_params and isinstance(resolved_params.get(key), str):
                    # This prevents re-resolving an already absolute path
                    if not Path(resolved_params[key]).is_absolute():
                        resolved_params[key] = str((base_path / resolved_params[key]).resolve())

        # Inject execution context for tools that need it (e.g., run_shell_command)
        if self.project_manager.is_venv_active:
            resolved_params['project_context'] = self.project_manager.get_venv_info()

        return resolved_params