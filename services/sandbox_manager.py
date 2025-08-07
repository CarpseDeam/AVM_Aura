# services/sandbox_manager.py
import logging
import shutil
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


class SandboxManager:
    """
    Manages a temporary, sandboxed environment for executing file operations.
    """

    def __init__(self, project_path: Path):
        """
        Initializes the manager with the path to the real project.

        Args:
            project_path: The absolute path to the real project directory.
        """
        if not project_path or not project_path.is_dir():
            raise ValueError("A valid project path must be provided to initialize the sandbox.")
        self.project_path = project_path
        self.sandbox_path: Path | None = None
        logger.info(f"SandboxManager initialized for project: {self.project_path.name}")

    def create(self) -> Path:
        """
        Creates a temporary sandbox and copies the project content into it.

        Returns:
            The Path object for the newly created sandbox directory.
        """
        self.sandbox_path = Path(tempfile.mkdtemp(prefix="aura_sandbox_"))
        logger.info(f"Created sandbox directory at: {self.sandbox_path}")

        # Copy the entire project directory into the sandbox
        shutil.copytree(
            src=str(self.project_path),
            dst=str(self.sandbox_path),
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns('*.pyc', '__pycache__', '.git', '.idea')
        )
        logger.info(f"Copied project content to sandbox.")
        return self.sandbox_path

    def commit(self) -> None:
        """
        Commits the changes from the sandbox back to the original project directory.
        This is a destructive operation on the original project path.
        """
        if not self.sandbox_path:
            raise RuntimeError("Cannot commit changes, sandbox was never created.")

        logger.warning(f"Committing changes from sandbox to project: {self.project_path}")

        # 1. Remove the original project's contents
        for item in self.project_path.iterdir():
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            else:
                item.unlink()

        # 2. Copy the new contents from the sandbox
        shutil.copytree(
            src=str(self.sandbox_path),
            dst=str(self.project_path),
            dirs_exist_ok=True
        )
        logger.info("Successfully committed changes from sandbox.")

    def cleanup(self) -> None:
        """
        Deletes the sandbox directory and all its contents.
        """
        if self.sandbox_path and self.sandbox_path.exists():
            shutil.rmtree(self.sandbox_path, ignore_errors=True)
            logger.info(f"Cleaned up sandbox directory: {self.sandbox_path}")
            self.sandbox_path = None