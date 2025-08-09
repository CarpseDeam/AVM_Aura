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
import re
import json
from contextlib import redirect_stdout
from typing import Optional, Dict, Any

from core.managers import ProjectContext

logger = logging.getLogger(__name__)


def _parse_pytest_output(output: str) -> Dict[str, Any]:
    """
    Parses the stdout from a pytest run to extract key metrics.
    Returns a structured dictionary.
    """
    summary_line_match = re.search(r"=+ (.*) =+", output)
    summary_line = summary_line_match.group(1) if summary_line_match else ""

    results = {
        "status": "error",
        "summary": summary_line.strip(),
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "full_output": output
    }

    # Extract counts of each status
    for status in ["passed", "failed", "errors", "skipped"]:
        match = re.search(rf"(\d+) {status}", summary_line)
        if match:
            results[status] = int(match.group(1))

    # Determine overall status
    if results["failed"] > 0 or results["errors"] > 0:
        results["status"] = "failure"
    elif results["passed"] > 0:
        results["status"] = "success"
    elif "no tests ran" in summary_line:
        results["status"] = "no_tests_found"

    return results


def lint_file(path: str) -> str:
    """
    Lints a Python file using pycodestyle (PEP8) and returns the results.
    """
    logger.info(f"Linting file: {path}")
    try:
        style_guide = pycodestyle.StyleGuide(quiet=False)
        string_io = io.StringIO()
        with redirect_stdout(string_io):
            result = style_guide.check_files([path])
        output = string_io.getvalue()

        if result.total_errors == 0:
            return f"Linting complete for '{path}': No issues found! Excellent code quality."
        else:
            return f"Linting found {result.total_errors} issue(s) in '{path}':\n{output}"
    except FileNotFoundError:
        return f"Error: File not found at '{path}'."
    except Exception as e:
        return f"An unexpected error occurred during linting: {e}"


def run_tests(project_context: ProjectContext, path: Optional[str] = None) -> Dict[str, Any]:
    """
    Runs automated tests using pytest and returns a structured JSON result.
    """
    if not project_context:
        return {"status": "error", "summary": "Cannot run tests. No active project context.", "full_output": ""}

    target_path = path or project_context.project_root
    logger.info(f"Running pytest on {target_path}.")

    python_executable = str(project_context.venv_python_path) if project_context.venv_python_path else sys.executable
    working_dir = str(project_context.project_root)

    command = [python_executable, "-m", "pytest", "--json-report", "--json-report-file=none"]
    if path:
        command.append(path)

    try:
        # Using '-q' for less verbose stdout, focusing on the summary
        result = subprocess.run(
            command + ['-q'],
            capture_output=True,
            text=True,
            check=False,
            cwd=working_dir
        )

        # We parse the combined output to get the summary line
        pytest_output = result.stdout + result.stderr
        parsed_results = _parse_pytest_output(pytest_output)

        logger.info(f"Pytest finished with status: {parsed_results['status']}")
        return parsed_results

    except FileNotFoundError:
        error_msg = f"Error: '{python_executable}' could not be run. Is it a valid executable?"
        logger.error(error_msg)
        return {"status": "error", "summary": error_msg, "full_output": ""}
    except Exception as e:
        error_message = f"An unexpected error occurred while running tests: {e}"
        logger.exception(error_message)
        return {"status": "error", "summary": error_message, "full_output": str(e)}