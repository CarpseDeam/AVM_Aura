# foundry/actions/debugging_actions.py
"""
Contains actions related to advanced debugging, like running tests with
state-capturing capabilities.
"""
import logging
import subprocess
import sys
import json
import pprint
from pathlib import Path
from typing import Optional, Dict, Any

from services.project_context import ProjectContext

logger = logging.getLogger(__name__)

# This Python code will be written to a temporary conftest.py file in the user's project
# to enable the debugger hook during a test run.
DEBUGGER_CONTEST_CODE = """
import pytest
import sys
import traceback
import json
import pprint
from pathlib import Path

OUTPUT_FILE = 'aura_debug_output.json'

def _format_locals(locals_dict):
    \"\"\"Safely format local variables, avoiding display of huge data.\"\"\"
    safe_locals = {}
    for key, value in locals_dict.items():
        try:
            if key == '__builtins__':
                continue
            repr_val = repr(value)
            if len(repr_val) > 1024:
                 safe_locals[key] = f"{repr_val[:1024]}... (truncated)"
            else:
                 safe_locals[key] = repr_val
        except Exception:
            safe_locals[key] = "!!! Error getting repr for this variable !!!"
    return safe_locals

@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_call(item):
    \"\"\"
    Hook to wrap the actual test call, allowing us to catch exceptions
    that pytest would normally handle itself (like AssertionErrors).
    \"\"\"
    outcome = yield
    try:
        # This will raise the exception if the test failed.
        outcome.get_result()
    except Exception:
        excinfo = sys.exc_info()
        exc_type, exc_value, tb = excinfo

        # We only want to generate a debug report for actual test failures,
        # not for things like skips or xfails which are expected.
        if not isinstance(exc_value, (pytest.skip.Exception, pytest.xfail.Exception)):
            frames = []
            project_root = Path(item.session.config.rootpath)
            tb_cursor = tb
            while tb_cursor:
                frame = tb_cursor.tb_frame
                filename = Path(frame.f_code.co_filename)

                is_in_project = False
                try:
                    if filename.is_relative_to(project_root):
                        is_in_project = True
                except (ValueError, AttributeError):
                    if str(project_root) in str(filename):
                        is_in_project = True

                if is_in_project:
                    frames.append({
                        "file": str(filename.relative_to(project_root)),
                        "line": tb_cursor.tb_lineno,
                        "function": frame.f_code.co_name,
                        "locals": _format_locals(frame.f_locals)
                    })
                tb_cursor = tb_cursor.tb_next

            tb_string = "".join(traceback.format_exception(exc_type, exc_value, tb))

            # This is the detailed report specific to the debugger
            debugger_report = {
                "exception_type": str(exc_type.__name__),
                "exception_value": str(exc_value),
                "traceback_string": tb_string,
                "stack": frames,
            }

            # This is the standardized report structure
            report_data = {
                "status": "failure",
                "summary": "Test failed with an exception.",
                "debugger_report": debugger_report
            }

            try:
                output_path = project_root / OUTPUT_FILE
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(report_data, f, indent=2)
            except Exception as e:
                print(f"Aura Debugger Hook Error: Failed to write to {output_path}: {e}")
"""


def run_with_debugger(project_context: ProjectContext, path: Optional[str] = None) -> Dict[str, Any]:
    """
    Runs pytest with a debugger hook to capture detailed state on failure.
    Returns a structured JSON result.
    """
    if not project_context:
        return {"status": "error", "summary": "Cannot run debugger. No active project context."}

    working_dir = Path(project_context.project_root)
    target = path or "the project"
    logger.info(f"Running pytest with debugger on {target} in '{working_dir}'.")

    python_executable = str(project_context.venv_python_path) if project_context.venv_python_path else sys.executable
    conftest_path = working_dir / "aura_debugger_conftest.py"
    output_path = working_dir / "aura_debug_output.json"

    try:
        conftest_path.write_text(DEBUGGER_CONTEST_CODE, encoding='utf-8')
        command = [python_executable, "-m", "pytest", "-p", "aura_debugger_conftest"]
        if path:
            command.append(path)

        result = subprocess.run(
            command, capture_output=True, text=True, check=False, cwd=str(working_dir)
        )

        if output_path.exists():
            logger.info("Test failure detected. Reading full debug report.")
            with open(output_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            if result.returncode == 0:
                return {"status": "success", "summary": "All tests passed."}
            else:
                return {"status": "error", "summary": "Tests failed, but debugger did not generate a report.", "full_output": result.stdout + result.stderr}

    except Exception as e:
        error_message = f"An unexpected error occurred while running the debugger: {e}"
        logger.exception(error_message)
        return {"status": "error", "summary": error_message}
    finally:
        conftest_path.unlink(missing_ok=True)
        output_path.unlink(missing_ok=True)
        logger.info("Cleaned up temporary debugger files.")