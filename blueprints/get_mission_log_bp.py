# blueprints/get_mission_log_bp.py
from foundry.blueprints import Blueprint

params = { "type": "object", "properties": {}, "required": [] }

blueprint = Blueprint(
    id="get_mission_log",
    description="Retrieves the current list of all tasks (both pending and completed) from the Mission Log.",
    parameters=params,
    action_function_name="get_mission_log"
)