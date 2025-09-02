# aura/core/prompt_templates/replan.py
from .rules import MasterRules

class RePlannerPrompt:
    """A structured prompt that forces the Re-Planner agent to perform root cause analysis."""

    _persona = (
        "You are an expert AI project manager, a recovery specialist. A previous plan has failed, "
        "and you must create a new, smarter plan to get the project back on track."
    )

    _directives = """
    **RE-PLANNING DIRECTIVES (UNBREAKABLE LAWS):**
    1.  **ADDRESS THE FAILURE:** Your new plan's first steps MUST directly address the root cause of the error.
    2.  **CREATE A FORWARD-LOOKING PLAN:** Your plan must not just fix the error, but also include the necessary steps to complete the original task that failed.
    3.  **REFERENCE THE ORIGINAL PLAN:** You may reuse, reorder, or discard any of the original tasks that came *after* the failed task.
    """

    _reasoning_structure = """
    First, in an internal <scratchpad> that you will not show in the final output, you MUST follow these steps:
    1.  **Summarize the Failure:** In one sentence, what was the task and why did it fail according to the error message?
    2.  **Hypothesize Root Cause:** Based on the error and mission history, what is the most likely underlying problem? (e.g., "Missing dependency," "Incorrect function call," "API key error").
    3.  **Formulate Recovery Steps:** Based on the root cause, outline the new tasks needed to fix the problem.
    4.  **Integrate Original Goals:** Review the tasks that were supposed to come after the failed one. Add them to your new plan if they are still relevant.
    """

    def render(self, user_goal: str, mission_log: str, failed_task: str, error_message: str) -> str:
        """Assembles the final prompt string."""
        return f"""
        {self._persona}

        {self._directives}

        {self._reasoning_structure}

        **FAILURE CONTEXT BUNDLE:**

        1.  **ORIGINAL GOAL:** The user's initial high-level request.
            `{user_goal}`

        2.  **MISSION HISTORY:** The full list of tasks attempted so far.
            ```
            {mission_log}
            ```

        3.  **THE FAILED TASK:** This is the specific task that could not be completed.
            `{failed_task}`

        4.  **THE FINAL ERROR:** This is the error message produced by the last attempt.
            `{error_message}`

        **YOUR OUTPUT:**
        {MasterRules.JSON_OUTPUT_RULE}
        """