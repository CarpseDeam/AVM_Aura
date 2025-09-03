# core/prompt_templates/dispatcher.py - Updated with Iterative Development
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

    3.  `"ITERATIVE_DEVELOPER"`: For refining, correcting, or improving existing code through collaborative iteration. Select this when the user is:
        - Providing feedback on recently generated code ("that's not quite right", "make it better")
        - Requesting corrections or refinements ("fix this", "improve that function") 
        - Asking for style adjustments ("I prefer this pattern", "change the approach")
        - Reporting errors that need fixing ("this is broken", "getting an error")
        - Wanting to iterate on existing implementations step-by-step
        - Engaged in back-and-forth refinement of code

    4.  `"CONDUCTOR"`: For executing the plan. Select this ONLY when the user gives an explicit command to start the build process (e.g., "Let's build it," "Run the plan," "Dispatch Aura").

    5.  `"GENERAL_CHAT"`: For conversational dialogue. Select this for questions, comments, or any input that isn't a direct order to create or modify software (e.g., "What do you think of Tree of Thought?", "That's funny.").
    """

    _reasoning_structure = """
    **REASONING PROCESS:**
    In a <thought> block, analyze the user's request in the context of the conversation history and mission log.
    Pay special attention to:
    - Is this the first request (new project) or are they refining existing work?
    - Are they providing feedback on something that was just generated?
    - Do they mention specific code, functions, or files that need changes?
    - Are they reporting errors or issues with existing code?
    - Is this part of an ongoing iterative development session?

    Synthesize your findings to determine the user's true intent and decide which specialist agent is the perfect fit for the task.
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

        **ITERATIVE DEVELOPMENT DETECTION:**
        Look for these patterns that indicate ITERATIVE_DEVELOPER should be used:
        - References to recently generated code or files
        - Feedback language: "that's wrong", "not quite", "better", "fix", "improve" 
        - Error reports: "getting error", "broken", "doesn't work"
        - Refinement requests: "make it more", "add to", "change the", "adjust"
        - Correction language: "should be", "instead of", "prefer"
        - Collaborative language: "let's refine", "can you improve", "try again"

        Now, provide your concise reasoning in a <thought> block, and then provide the final JSON output.
        """


# Add to services/agent_workflow_manager.py

# In the __init__ method, add this to self._agent_workflows:
"""
"ITERATIVE_DEVELOPER": {
    "prompt_class": IterativeDeveloperPrompt,
    "role": "iterative_coder", 
    "handler": self._run_iterative_development_workflow,
},
"""


# Add this method to AgentWorkflowManager:
async def _run_iterative_development_workflow(self, user_request: str, conversation_history: list):
    """Run iterative development workflow for code refinement."""
    self.log("info", f"Iterative development workflow initiated for: '{user_request[:50]}...'")
    self.event_bus.emit("agent_status_changed", "Aura", "Refining code iteratively...", "fa5s.sync-alt")

    # Get or create iterative development service
    iterative_service = self.service_manager.get_iterative_development_service()

    # Handle the refinement request
    try:
        tool_call = await iterative_service.handle_refinement_request(user_request, conversation_history)

        if tool_call:
            # Execute the refinement tool call
            tool_result = await self.tool_runner_service.execute_tool_call(tool_call)

            if tool_result.get("success"):
                # Track the generated code for learning
                if tool_call.get("tool_name") == "stream_and_write_file":
                    iterative_service.track_generated_code(
                        tool_call["arguments"]["content"],
                        tool_call["arguments"]["path"]
                    )

                self._post_chat_message("Aura",
                                        f"✅ Refinement completed! I've updated the code based on your feedback. How does this look?")
            else:
                self._post_chat_message("Aura", f"❌ Refinement failed: {tool_result.get('error', 'Unknown error')}")
        else:
            self._post_chat_message("Aura",
                                    "I understand you want to refine something, but I need more specific guidance about what to change.")

    except Exception as e:
        self.handle_error("Aura", f"Iterative development failed: {str(e)}")