# services/project_manager.py
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PROJECTS_ROOT_DIR = "projects"


class ProjectManager:
    """
    Manages the workspace, active project, and resolves file paths.
    """

    def __init__(self):
        """Initializes the ProjectManager and ensures the root projects directory exists."""
        self.root_path = Path(PROJECTS_ROOT_DIR)
        self.root_path.mkdir(exist_ok=True)
        self.active_project_path: Optional[Path] = None
        logger.info(f"ProjectManager initialized. Workspace is at './{PROJECTS_ROOT_DIR}/'")

    def is_project_active(self) -> bool:
        """Checks if a project is currently active."""
        return self.active_project_path is not None

    def create_project(self, project_name: str) -> tuple[bool, str]:
        """
        Creates a new directory for a project and sets it as the active project.

        Args:
            project_name: The name for the new project.

        Returns:
            A tuple of (success, message).
        """
        try:
            new_project_path = self.root_path / project_name
            if new_project_path.exists():
                message = f"Project '{project_name}' already exists. Setting it as active project."
                logger.warning(message)
                self.active_project_path = new_project_path
                return True, message

            new_project_path.mkdir(parents=True, exist_ok=True)
            self.active_project_path = new_project_path
            message = f"Successfully created and activated project: {project_name}"
            logger.info(message)
            return True, message
        except Exception as e:
            message = f"Failed to create project '{project_name}': {e}"
            logger.error(message, exc_info=True)
            return False, message

    def resolve_path(self, relative_or_absolute_path: str) -> Path:
        """
        Resolves a path relative to the active project.
        If no project is active, or if the path is absolute, it's returned as is.
        """
        path_obj = Path(relative_or_absolute_path)

        if not self.active_project_path or path_obj.is_absolute():
            # Return path as-is if no active project or if it's already absolute
            return path_obj.resolve()

        # Join the active project path with the relative path
        return (self.active_project_path / path_obj).resolve()

    def get_active_project_name(self) -> Optional[str]:
        """Returns the name of the active project, or None."""
        if not self.active_project_path:
            return None
        return self.active_project_path.name