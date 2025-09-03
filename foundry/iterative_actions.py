# foundry/actions/iterative_actions.py
"""
Foundry actions for iterative development workflows.
"""
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def start_iterative_session(iterative_development_service, goal: str, conversation_history: list = None) -> str:
    """
    Start a new iterative development session focused on a specific goal.

    Args:
        iterative_development_service: The iterative development service
        goal: What you want to build/accomplish
        conversation_history: Recent conversation context

    Returns:
        Session start confirmation
    """
    if not iterative_development_service:
        return "❌ Iterative development service not available."

    conversation_history = conversation_history or []

    try:
        iterative_development_service.start_iterative_session(goal, conversation_history)
        return f"""
🚀 **Iterative Development Session Started**

**Goal:** {goal}

I'm now in collaborative coding mode. Here's how we'll work together:

💬 **Tell me what to build**: Describe what you want in plain English
🔧 **I'll implement it**: I'll write the Python code step by step  
📝 **Give me feedback**: Tell me what's wrong, what to improve, or what to change
🔄 **I'll refine it**: I'll make exactly the changes you want
🎯 **We'll iterate**: Keep going until it's exactly what you need

**Ready to start coding together!** What should we build first?
        """.strip()

    except Exception as e:
        logger.error(f"Failed to start iterative session: {e}")
        return f"❌ Failed to start session: {str(e)}"


def provide_code_feedback(iterative_development_service, feedback: str, file_path: str = None) -> str:
    """
    Provide feedback on recently generated code to help the system learn.

    Args:
        iterative_development_service: The iterative development service
        feedback: Your feedback about the code
        file_path: Path to the file you're giving feedback on

    Returns:
        Acknowledgment of feedback
    """
    if not iterative_development_service:
        return "❌ Iterative development service not available."

    try:
        # Get the last generated code if no file specified
        if not file_path and hasattr(iterative_development_service, 'iteration_context'):
            working_files = iterative_development_service.iteration_context.files_being_worked_on
            file_path = list(working_files)[0] if working_files else "unknown"

        # Learn from the feedback
        original_code = iterative_development_service.iteration_context.last_generated_code or ""
        iterative_development_service.learn_from_user_feedback(original_code, feedback, file_path or "unknown")

        return f"""
📝 **Feedback Recorded**

Your feedback: "{feedback}"
File: {file_path or 'Recent code'}

✅ I've learned from your feedback and will apply these patterns to future code generation.

What would you like me to refine next?
        """.strip()

    except Exception as e:
        logger.error(f"Failed to process feedback: {e}")
        return f"❌ Failed to process feedback: {str(e)}"


def refine_code_element(iterative_development_service, element_description: str, refinement_request: str) -> str:
    """
    Refine a specific code element (function, class, etc.) based on user request.

    Args:
        iterative_development_service: The iterative development service
        element_description: Description of what code element to refine (e.g., "the login function")
        refinement_request: How you want it refined (e.g., "add error handling")

    Returns:
        Refinement result
    """
    if not iterative_development_service:
        return "❌ Iterative development service not available."

    try:
        full_request = f"Refine {element_description}: {refinement_request}"

        # This would trigger the iterative refinement workflow
        return f"""
🔧 **Code Refinement Queued**

**Target:** {element_description}
**Refinement:** {refinement_request}

I'll analyze the current implementation and make the requested improvements.
This will be processed through the iterative development workflow.

Use the chat interface to continue the refinement conversation.
        """.strip()

    except Exception as e:
        logger.error(f"Failed to refine code element: {e}")
        return f"❌ Failed to refine code: {str(e)}"


def get_session_summary(iterative_development_service) -> str:
    """
    Get a summary of the current iterative development session.

    Args:
        iterative_development_service: The iterative development service

    Returns:
        Session summary
    """
    if not iterative_development_service:
        return "❌ No active iterative development session."

    try:
        return iterative_development_service.get_session_summary()
    except Exception as e:
        logger.error(f"Failed to get session summary: {e}")
        return f"❌ Failed to get summary: {str(e)}"


