import logging
from pathlib import Path
from typing import Optional, Any, TYPE_CHECKING
import inspect
import asyncio

from event_bus import EventBus
from foundry import FoundryManager, BlueprintInvocation
from services.mission_log_service import MissionLogService
from services.vector_context_service import VectorContextService
from events import ToolCallInitiated, ToolCallCompleted

if TYPE_CHECKING:
    from core.managers import ProjectManager, ProjectContext
    from core.llm_client import LLMClient
    from services.development_team_service import DevelopmentTeamService

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
            project_manager: "ProjectManager",
            mission_log_service: MissionLogService,
            vector_context_service: Optional[VectorContextService] = None,
            development_team_service: Optional["DevelopmentTeamService"] = None,
            llm_client: Optional["LLMClient"] = None
    ):
        self.event_bus = event_bus
        self.foundry_manager = foundry_manager
        self.project_manager = project_manager
        self.mission_log_service = mission_log_service
        self.vector_context_service = vector_context_service
        self.development_team_service = development_team_service
        self.llm_client = llm_client

        self.PATH_PARAM_KEYS = ['path', 'source_path', 'destination_path', 'requirements_path']
        logger.info("ToolRunnerService initialized.")

    def _get_service_map(self):
        """
        Dynamically creates the service map to ensure it always has the latest
        service instances, especially after a project change.
        """
        return {
            'project_manager': self.project_manager,
            'mission_log_service': self.mission_log_service,
            'vector_context_service': self.vector_context_service,
            'development_team_service': self.development_team_service,
            'llm_client': self.llm_client,
            'event_bus': self.event_bus,
        }

    async def run_tool_by_dict(self, tool_call_dict: dict) -> Optional[Any]:
        """Convenience method to run a tool from a dictionary."""
        tool_name = tool_call_dict.get("tool_name")
        blueprint = self.foundry_manager.get_blueprint(tool_name)
        if not blueprint:
            error_msg = f"Error: Blueprint '{tool_name}' not found in Foundry."
            print(error_msg)
            return error_msg

        invocation = BlueprintInvocation(blueprint=blueprint, parameters=tool_call_dict.get('arguments', {}))
        return await self.run_tool(invocation)

    async def run_tool(self, invocation: BlueprintInvocation) -> Optional[Any]:
        """Executes a single blueprint invocation."""
        blueprint = invocation.blueprint
        action_id = blueprint.id
        print(f"▶️  Executing: {action_id} with params {invocation.parameters}")

        action_function = self.foundry_manager.get_action(blueprint.action_function_name)
        if not action_function:
            error_msg = f"Error: Action function '{blueprint.action_function_name}' not found."
            print(error_msg)
            return error_msg

        widget_id = id(invocation)
        self.event_bus.emit(
            "tool_call_initiated",
            ToolCallInitiated(widget_id, action_id, invocation.parameters)
        )
        await asyncio.sleep(0.1)

        try:
            prepared_params = self._prepare_parameters(action_function, invocation.parameters)

            # Support both async and sync actions
            if inspect.iscoroutinefunction(action_function):
                result = await action_function(**prepared_params)
            else:
                result = action_function(**prepared_params)

            status = "FAILURE" if isinstance(result, str) and result.strip().lower().startswith("error") else "SUCCESS"

            print(f"✅ Result from {action_id}: {result}")
            self.event_bus.emit(
                "tool_call_completed",
                ToolCallCompleted(widget_id, status, str(result))
            )
            return result

        except Exception as e:
            logger.exception("An exception occurred while executing blueprint '%s'.", action_id)
            error_msg = f"❌ Error executing Blueprint '{action_id}': {e}"
            print(error_msg)
            self.event_bus.emit(
                "tool_call_completed",
                ToolCallCompleted(widget_id, "FAILURE", error_msg)
            )
            return error_msg

    def _prepare_parameters(self, action_function: callable, action_params: dict) -> dict:
        """
        Resolves file paths (including defaults) and injects necessary services.
        """
        resolved_params = action_params.copy()
        base_path: Optional[Path] = self.project_manager.active_project_path
        sig = inspect.signature(action_function)

        service_map = self._get_service_map()

        if base_path:
            for key in self.PATH_PARAM_KEYS:
                if key in sig.parameters:
                    relative_path = action_params.get(key, sig.parameters[key].default)
                    if isinstance(relative_path, str) and relative_path:
                        if not Path(relative_path).is_absolute():
                            resolved_path = (base_path / relative_path).resolve()
                            resolved_params[key] = str(resolved_path)

        for param_name, param in sig.parameters.items():
            if param_name in service_map:
                if service_map[param_name] is not None:
                    resolved_params[param_name] = service_map[param_name]
            elif param_name == 'project_context':
                resolved_params['project_context'] = self.project_manager.active_project_context

        return resolved_params