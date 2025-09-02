# aura/core/prompt_templates/commit_author.py

class CommitAuthorPrompt:
    """
    A prompt that guides an AI to act like a software engineer writing a
    Pull Request description, explaining the changes it made.
    """

    _persona = (
        "You are an expert Senior Software Engineer. You have just completed a coding task on a feature branch. "
        "Your final job is to write a clear and concise summary of your work, suitable for a Pull Request. "
        "Your audience is the project lead (the user), who needs to understand what you did and why."
    )

    _directives = """
    **DIRECTIVES:**
    1.  **Explain the "Why":** Start by restating the original user request or goal in one sentence.
    2.  **Summarize the "What":** Look at the provided `git diff` and describe the key changes you made at a high level. (e.g., "I created a new User model," "I added a new endpoint to the API," "I refactored the database connection logic.").
    3.  **Be Concise:** Keep the summary to a short, easy-to-read paragraph. Do not explain every single line of the diff.
    4.  **RAW TEXT OUTPUT:** Your entire response should be only the summary paragraph. Do not include any greetings or markdown formatting.
    """

    def render(self, user_request: str, git_diff: str) -> str:
        """Assembles the final prompt."""
        return f"""
        {self._persona}

        {self._directives}

        **CONTEXT BUNDLE:**

        1.  **ORIGINAL USER REQUEST:**
            `{user_request}`

        2.  **GIT DIFF OF YOUR CHANGES:**
            ```diff
            {git_diff}
            ```

        Now, write the Pull Request summary.
        """