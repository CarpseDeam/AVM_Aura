from foundry.blueprints import Blueprint
blueprint = Blueprint(
    id="insert_task",
    description="Inserts a new task into the mission plan at a specific position.",
    parameters={
        "type": "object",
        "properties": {
            "new_task_description": {"type": "string", "description": "The description of the new task to add."},
            "after_task_id": {"type": "integer", "description": "The ID of the task after which this new task should be inserted."}
        },
        "required": ["new_task_description", "after_task_id"]
    },
    action_function_name="insert_task"
)