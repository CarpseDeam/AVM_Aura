# aura/core/prompt_templates/summarizer.py
from .rules import MasterRules

class MissionSummarizerPrompt:
    """A structured prompt for generating a concise, user-facing summary of a completed mission."""

    _persona = (
        "You are Aura, an AI Software Engineer. You have just completed a development mission. "
        "Your task is to write a concise, professional, and friendly summary of the work you performed."
    )

    _directives = """
    **SUMMARY DIRECTIVES:**
    1.  **Start with "Mission accomplished!":** Your summary must begin with this exact phrase.
    2.  **Focus on Accomplishments:** Summarize the key achievements based on the task log. Don't just list the tasks; describe what was built.
    3.  **User-Facing Language:** Use clear, non-technical language where possible.
    """

    def render(self, completed_tasks: str) -> str:
        """Assembles the final prompt string."""
        return f"""
        {self._persona}

        {self._directives}

        **COMPLETED TASK LOG:**
        This is the list of tasks you successfully completed.
        ```
        {completed_tasks}
        ```

        Now, generate the summary paragraph.
        """