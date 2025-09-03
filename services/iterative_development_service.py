"""
Iterative Development Service - Makes Aura a beast at collaborative Python coding.
Handles refinement, corrections, and learning from user feedback.
"""
import logging
import re
import ast
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from event_bus import EventBus
from core.models.messages import AuraMessage, MessageType
from services.vector_context_service import VectorContextService

logger = logging.getLogger(__name__)


@dataclass
class CodeFeedback:
    """User feedback about generated code."""
    original_code: str
    user_comment: str
    feedback_type: str  # "correction", "improvement", "style", "error"
    context_file: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class IterationContext:
    """Context for iterative development session."""
    current_goal: str
    files_being_worked_on: Set[str] = field(default_factory=set)
    recent_errors: List[str] = field(default_factory=list)
    user_preferences: Dict[str, Any] = field(default_factory=dict)
    iteration_history: List[Dict] = field(default_factory=list)
    last_generated_code: Optional[str] = None
    conversation_context: List[str] = field(default_factory=list)


class IterativeDevelopmentService:
    """
    Handles iterative Python development - refinement, corrections, and learning.
    """

    def __init__(self, event_bus: EventBus, service_manager):
        self.event_bus = event_bus
        self.service_manager = service_manager
        self.llm_client = service_manager.get_llm_client()
        self.project_manager = service_manager.project_manager
        self.vector_context_service = service_manager.vector_context_service
        self.mission_log_service = service_manager.mission_log_service

        # Track iterative development context
        self.iteration_context = IterationContext(current_goal="")
        self.code_feedback_history: List[CodeFeedback] = []
        self.user_coding_patterns: Dict[str, Any] = {}

        logger.info("IterativeDevelopmentService initialized")

    def start_iterative_session(self, goal: str, conversation_history: List[Dict]):
        """Start a new iterative development session."""
        logger.info(f"Starting iterative session: {goal}")

        self.iteration_context = IterationContext(
            current_goal=goal,
            conversation_context=[msg.get('content', '') for msg in conversation_history[-10:]]
        )

        # Analyze the goal to understand what we're building
        self._analyze_goal_and_set_context(goal)

        self._post_message(
            f"🚀 **Iterative Development Session Started**\n\nGoal: {goal}\n\nI'm ready to work with you step-by-step. Tell me what you want to build first, and we'll refine it together.")

    async def handle_refinement_request(self, user_input: str, conversation_history: List[Dict]) -> Dict[str, str]:
        """
        Handle requests to refine, improve, or fix existing code.
        """
        logger.info(f"Handling refinement: {user_input[:100]}...")

        # Update conversation context
        self.iteration_context.conversation_context.append(user_input)

        # Analyze the refinement request
        refinement_type = self._analyze_refinement_type(user_input)

        if refinement_type == "code_correction":
            return await self._handle_code_correction(user_input, conversation_history)
        elif refinement_type == "improvement_request":
            return await self._handle_improvement_request(user_input, conversation_history)
        elif refinement_type == "error_fix":
            return await self._handle_error_fix(user_input, conversation_history)
        elif refinement_type == "style_adjustment":
            return await self._handle_style_adjustment(user_input, conversation_history)
        else:
            return await self._handle_general_iteration(user_input, conversation_history)

    async def _handle_code_correction(self, user_input: str, conversation_history: List[Dict]) -> Dict[str, str]:
        """Handle direct code corrections from the user."""
        logger.info("Handling code correction")

        # Extract what the user wants corrected
        correction_context = self._extract_correction_context(user_input)

        # Get relevant code context
        relevant_files = self._get_current_working_files()
        code_context = await self._get_smart_code_context(correction_context, relevant_files)

        # Learn from the correction
        self._learn_from_correction(user_input, correction_context)

        prompt = f"""
You are helping with iterative Python development. The user has provided a correction/feedback.

**Current Goal:** {self.iteration_context.current_goal}

**User's Correction/Feedback:** 
{user_input}

**Relevant Code Context:**
{code_context}

**Previous Conversation:**
{chr(10).join(self.iteration_context.conversation_context[-5:])}

**User's Coding Preferences (learned):**
{self._format_learned_preferences()}

**Your Task:**
1. Understand exactly what the user wants corrected/changed
2. Apply the correction while maintaining the overall goal
3. Explain what you changed and why
4. Ask if this is closer to what they want

Generate a tool call to implement the correction. Be specific and incremental.
"""

        return await self._generate_iterative_tool_call(prompt, "correction")

    async def _handle_improvement_request(self, user_input: str, conversation_history: List[Dict]) -> Dict[str, str]:
        """Handle requests to improve existing code."""
        logger.info("Handling improvement request")

        improvement_focus = self._extract_improvement_focus(user_input)

        # Get context about current code
        relevant_files = self._get_current_working_files()
        code_context = await self._get_smart_code_context(user_input, relevant_files)

        prompt = f"""
You are helping with iterative Python development. The user wants to improve existing code.

**Current Goal:** {self.iteration_context.current_goal}

**Improvement Request:** 
{user_input}

**Focus Area:** {improvement_focus}

**Current Code Context:**
{code_context}

**Improvement Guidelines:**
- Make incremental improvements, don't rewrite everything
- Maintain existing functionality
- Follow Python best practices
- Add error handling if missing
- Improve readability and maintainability

**Your Task:**
Generate a specific tool call to improve the code. Explain what improvements you're making.
"""

        return await self._generate_iterative_tool_call(prompt, "improvement")

    async def _handle_error_fix(self, user_input: str, conversation_history: List[Dict]) -> Dict[str, str]:
        """Handle error fixing requests."""
        logger.info("Handling error fix")

        # Extract error information
        error_info = self._extract_error_info(user_input)
        self.iteration_context.recent_errors.append(error_info)

        # Get context about the problematic code
        relevant_files = self._get_current_working_files()
        code_context = await self._get_smart_code_context(f"fix error {error_info}", relevant_files)

        prompt = f"""
You are helping debug and fix Python code iteratively.

**Current Goal:** {self.iteration_context.current_goal}

**Error/Issue:** 
{user_input}

**Extracted Error Info:** {error_info}

**Code Context:**
{code_context}

**Recent Errors in Session:**
{chr(10).join(self.iteration_context.recent_errors[-3:])}

**Debugging Strategy:**
1. Identify the root cause of the error
2. Propose a minimal fix that addresses the issue
3. Add defensive programming if needed
4. Explain what went wrong and how the fix addresses it

Generate a tool call to fix the error. Be surgical - fix the specific issue without breaking other things.
"""

        return await self._generate_iterative_tool_call(prompt, "error_fix")

    async def _handle_style_adjustment(self, user_input: str, conversation_history: List[Dict]) -> Dict[str, str]:
        """Handle style and pattern adjustments."""
        logger.info("Handling style adjustment")

        # Learn the user's style preference
        style_preference = self._extract_style_preference(user_input)
        self._update_style_preferences(style_preference)

        relevant_files = self._get_current_working_files()
        code_context = await self._get_smart_code_context(user_input, relevant_files)

        prompt = f"""
You are helping adjust Python code style to match the user's preferences.

**Style Adjustment Request:** 
{user_input}

**Current Code Context:**
{code_context}

**User's Style Preferences (learned):**
{self._format_learned_preferences()}

**Your Task:**
Adjust the code style/pattern to match what the user prefers. Keep the functionality identical, just change the implementation style.
"""

        return await self._generate_iterative_tool_call(prompt, "style_adjustment")

    async def _generate_iterative_tool_call(self, prompt: str, operation_type: str) -> Dict[str, str]:
        """Generate a tool call for iterative development."""

        provider, model = self.llm_client.get_model_for_role("coder")
        if not provider or not model:
            return None

        try:
            # Add JSON formatting instruction
            full_prompt = f"""{prompt}

**Output Format:**
Return a JSON object with "tool_name" and "arguments" keys. The tool should be specific to the {operation_type} needed.

Example:
{{"tool_name": "stream_and_write_file", "arguments": {{"path": "specific_file.py", "content": "improved code here"}}}}
"""

            response_str = "".join(
                [chunk async for chunk in self.llm_client.stream_chat(provider, model, full_prompt, "coder")])

            # Parse JSON response
            import json
            match = re.search(r'\{.*\}', response_str, re.DOTALL)
            if match:
                tool_call = json.loads(match.group(0))

                # Track the iteration
                self.iteration_context.iteration_history.append({
                    "operation": operation_type,
                    "tool_call": tool_call,
                    "timestamp": datetime.now().isoformat()
                })

                return tool_call
            else:
                logger.error(f"No valid JSON in iterative response: {response_str}")
                return None

        except Exception as e:
            logger.error(f"Error generating iterative tool call: {e}")
            return None

    def learn_from_user_feedback(self, original_code: str, user_feedback: str, context_file: str):
        """Learn from user feedback to improve future iterations."""
        feedback = CodeFeedback(
            original_code=original_code,
            user_comment=user_feedback,
            feedback_type=self._classify_feedback_type(user_feedback),
            context_file=context_file
        )

        self.code_feedback_history.append(feedback)

        # Extract patterns from feedback
        self._extract_patterns_from_feedback(feedback)

        logger.info(f"Learned from feedback: {feedback.feedback_type}")

    def _analyze_goal_and_set_context(self, goal: str):
        """Analyze the goal and set up appropriate context."""
        goal_lower = goal.lower()

        # Detect what kind of system they're building
        if any(word in goal_lower for word in ['api', 'endpoint', 'rest', 'flask', 'fastapi']):
            self.iteration_context.user_preferences['architecture'] = 'web_api'
        elif any(word in goal_lower for word in ['cli', 'command line', 'script']):
            self.iteration_context.user_preferences['architecture'] = 'cli_tool'
        elif any(word in goal_lower for word in ['class', 'oop', 'object']):
            self.iteration_context.user_preferences['paradigm'] = 'object_oriented'
        elif any(word in goal_lower for word in ['function', 'functional']):
            self.iteration_context.user_preferences['paradigm'] = 'functional'

    def _analyze_refinement_type(self, user_input: str) -> str:
        """Analyze what type of refinement the user is requesting."""
        input_lower = user_input.lower()

        # Error fixing
        if any(word in input_lower for word in ['error', 'exception', 'traceback', 'broken', 'fix', 'bug']):
            return "error_fix"

        # Style/pattern adjustments
        if any(word in input_lower for word in ['style', 'pattern', 'prefer', 'instead', 'rather', 'like this']):
            return "style_adjustment"

        # Improvements
        if any(word in input_lower for word in ['improve', 'better', 'optimize', 'enhance', 'add', 'handle']):
            return "improvement_request"

        # Direct corrections
        if any(word in input_lower for word in ['wrong', 'incorrect', 'should be', 'change', 'correct']):
            return "code_correction"

        return "general_iteration"

    def _extract_correction_context(self, user_input: str) -> str:
        """Extract what the user wants corrected."""
        # Look for specific mentions of code elements
        code_patterns = re.findall(r'`([^`]+)`', user_input)
        if code_patterns:
            return f"Code elements mentioned: {', '.join(code_patterns)}"

        # Look for function/class references
        func_patterns = re.findall(r'\b(def\s+\w+|class\s+\w+|\w+\(\))', user_input)
        if func_patterns:
            return f"Functions/classes mentioned: {', '.join(func_patterns)}"

        return user_input

    def _extract_error_info(self, user_input: str) -> str:
        """Extract error information from user input."""
        # Look for common error patterns
        error_patterns = [
            r'(\w*Error: [^\n]+)',
            r'(Traceback[^\n]+)',
            r'(\w+Exception: [^\n]+)'
        ]

        for pattern in error_patterns:
            matches = re.findall(pattern, user_input)
            if matches:
                return matches[0]

        return user_input[:200]

    def _extract_improvement_focus(self, user_input: str) -> str:
        """Extract what aspect the user wants to improve."""
        input_lower = user_input.lower()

        if 'error handling' in input_lower or 'exception' in input_lower:
            return "error_handling"
        elif 'performance' in input_lower or 'optimize' in input_lower:
            return "performance"
        elif 'readable' in input_lower or 'clean' in input_lower:
            return "readability"
        elif 'test' in input_lower:
            return "testing"
        else:
            return "general_improvement"

    def _extract_style_preference(self, user_input: str) -> Dict[str, str]:
        """Extract style preferences from user input."""
        preferences = {}

        input_lower = user_input.lower()

        # Function vs class preference
        if 'prefer functions' in input_lower or 'functional' in input_lower:
            preferences['paradigm'] = 'functional'
        elif 'prefer classes' in input_lower or 'oop' in input_lower:
            preferences['paradigm'] = 'object_oriented'

        # Error handling style
        if 'try/except' in input_lower:
            preferences['error_handling'] = 'try_except'
        elif 'if/else' in input_lower:
            preferences['error_handling'] = 'if_else'

        return preferences

    def _update_style_preferences(self, style_preference: Dict[str, str]):
        """Update learned style preferences."""
        self.user_coding_patterns.update(style_preference)

    def _learn_from_correction(self, user_input: str, correction_context: str):
        """Learn patterns from user corrections."""
        # This would analyze the correction and update patterns
        feedback_type = self._classify_feedback_type(user_input)

        feedback = CodeFeedback(
            original_code=self.iteration_context.last_generated_code or "",
            user_comment=user_input,
            feedback_type=feedback_type,
            context_file=list(self.iteration_context.files_being_worked_on)[
                0] if self.iteration_context.files_being_worked_on else "unknown"
        )

        self.code_feedback_history.append(feedback)

    def _classify_feedback_type(self, feedback: str) -> str:
        """Classify the type of feedback."""
        feedback_lower = feedback.lower()

        if any(word in feedback_lower for word in ['wrong', 'incorrect', 'error']):
            return "correction"
        elif any(word in feedback_lower for word in ['better', 'improve', 'prefer']):
            return "improvement"
        elif any(word in feedback_lower for word in ['style', 'pattern']):
            return "style"
        else:
            return "general"

    def _extract_patterns_from_feedback(self, feedback: CodeFeedback):
        """Extract coding patterns from user feedback."""
        # This would use NLP to extract patterns and preferences
        # For now, simple keyword-based extraction
        comment_lower = feedback.user_comment.lower()

        if 'too complex' in comment_lower:
            self.user_coding_patterns['complexity_preference'] = 'simple'
        elif 'add error handling' in comment_lower:
            self.user_coding_patterns['error_handling_important'] = True
        elif 'prefer' in comment_lower:
            # Extract specific preferences
            preference_match = re.search(r'prefer (\w+)', comment_lower)
            if preference_match:
                self.user_coding_patterns['general_preference'] = preference_match.group(1)

    def _format_learned_preferences(self) -> str:
        """Format learned preferences for prompts."""
        if not self.user_coding_patterns:
            return "No specific preferences learned yet."

        formatted = []
        for key, value in self.user_coding_patterns.items():
            formatted.append(f"- {key}: {value}")

        return "\n".join(formatted)

    def _get_current_working_files(self) -> List[str]:
        """Get files currently being worked on."""
        return list(self.iteration_context.files_being_worked_on)

    async def _get_smart_code_context(self, query: str, relevant_files: List[str]) -> str:
        """Get smart code context for the query."""
        if not self.vector_context_service:
            return "No code context available."

        # Use smart query if available
        if hasattr(self.vector_context_service, 'smart_query'):
            results = self.vector_context_service.smart_query(
                query_text=query,
                intent="refactor",  # Since we're iterating/refining
                current_file=relevant_files[0] if relevant_files else None,
                n_results=5
            )

            if results:
                context_parts = []
                for result in results:
                    metadata = result.get('metadata', {})
                    document = result.get('document', '')
                    context_parts.append(f"From {metadata.get('file_path', 'unknown')}:\n```python\n{document}\n```")

                return "\n\n".join(context_parts)

        # Fallback to regular context
        return self.vector_context_service.get_relevant_context(query, relevant_files[0] if relevant_files else None)

    def _post_message(self, message: str):
        """Post a message to the user."""
        self.event_bus.emit("post_structured_message", AuraMessage.agent_response(message))

    def track_generated_code(self, code: str, file_path: str):
        """Track code that was just generated for learning purposes."""
        self.iteration_context.last_generated_code = code
        self.iteration_context.files_being_worked_on.add(file_path)

    def get_session_summary(self) -> str:
        """Get a summary of the current iterative session."""
        stats = {
            "goal": self.iteration_context.current_goal,
            "iterations": len(self.iteration_context.iteration_history),
            "files_worked_on": len(self.iteration_context.files_being_worked_on),
            "patterns_learned": len(self.user_coding_patterns),
            "feedback_received": len(self.code_feedback_history)
        }

        return f"""
**Iterative Development Session Summary**
- Goal: {stats['goal']}
- Iterations completed: {stats['iterations']}
- Files worked on: {stats['files_worked_on']}
- Coding patterns learned: {stats['patterns_learned']}
- User feedback processed: {stats['feedback_received']}
        """.strip()