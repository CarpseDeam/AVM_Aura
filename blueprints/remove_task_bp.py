from foundry.blueprints import Blueprint
blueprint = Blueprint(
    id="remove_task",
    description="Removes a task from the mission plan.",
    parameters={
        "type": "object",
        "properties": {"task_id": {"type": "integer", "description": "The ID of the task to remove."}},
        "required": ["task_id"]
    },
    action_function_name="remove_task"
)