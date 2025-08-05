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
from typing import Optional

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

                # Only include frames that are within the project's directory
                # to avoid clutter from standard library or site-packages.
                is_in_project = False
                try:
                    # is_relative_to is Python 3.9+
                    if filename.is_relative_to(project_root):
                        is_in_project = True
                except (ValueError, AttributeError):
                    # Fallback for older python or different drives on Windows
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

            report_data = {
                "exception_type": str(exc_type.__name__),
                "exception_value": str(exc_value),
                "traceback_string": tb_string,
                "stack": frames,
            }

            try:
                output_path = project_root / OUTPUT_FILE
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(report_data, f, indent=2)
            except Exception as e:
                print(f"Aura Debugger Hook Error: Failed to write to {output_path}: {e}")

    # We do not raise here. Let pytest handle its own reporting flow after we're done.
"""


def run_with_debugger(project_context: ProjectContext, path: Optional[str] = None) -> str:
    """
    Runs pytest with a debugger hook to capture detailed state on failure.
    """
    if not project_context:
        return "Error: Cannot run debugger. No active project context."

    working_dir = Path(project_context.project_root)
    target = path or "the project"
    logger.info(f"Running pytest with debugger on {target} in '{working_dir}'.")

    python_executable = str(project_context.venv_python_path) if project_context.venv_python_path else sys.executable
    conftest_path = working_dir / "aura_debugger_conftest.py"
    output_path = working_dir / "aura_debug_output.json"

    return_value = ""  # The value to be returned at the end.

    try:
        # Step 1: Write the dynamic conftest file into the target project
        conftest_path.write_text(DEBUGGER_CONTEST_CODE, encoding='utf-8')
        logger.info(f"Created temporary debugger plugin at {conftest_path}")

        # Step 2: Build and run the pytest command, loading our plugin
        command = [
            python_executable, "-m", "pytest",
            "-p", "aura_debugger_conftest"
        ]
        if path:
            command.append(path)

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,  # We handle the non-zero exit code ourselves
            cwd=str(working_dir)
        )

        # Step 3: Check if the debugger hook created its output file
        if output_path.exists():
            logger.info("Test failure detected. Reading full debug report from Omniscient Debugger.")
            with open(output_path, 'r', encoding='utf-8') as f:
                debug_data = json.load(f)

            # Step 4: Format the rich debug info into a single string for the LLM
            report = [
                "❌ Tests failed! The Omniscient Debugger captured the following state:",
                "--- EXCEPTION ---",
                f"Type: {debug_data['exception_type']}",
                f"Value: {debug_data['exception_value']}",
                "\n--- FULL STACK TRACE ---",
                debug_data['traceback_string'],
                "\n--- LOCAL VARIABLES (Most Recent Call First) ---"
            ]

            for frame in reversed(debug_data.get('stack', [])):
                report.append(f"\n[File: '{frame['file']}', Line: {frame['line']}, In: `{frame['function']}`]")
                locals_str = pprint.pformat(frame['locals'], indent=2, width=120, sort_dicts=False)
                report.append(locals_str)

            return_value = "\n".join(report)

        else:
            # Step 5: If no debug file, tests passed or another error occurred
            output = result.stdout + "\n" + result.stderr
            if result.returncode == 0:
                return_value = f"✅ All tests passed!\n\n{output}"
            else:
                return_value = f"⚠️ Tests failed, but the debugger did not generate a report. Standard pytest output:\n\n{output}"

    except Exception as e:
        error_message = f"An unexpected error occurred while running the debugger: {e}"
        logger.exception(error_message)
        return_value = error_message
    finally:
        # Step 6: Always clean up the temporary files
        conftest_path.unlink(missing_ok=True)
        output_path.unlink(missing_ok=True)
        logger.info("Cleaned up temporary debugger files.")

    return return_value