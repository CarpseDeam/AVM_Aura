from __future__ import annotations
import sys
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Optional
import traceback
import asyncio

from event_bus import EventBus
from core.llm_client import LLMClient
from core.project_manager import ProjectManager
from core.execution_engine import ExecutionEngine
from core.plugins.plugin_manager import PluginManager
# We will create these services in the next steps
from services import (
    ActionService, AppStateService, TerminalService,
    LSPClientService, MissionLogService, DevelopmentTeamService,
    ConductorService, ToolRunnerService
)
from foundry import FoundryManager

if TYPE_CHECKING:
    from services.rag_manager import RAGManager


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
        self.plugin_manager: PluginManager = None
        self.foundry_manager: FoundryManager = None

        # Core Services
        self.app_state_service: AppStateService = None
        self.action_service: ActionService = None
        self.terminal_service: TerminalService = None
        self.rag_manager: "RAGManager" = None
        self.lsp_client_service: LSPClientService = None
        self.mission_log_service: MissionLogService = None
        self.development_team_service: DevelopmentTeamService = None
        self.conductor_service: ConductorService = None
        self.tool_runner_service: ToolRunnerService = None

        self.rag_server_process: Optional[subprocess.Popen] = None
        self.llm_server_process: Optional[subprocess.Popen] = None
        self.lsp_server_process: Optional[subprocess.Popen] = None

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

    async def initialize_plugins(self) -> bool:
        if not self.plugin_manager:
            self.log_to_event_bus("warning", "[ServiceManager] No plugin manager available for plugin initialization")
            return False
        success = await self.plugin_manager.initialize()
        self.log_to_event_bus("info", "[ServiceManager] Plugin initialization completed")
        return success

    def initialize_services(self, code_viewer=None):
        """Initialize services with proper dependency order."""
        self.log_to_event_bus("info", "[ServiceManager] Initializing services...")
        from services.rag_manager import RAGManager

        self.app_state_service = AppStateService(self.event_bus)
        self.rag_manager = RAGManager(self.event_bus, self.project_root)
        if self.project_manager:
            self.rag_manager.set_project_manager(self.project_manager)

        self.lsp_client_service = LSPClientService(self.event_bus, self.project_manager)
        self.mission_log_service = MissionLogService(self.event_bus, self.project_manager)
        self.tool_runner_service = ToolRunnerService(self.event_bus, self.foundry_manager, self.project_manager)
        self.conductor_service = ConductorService(self.event_bus, self.mission_log_service, self.tool_runner_service)

        self.development_team_service = DevelopmentTeamService(self.event_bus, self)

        self.terminal_service = TerminalService(self.event_bus, self.project_manager)
        self.action_service = ActionService(self.event_bus, self, None, None)

        self.log_to_event_bus("info", "[ServiceManager] Services initialized")

    def launch_background_servers(self):
        # This logic is adapted from AvA to run servers from a flat structure
        python_executable_to_use: str
        cwd_for_servers: Path
        log_dir_for_servers: Path

        self.log_to_event_bus("info", "Determining paths for launching background servers...")

        # We assume a flat structure where servers/ is a sibling of core/, gui/, etc.
        server_script_base_dir = self.project_root / "servers"
        python_executable_to_use = sys.executable
        cwd_for_servers = self.project_root
        log_dir_for_servers = self.project_root

        llm_script_path = server_script_base_dir / "llm_server.py"
        rag_script_path = server_script_base_dir / "rag_server.py"

        llm_subprocess_log_file = log_dir_for_servers / "llm_server_subprocess.log"
        rag_subprocess_log_file = log_dir_for_servers / "rag_server_subprocess.log"
        lsp_subprocess_log_file = log_dir_for_servers / "lsp_server_subprocess.log"

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

        # Launch RAG Server
        if self.rag_server_process is None or self.rag_server_process.poll() is not None:
            self.log_to_event_bus("info", f"Attempting to launch RAG server from {rag_script_path}...")
            try:
                with open(rag_subprocess_log_file, "w", encoding="utf-8") as rag_log_handle:
                    self.rag_server_process = subprocess.Popen(
                        [python_executable_to_use, str(rag_script_path)], cwd=str(cwd_for_servers),
                        stdout=rag_log_handle, stderr=subprocess.STDOUT, startupinfo=startupinfo
                    )
                self.log_to_event_bus("info", f"RAG Server process started with PID: {self.rag_server_process.pid}")
            except Exception as e:
                self.log_to_event_bus("error", f"Failed to launch RAG server: {e}\n{traceback.format_exc()}")

        # Launch LSP Server
        if self.lsp_server_process is None or self.lsp_server_process.poll() is not None:
            self.log_to_event_bus("info", "Attempting to launch Python LSP server...")
            lsp_command = [python_executable_to_use, "-m", "pylsp", "--tcp", "--port", "8003"]
            try:
                with open(lsp_subprocess_log_file, "w", encoding="utf-8") as lsp_log_handle:
                    self.lsp_server_process = subprocess.Popen(
                        lsp_command, cwd=str(cwd_for_servers),
                        stdout=lsp_log_handle, stderr=subprocess.STDOUT, startupinfo=startupinfo
                    )
                self.log_to_event_bus("info", f"LSP Server process started with PID: {self.lsp_server_process.pid}")
                asyncio.create_task(self.lsp_client_service.connect())
            except FileNotFoundError:
                self.log_to_event_bus("error",
                                      "Failed to launch LSP server: `pylsp` command not found. Please ensure `python-lsp-server` is installed via requirements_lsp.txt.")
            except Exception as e:
                self.log_to_event_bus("error", f"Failed to launch LSP server: {e}\n{traceback.format_exc()}")

    def terminate_background_servers(self):
        """Terminates all managed background server processes."""
        self.log_to_event_bus("info", "[ServiceManager] Terminating background servers...")
        servers = {"LLM": self.llm_server_process, "RAG": self.rag_server_process, "LSP": self.lsp_server_process}
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
        self.rag_server_process = None
        self.lsp_server_process = None

    async def shutdown(self):
        self.log_to_event_bus("info", "[ServiceManager] Shutting down services...")
        if self.lsp_client_service:
            await self.lsp_client_service.shutdown()
        self.terminate_background_servers()
        if self.plugin_manager:
            await self.plugin_manager.shutdown()
        self.log_to_event_bus("info", "[ServiceManager] Services shutdown complete")

    # --- Getters for Dependency Injection ---
    def get_llm_client(self) -> LLMClient:
        return self.llm_client

    def get_project_manager(self) -> ProjectManager:
        return self.project_manager

    def get_foundry_manager(self) -> FoundryManager:
        return self.foundry_manager

    def get_rag_manager(self) -> "RAGManager":
        return self.rag_manager

    def get_development_team_service(self) -> DevelopmentTeamService:
        return self.development_team_service

    def is_fully_initialized(self) -> bool:
        return all([self.llm_client, self.project_manager, self.foundry_manager])