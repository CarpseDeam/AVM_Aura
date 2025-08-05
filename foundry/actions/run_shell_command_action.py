# foundry/actions/run_shell_command_action.py
import logging
import subprocess
import shlex
import os
from typing import Optional
from services.project_context import ProjectContext

logger = logging.getLogger(__name__)


def run_shell_command(project_context: ProjectContext, command: str) -> str:
    """
    Executes a shell command within the project's context.

    Args:
        project_context: The context of the active project.
        command: The shell command to execute.

    Returns:
        A formatted string containing the command's stdout and stderr.
    """
    if not project_context:
        return "Error: Cannot run shell command. No active project context."

    working_dir = str(project_context.project_root)
    logger.info(f"Executing shell command: '{command}' in directory '{working_dir}'")

    try:
        command_parts = shlex.split(command, posix=os.name != 'nt')

        # Intercept and replace python/pip calls with venv paths
        if command_parts[0].lower() == 'python' and project_context.venv_python_path:
            command_parts[0] = str(project_context.venv_python_path)
            logger.info(f"Replaced 'python' with venv executable: {command_parts[0]}")
        elif command_parts[0].lower() == 'pip' and project_context.venv_pip_path:
             command_parts[0] = str(project_context.venv_pip_path)
             logger.info(f"Replaced 'pip' with venv executable: {command_parts[0]}")
        elif os.name == 'nt' and command_parts[0].lower().replace('\\', '/') == 'venv/scripts/pip' and project_context.venv_pip_path:
             command_parts[0] = str(project_context.venv_pip_path)
             logger.info(f"Replaced 'venv/scripts/pip' with venv executable: {command_parts[0]}")


        result = subprocess.run(
            command_parts,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            cwd=working_dir,
            shell=False
        )
        output = f"Command executed successfully.\n--- STDOUT ---\n{result.stdout}\n--- STDERR ---\n{result.stderr}"
        logger.info(f"Command '{command}' succeeded.")
        return output
    except subprocess.CalledProcessError as e:
        error_output = (
            f"Error executing command: '{command}'\n"
            f"Return Code: {e.returncode}\n"
            f"--- STDOUT ---\n{e.stdout}\n"
            f"--- STDERR ---\n{e.stderr}"
        )
        logger.error(error_output)
        return error_output
    except FileNotFoundError:
        error_output = f"An unexpected error occurred: Command not found '{command_parts[0]}'. Make sure it's a valid command."
        logger.exception(error_output)
        return error_output
    except Exception as e:
        error_output = f"An unexpected error occurred while trying to run command '{command}': {e}"
        logger.exception(error_output)
        return error_output