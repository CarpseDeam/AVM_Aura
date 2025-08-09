# foundry/actions/pip_install_action.py
import logging
import subprocess
import os
import sys
from pathlib import Path
from typing import Optional

from core.managers import ProjectContext

logger = logging.getLogger(__name__)


def pip_install(project_context: ProjectContext, requirements_path: str = "requirements.txt") -> str:
    """
    Installs dependencies from a requirements file, creating a virtual environment
    in the project root if one doesn't already exist.
    """
    if not project_context:
        return "Error: Cannot run pip install. No active project context."

    working_dir = Path(project_context.project_root)
    req_file = working_dir / requirements_path

    if not req_file.exists():
        return f"Error: requirements file not found at '{req_file}'. Please create it first."

    venv_path = working_dir / 'venv'

    # --- Intelligent Environment Creation ---
    if not venv_path.is_dir():
        logger.info(f"No virtual environment found at '{venv_path}'. Creating one now.")
        try:
            # Using sys.executable ensures we use the python that's running Aura
            create_venv_command = [sys.executable, "-m", "venv", str(venv_path)]
            result = subprocess.run(
                create_venv_command,
                check=True,
                capture_output=True,
                text=True,
                cwd=str(working_dir),
                shell=False
            )
            logger.info(f"Successfully created virtual environment.\n{result.stdout}")
        except subprocess.CalledProcessError as e:
            error_msg = f"Failed to create virtual environment.\nReturn Code: {e.returncode}\n---STDERR---\n{e.stderr}"
            logger.error(error_msg)
            return error_msg
        except Exception as e:
            return f"An unexpected error occurred while creating the virtual environment: {e}"

    # Determine the correct pip executable path based on the OS
    if os.name == 'nt':  # Windows
        pip_executable = venv_path / 'Scripts' / 'pip.exe'
    else:  # Unix-like (macOS, Linux)
        pip_executable = venv_path / 'bin' / 'pip'

    if not pip_executable.exists():
        return f"Error: Could not find pip executable at '{pip_executable}' after creating venv."

    # --- Dependency Installation ---
    install_command = [str(pip_executable), "install", "-r", str(req_file)]

    logger.info(f"Executing command: '{' '.join(install_command)}' in '{working_dir}'")
    try:
        result = subprocess.run(
            install_command,
            check=True,
            capture_output=True,
            text=True,
            cwd=str(working_dir),
            shell=False
        )
        # IMPORTANT: A successful run here should trigger a rescan of the project context
        # in the executor to pick up the new paths for subsequent steps.
        return f"Successfully installed dependencies from {requirements_path}.\n---STDOUT---\n{result.stdout}"
    except subprocess.CalledProcessError as e:
        return f"Error installing dependencies.\nReturn Code: {e.returncode}\n---STDERR---\n{e.stderr}"
    except Exception as e:
        return f"An unexpected error occurred during pip install: {e}"