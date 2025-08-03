# foundry/actions/code_quality_actions.py
"""
Contains actions related to code quality, such as linting and testing.
"""
import logging
import pycodestyle
import io
import subprocess
import sys
from contextlib import redirect_stdout
from typing import Optional

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
        # Create a StyleGuide instance. We can configure it if needed.
        style_guide = pycodestyle.StyleGuide(quiet=False)

        # pycodestyle's check_files method prints to stdout. We need to capture it.
        string_io = io.StringIO()
        with redirect_stdout(string_io):
            result = style_guide.check_files([path])

        # Get the output from the StringIO buffer
        output = string_io.getvalue()

        if result.total_errors == 0:
            success_message = f"Linting complete for '{path}': No issues found! Excellent code quality."
            logger.info(success_message)
            return success_message
        else:
            report_message = (
                f"Linting found {result.total_errors} issue(s) in '{path}':\n"
                f"----------------------------------------\n"
                f"{output}"
                f"----------------------------------------"
            )
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


def run_tests(path: Optional[str] = None) -> str:
    """
    Runs automated tests using pytest.

    Args:
        path: Optional. A specific file or directory to test. If None,
              pytest will discover and run all tests in the project.

    Returns:
        A formatted string with the pytest results.
    """
    target = path or "the project"
    logger.info(f"Running pytest on {target}.")

    # Using sys.executable ensures we use the pytest from the correct venv
    command = [sys.executable, "-m", "pytest"]
    if path:
        command.append(path)

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False  # We handle the return code manually
        )

        output = result.stdout + "\n" + result.stderr

        # pytest exit codes:
        # 0: All tests passed
        # 1: Tests were collected and run, but some tests failed
        # 2: Test execution was interrupted by the user
        # 3: Internal error occurred while executing tests
        # 4: pytest command line usage error
        # 5: No tests were collected
        if result.returncode == 0:
            success_message = f"✅ All tests passed for {target}!\n\n" + output
            logger.info(success_message)
            return success_message
        elif result.returncode == 5:
            no_tests_message = f"⚠️ No tests were found for {target}.\n\n" + output
            logger.warning(no_tests_message)
            return no_tests_message
        else:
            failure_message = f"❌ Tests failed for {target} (exit code {result.returncode}).\n\n" + output
            logger.error(failure_message)
            return failure_message

    except FileNotFoundError:
        error_msg = "Error: 'pytest' could not be run. Is it installed in the environment?"
        logger.error(error_msg)
        return error_msg
    except Exception as e:
        error_message = f"An unexpected error occurred while running tests: {e}"
        logger.exception(error_message)
        return error_message