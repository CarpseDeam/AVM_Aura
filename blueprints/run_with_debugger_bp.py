# blueprints/run_with_debugger_bp.py
from foundry.blueprints import Blueprint

params = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "Optional. The specific directory or file to run tests on. If omitted, tests are run for the entire project.",
        }
    },
    "required": [],
}

blueprint = Blueprint(
    id="run_with_debugger",
    description="Executes tests using pytest with a special debugger attached. If tests fail, it captures a detailed report including the exception, stack trace, and all local variables at each frame. This is the preferred tool for fixing bugs.",
    parameters=params,
    action_function_name="run_with_debugger"
)