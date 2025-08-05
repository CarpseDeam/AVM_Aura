# blueprints/pip_install_bp.py
from foundry.blueprints import Blueprint

params = {
    "type": "object",
    "properties": {
        "requirements_path": {
            "type": "string",
            "description": "Optional. The path to the requirements.txt file. Defaults to 'requirements.txt' in the project root.",
            # "default": "requirements.txt"  <-- REMOVE THIS LINE
        }
    },
    "required": [],
}

blueprint = Blueprint(
    id="pip_install",
    description="Installs Python packages from a requirements.txt file into the project's virtual environment. It will automatically find the correct venv pip executable.",
    parameters=params,
    action_function_name="pip_install"
)