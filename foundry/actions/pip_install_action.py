# foundry/actions/pip_install_action.py
import logging
import subprocess
from typing import Optional

from services.project_context import ProjectContext

logger = logging.getLogger(__name__)

# CHANGE THE FUNCTION SIGNATURE HERE
def pip_install(project_context: ProjectContext, requirements_path: str = "requirements.txt") -> str:
    """
    Installs dependencies from a requirements file using the project's venv.

    Args:
        project_context: The context of the active project.
        requirements_path: The path to the requirements.txt file.
    """
    if not project_context:
        return "Error: Cannot run pip install. No active project context."
    if not project_context.venv_pip_path:
        return "Error: No virtual environment `pip` found in the project context. Was the venv created successfully?"

    pip_executable = str(project_context.venv_pip_path)
    working_dir = str(project_context.project_root)
    req_file = project_context.project_root / requirements_path

    if not req_file.exists():
        return f"Error: requirements file not found at '{req_file}'"

    command = [pip_executable, "install", "-r", str(req_file)]

    logger.info(f"Executing command: '{' '.join(command)}' in '{working_dir}'")
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            cwd=working_dir,
            shell=False
        )
        return f"Successfully installed dependencies from {requirements_path}.\n---STDOUT---\n{result.stdout}"
    except subprocess.CalledProcessError as e:
        return f"Error installing dependencies.\nReturn Code: {e.returncode}\n---STDERR---\n{e.stderr}"
    except Exception as e:
        return f"An unexpected error occurred during pip install: {e}"