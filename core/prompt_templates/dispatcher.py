# aura/core/prompt_templates/dispatcher.py
from .rules import MasterRules

class ChiefOfStaffDispatcherPrompt:
    """
    A sophisticated prompt that uses full project context to determine the user's
    intent and select the correct AI agent for the job.
    """

    _persona = (
        "You are a hyper-competent 'Chief of Staff' AI for a senior software developer. "
        "Your job is to analyze the developer's latest request in the full context of the ongoing "
        "project and conversation. Based on this deep understanding, you must determine the user's "
        "core intent and select the appropriate specialist agent to handle the request."
    )

    _intents = """
    **SPECIALIST AGENTS AVAILABLE FOR DISPATCH:**

    1.  `"CREATIVE_ASSISTANT"`: For brainstorming new ideas. Select this when the user is starting a new project, proposing a new feature from a blank slate, or asking to start over. The mission log is typically empty.

    2.  `"ITERATIVE_ARCHITECT"`: For modifying an existing plan or codebase. Select this when the user's request is a clear instruction to change, add, or remove something from the code or the mission plan that already exists.

    3.  `"CONDUCTOR"`: For executing the plan. Select this ONLY when the user gives an explicit command to start the build process (e.g., "Let's build it," "Run the plan," "Dispatch Aura").

    4.  `"GENERAL_CHAT"`: For conversational dialogue. Select this for questions, comments, or any input that isn't a direct order to create or modify software (e.g., "What do you think of Tree of Thought?", "That's funny.").
    """

    _reasoning_structure = """
    **REASONING PROCESS:**
    First, in a <thought> block, you MUST follow these steps:
    1.  **Analyze Mission State:** Review the `CURRENT MISSION LOG STATE`. Is it empty, in progress, or complete? This provides the primary context for the user's request.
    2.  **Analyze User Request:** Read the `USER'S LATEST MESSAGE`. What is their literal command, question, or statement?
    3.  **Synthesize and Decide:** Based on the mission state AND the user's request, what is their true intent? Which single specialist agent is the perfect fit for this specific task? For example, if the mission log is empty and the user says "build a flask app," the intent is `CREATIVE_ASSISTANT` to start the plan. If the log is full and the user says "add a new field," the intent is `ITERATIVE_ARCHITECT`.
    """

    _output_format = f"""
    **YOUR OUTPUT FORMAT:**
    Your response must start with your reasoning in a <thought> block, followed by a single JSON object with one key: `"dispatch_to"`.
    The value MUST be one of the exact agent names listed above.
    {MasterRules.JSON_OUTPUT_RULE}
    """

    def render(self, user_prompt: str, conversation_history: str, mission_log_state: str) -> str:
        """Assembles the final prompt."""
        return f"""
        {self._persona}
        {self._intents}
        {self._reasoning_structure}
        {self._output_format}
        ---
        **INTELLIGENCE BRIEFING:**

        1.  **CONVERSATION HISTORY:**
            ```
            {conversation_history}
            ```

        2.  **CURRENT MISSION LOG STATE:**
            ```
            {mission_log_state}
            ```

        3.  **USER'S LATEST MESSAGE:**
            "{user_prompt}"
        ---
        Now, write your reasoning in a <thought> block, and then provide the final JSON output.
        """
