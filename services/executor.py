# services/executor.py
import logging
from typing import Callable, Optional

from event_bus import EventBus
from events import (
    BlueprintInvocation, DirectToolInvocationRequest, MissionDispatchRequest, ProjectCreated
)
from foundry import FoundryManager
from .mission_log_service import MissionLogService
from .conductor_service import ConductorService
from .tool_runner_service import ToolRunnerService
from services.vector_context_service import VectorContextService

logger = logging.getLogger(__name__)


class ExecutorService:
    """
    Acts as a simple dispatcher, listening for events and delegating
    execution to the appropriate specialized service (Conductor or ToolRunner).
    """

    def __init__(
            self,
            event_bus: EventBus,
            foundry_manager: FoundryManager,
            conductor_service: ConductorService,
            tool_runner_service: ToolRunnerService,
            vector_context_service: VectorContextService,
            mission_log_service: MissionLogService,
    ):
        self.event_bus = event_bus
        self.foundry_manager = foundry_manager
        self.conductor_service = conductor_service
        self.tool_runner_service = tool_runner_service
        self.vector_context_service = vector_context_service
        self.mission_log_service = mission_log_service
        logger.info("ExecutorService (Dispatcher) initialized.")
        self._register_handlers()

    def _register_handlers(self) -> None:
        """Subscribes to events that trigger execution."""
        self.event_bus.subscribe(DirectToolInvocationRequest, self._handle_direct_tool_invocation)
        self.event_bus.subscribe(MissionDispatchRequest, self._handle_mission_dispatch)
        self.event_bus.subscribe(ProjectCreated, self._handle_project_created)

    def _handle_direct_tool_invocation(self, event: DirectToolInvocationRequest):
        """Delegates a single tool call to the ToolRunnerService."""
        logger.info(f"Dispatching direct tool invocation for '{event.tool_id}' to ToolRunnerService.")
        blueprint = self.foundry_manager.get_blueprint(event.tool_id)
        if not blueprint:
            logger.error(f"Executor could not find tool '{event.tool_id}' for direct invocation.")
            return

        invocation = BlueprintInvocation(blueprint=blueprint, parameters=event.params)

        # Inject mission_log_service for direct calls to its tools
        if event.tool_id.startswith(("add_task", "mark_task", "get_mission")):
            invocation.parameters['mission_log_service'] = self.mission_log_service

        # Inject vector_context_service for direct calls to it
        if event.tool_id == 'index_project_context':
            invocation.parameters['vector_context_service'] = self.vector_context_service

        self.tool_runner_service.run_tool(invocation)

    def _handle_mission_dispatch(self, event: MissionDispatchRequest):
        """Delegates a mission dispatch request to the ConductorService."""
        logger.info("Dispatching mission request to ConductorService.")
        self.conductor_service.execute_mission_in_background()

    def _handle_project_created(self, event: ProjectCreated):
        """Handles post-project creation tasks, like indexing."""
        logger.info(f"ProjectCreated event caught by dispatcher. Loading mission log and auto-indexing.")
        # Load the (likely empty) mission log for the new project
        self.mission_log_service.load_log_for_active_project()

        # Trigger the indexing via a direct tool call
        self.event_bus.publish(DirectToolInvocationRequest(
            tool_id='index_project_context',
            params={'path': event.project_path}
        ))