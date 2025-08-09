# core/managers/service_manager.py
from __future__ import annotations
import sys
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Optional
import traceback
import asyncio

from event_bus import EventBus
from core.llm_client import LLMClient
from core.managers.project_manager import ProjectManager
from core.execution_engine import ExecutionEngine
from services import (
    ActionService, AppStateService, MissionLogService, DevelopmentTeamService,
    ConductorService, ToolRunnerService
)
from foundry import FoundryManager

if TYPE_CHECKING:
    from core.managers.window_manager import WindowManager


class ServiceManager:
    """
    Manages all application services and their dependencies.
    Single responsibility: Service lifecycle and dependency injection.
    """

    def __init__(self, event_bus: EventBus, project_root: Path):
        self.event_bus = event_bus
        self.project_root = project_root
        self.llm_client: LLMClient = None
        self.project_manager: ProjectManager = None
        self.execution_engine: ExecutionEngine = None
        self.foundry_manager: FoundryManager = None

        # Core Services
        self.app_state_service: AppStateService = None
        self.action_service: ActionService = None
        self.mission_log_service: MissionLogService = None
        self.development_team_service: DevelopmentTeamService = None
        self.conductor_service: ConductorService = None
        self.tool_runner_service: ToolRunnerService = None

        self.llm_server_process: Optional[subprocess.Popen] = None

        self.log_to_event_bus("info", "[ServiceManager] Initialized")

    def log_to_event_bus(self, level: str, message: str):
        self.event_bus.emit("log_message_received", "ServiceManager", level, message)

    def initialize_core_components(self, project_root: Path, project_manager: ProjectManager):
        self.log_to_event_bus("info", "[ServiceManager] Initializing core components...")
        self.llm_client = LLMClient(project_root)
        self.project_manager = project_manager
        self.execution_engine = ExecutionEngine(self.project_manager)
        self.foundry_manager = FoundryManager()
        self.log_to_event_bus("info", "[ServiceManager] Core components initialized")

    def initialize_services(self):
        """Initialize services with proper dependency order."""
        self.log_to_event_bus("info", "[ServiceManager] Initializing services...")

        self.app_state_service = AppStateService(self.event_bus)
        self.mission_log_service = MissionLogService(self.project_manager, self.event_bus)
        self.tool_runner_service = ToolRunnerService(self.event_bus, self.foundry_manager, self.project_manager,
                                                     self.mission_log_service, None)
        self.conductor_service = ConductorService(self.event_bus, self.mission_log_service, self.tool_runner_service)

        self.development_team_service = DevelopmentTeamService(self.event_bus, self)
        self.action_service = ActionService(self.event_bus, self, None, None)

        self.log_to_event_bus("info", "[ServiceManager] Services initialized")

    async def launch_background_servers(self):
        python_executable_to_use: str
        cwd_for_servers: Path
        log_dir_for_servers: Path

        self.log_to_event_bus("info", "Determining paths for launching background servers...")

        server_script_base_dir = self.project_root / "servers"
        python_executable_to_use = sys.executable
        cwd_for_servers = self.project_root
        log_dir_for_servers = self.project_root

        llm_script_path = server_script_base_dir / "llm_server.py"
        llm_subprocess_log_file = log_dir_for_servers / "llm_server_subprocess.log"

        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        # Launch LLM Server
        if self.llm_server_process is None or self.llm_server_process.poll() is not None:
            self.log_to_event_bus("info", f"Attempting to launch LLM server from {llm_script_path}...")
            try:
                with open(llm_subprocess_log_file, "w", encoding="utf-8") as llm_log_handle:
                    self.llm_server_process = subprocess.Popen(
                        [python_executable_to_use, str(llm_script_path)], cwd=str(cwd_for_servers),
                        stdout=llm_log_handle, stderr=subprocess.STDOUT, startupinfo=startupinfo
                    )
                self.log_to_event_bus("info", f"LLM Server process started with PID: {self.llm_server_process.pid}")
            except Exception as e:
                self.log_to_event_bus("error", f"Failed to launch LLM server: {e}\n{traceback.format_exc()}")

        self.log_to_event_bus("info", "Waiting for background servers to initialize...")
        await asyncio.sleep(3) # Give servers time to start up.
        self.log_to_event_bus("info", "Resuming main application initialization.")


    def terminate_background_servers(self):
        """Terminates all managed background server processes."""
        self.log_to_event_bus("info", "[ServiceManager] Terminating background servers...")
        servers = {"LLM": self.llm_server_process}
        for name, process in servers.items():
            if process and process.poll() is None:
                self.log_to_event_bus("info", f"[ServiceManager] Terminating {name} server (PID: {process.pid})...")
                process.terminate()
                try:
                    process.wait(timeout=5)
                    self.log_to_event_bus("info", f"[ServiceManager] {name} server terminated.")
                except subprocess.TimeoutExpired:
                    self.log_to_event_bus("warning",
                                          f"[ServiceManager] {name} server did not terminate gracefully. Killing.")
                    process.kill()

        self.llm_server_process = None

    async def shutdown(self):
        self.log_to_event_bus("info", "[ServiceManager] Shutting down services...")
        self.terminate_background_servers()
        self.log_to_event_bus("info", "[ServiceManager] Services shutdown complete")

    # --- Getters for Dependency Injection ---
    def get_llm_client(self) -> LLMClient:
        return self.llm_client

    def get_project_manager(self) -> ProjectManager:
        return self.project_manager

    def get_foundry_manager(self) -> FoundryManager:
        return self.foundry_manager

    def get_development_team_service(self) -> DevelopmentTeamService:
        return self.development_team_service

    def is_fully_initialized(self) -> bool:
        return all([self.llm_client, self.project_manager, self.foundry_manager])