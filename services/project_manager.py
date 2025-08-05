# services/project_manager.py
import logging
import os
from pathlib import Path
from typing import Optional

from .project_context import ProjectContext

logger = logging.getLogger(__name__)

PROJECTS_ROOT_DIR = "projects"


class ProjectManager:
    """
    Manages the workspace, active project, and its execution context.
    """

    def __init__(self):
        self.root_path = Path(PROJECTS_ROOT_DIR).resolve()
        self.root_path.mkdir(exist_ok=True)
        self.active_project_path: Optional[Path] = None
        self.active_project_context: Optional[ProjectContext] = None
        logger.info(f"ProjectManager initialized. Workspace is at '{self.root_path}'")

    def _update_project_context(self):
        """
        Scans the active project path and builds the ProjectContext object.
        """
        if not self.active_project_path:
            self.active_project_context = None
            return

        venv_python = None
        venv_pip = None
        venv_path = self.active_project_path / 'venv'

        if venv_path.is_dir():
            if os.name == 'nt':  # Windows
                py_path = venv_path / 'Scripts' / 'python.exe'
                pip_path = venv_path / 'Scripts' / 'pip.exe'
            else:  # Unix-like
                py_path = venv_path / 'bin' / 'python'
                pip_path = venv_path / 'bin' / 'pip'

            if py_path.exists():
                venv_python = py_path
                logger.info(f"Found venv python at: {venv_python}")
            if pip_path.exists():
                venv_pip = pip_path
                logger.info(f"Found venv pip at: {venv_pip}")

        self.active_project_context = ProjectContext(
            project_root=self.active_project_path,
            venv_python_path=venv_python,
            venv_pip_path=venv_pip
        )

    def is_project_active(self) -> bool:
        return self.active_project_path is not None

    def create_project(self, project_name: str) -> tuple[bool, str]:
        try:
            new_project_path = self.root_path / project_name
            if new_project_path.exists():
                message = f"Project '{project_name}' already exists. Setting it as active project."
                logger.warning(message)
            else:
                new_project_path.mkdir(parents=True, exist_ok=True)
                message = f"Successfully created and activated project: {project_name}"

            self.active_project_path = new_project_path.resolve()
            self._update_project_context()
            logger.info(message)
            return True, message
        except Exception as e:
            message = f"Failed to create project '{project_name}': {e}"
            logger.error(message, exc_info=True)
            return False, message

    def resolve_path(self, relative_or_absolute_path: str) -> Path:
        path_obj = Path(relative_or_absolute_path)
        if not self.active_project_path or path_obj.is_absolute():
            return path_obj.resolve()
        return (self.active_project_path / path_obj).resolve()

    def get_active_project_name(self) -> Optional[str]:
        if not self.active_project_path:
            return None
        return self.active_project_path.name

    def get_relative_path_str(self, absolute_path_str: str) -> str:
        if not self.is_project_active():
            return absolute_path_str
        try:
            absolute_path = Path(absolute_path_str)
            relative_path = absolute_path.relative_to(self.active_project_path)
            return str(relative_path)
        except ValueError:
            return absolute_path_str