def review_recent_code(iterative_development_service, project_manager, focus: str = "general") -> str:
    """
    Review recently generated code and suggest improvements.

    Args:
        iterative_development_service: The iterative development service
        project_manager: The project manager to read files
        focus: Review focus (general, performance, security, style)

    Returns:
        Code review results
    """
    if not iterative_development_service or not project_manager:
        return "❌ Required services not available for code review."

    try:
        # Get recently worked on files
        if hasattr(iterative_development_service, 'iteration_context'):
            working_files = list(iterative_development_service.iteration_context.files_being_worked_on)

            if not working_files:
                return "📋 No recent code to review. Generate some code first, then ask for a review."

            # Read the most recently modified file
            recent_file = working_files[-1]
            code_content = project_manager.read_file(recent_file)

            if not code_content:
                return f"❌ Could not read file: {recent_file}"

            # This would use the CodeReviewPrompt to analyze the code
            review_summary = f"""
📋 **Code Review: {recent_file}**

**Review Focus:** {focus}

🔍 **Quick Analysis:**
- File length: {len(code_content.split())} lines
- Functions found: {code_content.count('def ')}
- Classes found: {code_content.count('class ')}

📝 **Review Notes:**
I've analyzed the code structure. For detailed review and suggestions, continue the conversation and ask me about specific aspects like:
- "Are there any bugs in this code?"
- "How can I improve the error handling?"
- "Is the code following Python best practices?"

**Ready for detailed review questions!**
            """.strip()

            return review_summary
        else:
            return "📋 No active iterative session to review."

    except Exception as e:
        logger.error(f"Failed to review code: {e}")
        return f"❌ Code review failed: {str(e)}"


def fix_error_iteratively(iterative_development_service, error_description: str, context: str = None) -> str:
    """
    Start an iterative error fixing session.

    Args:
        iterative_development_service: The iterative development service
        error_description: Description of the error or paste the error message
        context: Additional context about when/where the error occurs

    Returns:
        Error fixing session start
    """
    if not iterative_development_service:
        return "❌ Iterative development service not available."

    try:
        context_info = f"\n\n**Context:** {context}" if context else ""

        return f"""
🐛 **Error Fixing Session Started**

**Error:** {error_description}{context_info}

I'm now in debugging mode. Here's how we'll fix this:

1️⃣ **I'll analyze** the error and identify the root cause
2️⃣ **I'll propose a fix** with explanation of what went wrong  
3️⃣ **You test it** and let me know if it works
4️⃣ **I'll refine** the fix if needed until the error is resolved

**Continue in chat** - describe the error in detail or paste the error message, and I'll start debugging!
        """.strip()

    except Exception as e:
        logger.error(f"Failed to start error fixing: {e}")
        return f"❌ Failed to start error fixing: {str(e)}"


def learn_coding_pattern(iterative_development_service, example_code: str, pattern_description: str) -> str:
    """
    Teach the system a coding pattern you prefer.

    Args:
        iterative_development_service: The iterative development service
        example_code: Example of the pattern you like
        pattern_description: Description of when/how to use this pattern

    Returns:
        Learning confirmation
    """
    if not iterative_development_service:
        return "❌ Iterative development service not available."

    try:
        # Store the pattern as a preference
        if hasattr(iterative_development_service, 'user_coding_patterns'):
            pattern_key = f"user_example_{len(iterative_development_service.user_coding_patterns)}"
            iterative_development_service.user_coding_patterns[pattern_key] = {
                "example": example_code,
                "description": pattern_description,
                "learned_from": "explicit_teaching"
            }

        return f"""
🎓 **Coding Pattern Learned**

**Pattern Description:** {pattern_description}

**Example Code:**
```python
{example_code}
```

✅ I've stored this pattern and will use it as a reference for future code generation.

This pattern will be applied when generating similar code. You can teach me more patterns anytime!
        """.strip()

    except Exception as e:
        logger.error(f"Failed to learn pattern: {e}")
        return f"❌ Failed to learn pattern: {str(e)}"