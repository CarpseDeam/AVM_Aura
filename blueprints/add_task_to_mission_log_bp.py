# blueprints/add_task_to_mission_log_bp.py
from foundry.blueprints import Blueprint

params = {
    "type": "object",
    "properties": {
        "description": {
            "type": "string",
            "description": "A clear, concise description of the task to be added to the mission log.",
        }
    },
    "required": ["description"],
}

blueprint = Blueprint(
    id="add_task_to_mission_log",
    description="Adds a new task to the project's shared to-do list (the Mission Log).",
    parameters=params,
    action_function_name="add_task_to_mission_log"
)