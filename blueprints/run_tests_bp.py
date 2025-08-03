# blueprints/run_tests_bp.py
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
    id="run_tests",
    description="Executes automated tests using pytest. Can target the whole project or a specific file/directory. This is the primary way to verify code correctness.",
    parameters=params,
    action_function_name="run_tests"
)