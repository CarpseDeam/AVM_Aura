# foundry/actions/code_quality_actions.py
"""
Contains actions related to code quality, such as linting and testing.
"""
import logging
import pycodestyle
import io
import subprocess
import sys
import os
from contextlib import redirect_stdout
from typing import Optional

from services.project_context import ProjectContext

logger = logging.getLogger(__name__)


def lint_file(path: str) -> str:
    """
    Lints a Python file using pycodestyle (PEP8) and returns the results.

    Args:
        path: The path to the Python file to be linted.

    Returns:
        A formatted string with the linting results, or a success message.
    """
    logger.info(f"Linting file: {path}")
    try:
        style_guide = pycodestyle.StyleGuide(quiet=False)
        string_io = io.StringIO()
        with redirect_stdout(string_io):
            result = style_guide.check_files([path])
        output = string_io.getvalue()

        if result.total_errors == 0:
            success_message = f"Linting complete for '{path}': No issues found! Excellent code quality."
            logger.info(success_message)
            return success_message
        else:
            report_message = f"Linting found {result.total_errors} issue(s) in '{path}':\n{output}"
            logger.warning(f"Linting found issues in '{path}'.")
            return report_message
    except FileNotFoundError:
        error_message = f"Error: File not found at '{path}'."
        logger.warning(error_message)
        return error_message
    except Exception as e:
        error_message = f"An unexpected error occurred during linting: {e}"
        logger.exception(error_message)
        return error_message


def run_tests(project_context: ProjectContext, path: Optional[str] = None) -> str:
    """
    Runs automated tests using pytest within the project's context.

    Args:
        project_context: The context of the active project.
        path: Optional. A specific file or directory to test.

    Returns:
        A formatted string with the pytest results.
    """
    if not project_context:
        return "Error: Cannot run tests. No active project context."

    target = path or "the project"
    logger.info(f"Running pytest on {target}.")

    python_executable = str(project_context.venv_python_path) if project_context.venv_python_path else sys.executable
    working_dir = str(project_context.project_root)

    logger.info(f"Using python: {python_executable}")
    logger.info(f"Setting working directory for pytest to: {working_dir}")

    command = [python_executable, "-m", "pytest"]
    if path:
        command.append(path)

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            cwd=working_dir
        )

        output = result.stdout + "\n" + result.stderr

        if result.returncode == 0:
            success_message = f"✅ All tests passed for {target}!\n\n{output}"
            logger.info(success_message)
            return success_message
        elif result.returncode == 5:
            no_tests_message = f"⚠️ No tests were found for {target}.\n\n{output}"
            logger.warning(no_tests_message)
            return no_tests_message
        else:
            failure_message = f"❌ Tests failed for {target} (exit code {result.returncode}).\n\n" + output
            logger.error(failure_message)
            return failure_message
    except FileNotFoundError:
        error_msg = f"Error: '{python_executable}' could not be run. Is it a valid executable?"
        logger.error(error_msg)
        return error_msg
    except Exception as e:
        error_message = f"An unexpected error occurred while running tests: {e}"
        logger.exception(error_message)
        return error_message