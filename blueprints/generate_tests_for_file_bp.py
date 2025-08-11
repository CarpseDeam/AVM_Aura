# blueprints/generate_tests_for_file_bp.py
from foundry.blueprints import Blueprint

params = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "The relative path to the Python source file that needs to be tested.",
        }
    },
    "required": ["path"],
}

blueprint = Blueprint(
    id="generate_tests_for_file",
    description="Generates a new pytest test file for a given Python source file and saves it in the 'tests' directory. This is the required tool for creating tests.",
    parameters=params,
    action_function_name="generate_tests_for_file"
)