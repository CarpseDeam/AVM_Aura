# foundry/actions/run_shell_command_action.py
import logging
import subprocess
from typing import Dict, Any

logger = logging.getLogger(__name__)


def run_shell_command(command: str) -> str:
    """
    Executes a shell command and returns its output, with robust error handling.

    Args:
        command: The shell command to execute.

    Returns:
        A formatted string containing the command's stdout and stderr.
    """
    logger.info(f"Executing shell command: '{command}'")
    try:
        # We execute from the project's root directory.
        # The agent is expected to provide full paths for project-specific commands.
        result = subprocess.run(
            command,
            shell=True,
            check=True,  # This will raise a CalledProcessError for non-zero exit codes
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8' # Be explicit about encoding
        )
        output = f"Command executed successfully.\n--- STDOUT ---\n{result.stdout}\n--- STDERR ---\n{result.stderr}"
        logger.info(f"Command '{command}' succeeded.")
        return output
    except subprocess.CalledProcessError as e:
        # This catches errors from the command itself (e.g., command not found, script error)
        error_output = (
            f"Error executing command: '{command}'\n"
            f"Return Code: {e.returncode}\n"
            f"--- STDOUT ---\n{e.stdout}\n"
            f"--- STDERR ---\n{e.stderr}"
        )
        logger.error(error_output)
        return error_output
    except Exception as e:
        # This catches other errors, like problems with starting the process
        error_output = f"An unexpected error occurred while trying to run command '{command}': {e}"
        logger.exception(error_output)
        return error_output