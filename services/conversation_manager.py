"""
Conversation Manager - Central hub for all conversational interactions
Handles routing, context management, and conversation flow
"""
import logging
import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from enum import Enum

from core.models.messages import AuraMessage, MessageType
from event_bus import EventBus


class ConversationIntent(Enum):
    """Categorizes user intent for proper routing"""
    GREETING = "greeting"
    CASUAL_CHAT = "casual_chat"
    PLANNING = "planning"
    CODING = "coding"
    ARCHITECTURE = "architecture"
    DEBUGGING = "debugging"
    CLARIFICATION = "clarification"
    BUILD_REQUEST = "build_request"


@dataclass
class ConversationContext:
    """Maintains conversation state and context"""
    current_topic: Optional[str] = None
    current_intent: Optional[ConversationIntent] = None
    active_project_context: Dict[str, Any] = field(default_factory=dict)
    pending_clarifications: List[str] = field(default_factory=list)
    conversation_depth: int = 0
    last_code_context: Optional[str] = None


class ConversationManager:
    """
    Manages all conversational interactions between user and AI assistant.
    Provides intelligent routing and context-aware responses.
    """

    def __init__(self, event_bus: EventBus, llm_client, project_manager):
        self.event_bus = event_bus
        self.llm_client = llm_client
        self.project_manager = project_manager
        self.context = ConversationContext()
        self.logger = logging.getLogger(__name__)

        self.greeting_phrases = {
            "hi", "hello", "hey", "howdy", "greetings", "good morning",
            "good afternoon", "good evening", "sup", "what's up"
        }

        self.coding_keywords = {
            "code", "implement", "function", "class", "method", "api",
            "database", "frontend", "backend", "algorithm", "data structure"
        }

        self.planning_keywords = {
            "plan", "design", "architect", "structure", "organize",
            "brainstorm", "ideas", "approach", "strategy"
        }

    async def process_message(self, message: str, conversation_history: List[Dict]) -> None:
        """
        Main entry point for processing user messages.
        Analyzes intent and routes to appropriate handler.
        """
        self.logger.info(f"Processing message: {message[:50]}...")

        # Analyze user intent
        intent = self._analyze_intent(message, conversation_history)
        self.context.current_intent = intent
        self.context.conversation_depth = len(conversation_history)

        # Update status
        self._update_agent_status(intent)

        try:
            # Route based on intent
            if intent == ConversationIntent.GREETING:
                await self._handle_greeting(message)
            elif intent == ConversationIntent.CASUAL_CHAT:
                await self._handle_casual_chat(message, conversation_history)
            elif intent == ConversationIntent.PLANNING:
                await self._handle_planning_request(message, conversation_history)
            elif intent == ConversationIntent.CODING:
                await self._handle_coding_request(message, conversation_history)
            elif intent == ConversationIntent.ARCHITECTURE:
                await self._handle_architecture_discussion(message, conversation_history)
            elif intent == ConversationIntent.DEBUGGING:
                await self._handle_debugging_request(message, conversation_history)
            elif intent == ConversationIntent.BUILD_REQUEST:
                await self._handle_build_request(message, conversation_history)
            else:
                await self._handle_general_conversation(message, conversation_history)

        except Exception as e:
            self.logger.error(f"Error processing message: {e}")
            self._post_error(f"I encountered an issue processing your message: {str(e)}")

    def _analyze_intent(self, message: str, _history: List[Dict]) -> ConversationIntent:
        """
        Analyzes user message to determine intent.
        Uses both keyword matching and context awareness.
        """
        message_lower = message.lower().strip()

        # Check for greetings
        if any(greeting in message_lower.split() for greeting in self.greeting_phrases):
            if self.context.conversation_depth == 0:
                return ConversationIntent.GREETING
            else:
                return ConversationIntent.CASUAL_CHAT

        # Check for explicit build/create requests
        if any(keyword in message_lower for keyword in ["build", "create", "make", "develop"]):
            if any(keyword in message_lower for keyword in self.coding_keywords):
                return ConversationIntent.BUILD_REQUEST

        # Check for planning requests
        if any(keyword in message_lower for keyword in self.planning_keywords):
            return ConversationIntent.PLANNING

        # Check for coding-related content
        if any(keyword in message_lower for keyword in self.coding_keywords):
            return ConversationIntent.CODING

        # Check for debugging
        if any(keyword in message_lower for keyword in ["debug", "error", "bug", "fix", "issue"]):
            return ConversationIntent.DEBUGGING

        # Check for architecture discussions
        if any(keyword in message_lower for keyword in ["architecture", "design pattern", "structure"]):
            return ConversationIntent.ARCHITECTURE

        # Check for questions or clarifications
        if "?" in message or any(word in message_lower for word in ["what", "how", "why", "when", "where"]):
            return ConversationIntent.CLARIFICATION

        # Default to casual chat
        return ConversationIntent.CASUAL_CHAT

    async def _handle_greeting(self, _message: str) -> None:
        """Handles initial greetings with a warm, helpful response"""
        response = (
            "Hey there! 👋 I'm Aura, your AI coding companion! I'm here to help you design, "
            "plan, and build amazing software through conversation. \n\n"
            "You can:\n"
            "• Chat with me about your project ideas\n"
            "• Ask me to plan out complex features\n"
            "• Have me write code implementations\n"
            "• Discuss architecture and design patterns\n"
            "• Debug issues together\n\n"
            "What would you like to create today?"
        )
        self._post_message(response, MessageType.AGENT_RESPONSE)

    async def _handle_casual_chat(self, message: str, history: List[Dict]) -> None:
        """Handles casual conversation with context awareness"""
        provider, model = self.llm_client.get_model_for_role("chat")
        if not provider or not model:
            self._post_error("Chat model not configured. Please configure models first.")
            return

        prompt = self._build_chat_prompt(message, history)

        try:
            response_text = ""
            stream = self.llm_client.stream_chat(provider, model, prompt, "chat", history=history)

            async for chunk in stream:
                response_text += chunk

            if response_text.strip():
                self._post_message(response_text, MessageType.AGENT_RESPONSE)
            else:
                self._post_message("I'm here to help! What would you like to work on?", MessageType.AGENT_RESPONSE)

        except Exception as e:
            self.logger.error(f"Chat error: {e}")
            self._post_error("I had trouble generating a response. Let's try again!")

    async def _handle_planning_request(self, message: str, history: List[Dict]) -> None:
        """Handles requests for project planning and brainstorming"""
        provider, model = self.llm_client.get_model_for_role("planner")
        if not provider or not model:
            self._post_error("Planning model not configured. Please configure models first.")
            return

        self._post_message("Let me think about this and create a comprehensive plan for you...",
                           MessageType.AGENT_THOUGHT)

        prompt = self._build_planning_prompt(message, history)

        try:
            stream = self.llm_client.stream_chat(provider, model, prompt, "planner", history=history)
            response_text = ""

            async for chunk in stream:
                response_text += chunk

            # Parse and handle the planning response
            if response_text.strip():
                await self._process_planning_response(response_text)
            else:
                self._post_error("I couldn't generate a proper plan. Could you provide more details?")

        except Exception as e:
            self.logger.error(f"Planning error: {e}")
            self._post_error("I encountered an issue while planning. Let me try a different approach.")

    async def _handle_coding_request(self, message: str, history: List[Dict]) -> None:
        """Handles direct coding requests"""
        self._post_message("I'll help you with that code. Let me work on it...", MessageType.AGENT_THOUGHT)

        # Determine if we need to plan first or can code directly
        if self._needs_planning(message):
            await self._handle_planning_request(message, history)
        else:
            await self._generate_code_response(message, history)

    async def _handle_architecture_discussion(self, message: str, history: List[Dict]) -> None:
        """Handles architecture and design pattern discussions"""
        provider, model = self.llm_client.get_model_for_role("architect")
        if not provider or not model:
            # Fall back to planner if architect not configured
            provider, model = self.llm_client.get_model_for_role("planner")

        if not provider or not model:
            self._post_error("Architecture models not configured.")
            return

        prompt = self._build_architecture_prompt(message, history)

        try:
            stream = self.llm_client.stream_chat(provider, model, prompt, "architect", history=history)
            response_text = ""

            async for chunk in stream:
                response_text += chunk

            if response_text.strip():
                self._post_message(response_text, MessageType.AGENT_RESPONSE)

        except Exception as e:
            self.logger.error(f"Architecture discussion error: {e}")
            self._post_error("Let me reconsider the architecture approach.")

    async def _handle_debugging_request(self, message: str, history: List[Dict]) -> None:
        """Handles debugging and troubleshooting requests"""
        self._post_message("Let's debug this together. I'll analyze the issue...", MessageType.AGENT_THOUGHT)

        # Get current project context if available
        project_files = self.project_manager.get_project_files() if self.project_manager else {}

        prompt = self._build_debugging_prompt(message, history, project_files)

        provider, model = self.llm_client.get_model_for_role("chat")
        if not provider or not model:
            self._post_error("Debugging model not configured.")
            return

        try:
            stream = self.llm_client.stream_chat(provider, model, prompt, "chat", history=history)
            response_text = ""

            async for chunk in stream:
                response_text += chunk

            if response_text.strip():
                self._post_message(response_text, MessageType.AGENT_RESPONSE)

        except Exception as e:
            self.logger.error(f"Debugging error: {e}")
            self._post_error("I encountered an issue while debugging.")

    async def _handle_build_request(self, message: str, history: List[Dict]) -> None:
        """Handles explicit build/create requests"""
        self._post_message("Great! Let's build this together. I'll create a plan first...", MessageType.AGENT_RESPONSE)
        await self._handle_planning_request(message, history)

    async def _handle_general_conversation(self, message: str, history: List[Dict]) -> None:
        """Fallback handler for general conversation"""
        await self._handle_casual_chat(message, history)

    def _build_chat_prompt(self, message: str, history: List[Dict]) -> str:
        """Builds a conversational prompt for chat interactions"""
        return f"""You are Aura, an enthusiastic and helpful AI coding assistant. 
You love discussing software development, sharing ideas, and helping developers.

Your personality:
- Friendly, encouraging, and supportive
- Expert in software development but explain things clearly
- Use analogies and examples to clarify concepts
- Be concise but thorough
- Show enthusiasm for coding and problem-solving

Current conversation context:
{self._format_history(history[-5:])}  # Last 5 messages for context

User says: {message}

Respond naturally and helpfully. If they're asking about coding, be ready to help.
If it's casual conversation, be friendly and engaging."""

    def _build_planning_prompt(self, message: str, history: List[Dict]) -> str:
        """Builds a prompt for planning responses"""
        return f"""You are Aura, an expert software architect and planner.

Create a comprehensive plan for the user's request.

IMPORTANT: Respond with a JSON structure:
{{
    "thought": "Your analysis and reasoning about the request",
    "plan": [
        "Step 1: Clear, actionable task",
        "Step 2: Another clear task",
        ...
    ]
}}

User request: {message}

Context from conversation:
{self._format_history(history[-3:])}

Create an efficient, practical plan that focuses on implementation."""

    @staticmethod
    def _build_architecture_prompt(message: str, _history: List[Dict]) -> str:
        """Builds a prompt for architecture discussions"""
        return f"""You are Aura, an expert software architect.

Discuss architecture, design patterns, and best practices.
Be specific and practical, providing examples where helpful.

User's architecture question: {message}

Provide insights on:
- Design patterns that apply
- Architectural considerations
- Best practices
- Potential pitfalls to avoid
- Scalability and maintainability

Keep your response focused and actionable."""

    @staticmethod
    def _build_debugging_prompt(message: str, _history: List[Dict], project_files: Dict) -> str:
        """Builds a prompt for debugging assistance"""
        files_context = "\n".join(project_files.keys()) if project_files else "No files in project yet"

        return f"""You are Aura, an expert debugger and problem solver.

Help debug the issue described by the user.

Current project files:
{files_context}

User's issue: {message}

Provide:
1. Likely cause of the issue
2. Step-by-step debugging approach
3. Potential solutions
4. Code fixes if applicable

Be systematic and thorough in your debugging approach."""

    async def _generate_code_response(self, message: str, history: List[Dict]) -> None:
        """Generates actual code in response to coding requests"""
        provider, model = self.llm_client.get_model_for_role("coder")
        if not provider or not model:
            provider, model = self.llm_client.get_model_for_role("chat")

        if not provider or not model:
            self._post_error("Coding model not configured.")
            return

        prompt = f"""You are Aura, an expert programmer.

Generate clean, well-structured code for the user's request.
Follow best practices and include helpful comments.

User request: {message}

Provide complete, working code that solves their problem."""

        try:
            stream = self.llm_client.stream_chat(provider, model, prompt, "coder", history=history)
            response_text = ""

            async for chunk in stream:
                response_text += chunk

            if response_text.strip():
                self._post_message(response_text, MessageType.AGENT_RESPONSE)

        except Exception as e:
            self.logger.error(f"Code generation error: {e}")
            self._post_error("I had trouble generating the code. Let me try again.")

    async def _process_planning_response(self, response_text: str) -> None:
        """Processes and formats planning responses"""
        try:
            # Try to parse as JSON first
            if response_text.strip().startswith('{'):
                data = json.loads(response_text)

                if "thought" in data:
                    self._post_message(data["thought"], MessageType.AGENT_THOUGHT)

                if "plan" in data and data["plan"]:
                    # Add tasks to mission log
                    from events import PlanReadyForReview

                    for task in data["plan"]:
                        # Emit event to add task to
                        self.event_bus.emit("add_mission_task", task)

                    self._post_message(
                        f"I've created a comprehensive plan with {len(data['plan'])} steps. "
                        "Check the Agent TODO list to review and execute the tasks!",
                        MessageType.AGENT_RESPONSE
                    )
                    self.event_bus.emit("plan_ready_for_review", PlanReadyForReview())
                else:
                    # No plan in response, treat as regular response
                    self._post_message(response_text, MessageType.AGENT_RESPONSE)
            else:
                # Not JSON, treat as regular response
                self._post_message(response_text, MessageType.AGENT_RESPONSE)

        except json.JSONDecodeError:
            # If not valid JSON, just post as regular response
            self._post_message(response_text, MessageType.AGENT_RESPONSE)

    @staticmethod
    def _needs_planning(message: str) -> bool:
        """Determines if a coding request needs planning first"""
        complexity_indicators = [
            "application", "system", "full", "complete", "entire",
            "project", "multiple", "complex", "architecture"
        ]
        return any(indicator in message.lower() for indicator in complexity_indicators)

    @staticmethod
    def _format_history(history: List[Dict]) -> str:
        """Formats conversation history for prompts"""
        if not history:
            return "No previous conversation"

        formatted = []
        for msg in history:
            role = "User" if msg.get("role") == "user" else "Aura"
            content = msg.get("content", "")[:200]  # Truncate long messages
            formatted.append(f"{role}: {content}")

        return "\n".join(formatted)

    def _update_agent_status(self, intent: ConversationIntent) -> None:
        """Updates agent status based on intent"""
        status_map = {
            ConversationIntent.GREETING: ("Saying hello!", "fa5s.hand-wave"),
            ConversationIntent.CASUAL_CHAT: ("Chatting...", "fa5s.comment-dots"),
            ConversationIntent.PLANNING: ("Planning...", "fa5s.lightbulb"),
            ConversationIntent.CODING: ("Coding...", "fa5s.code"),
            ConversationIntent.ARCHITECTURE: ("Designing...", "fa5s.drafting-compass"),
            ConversationIntent.DEBUGGING: ("Debugging...", "fa5s.bug"),
            ConversationIntent.BUILD_REQUEST: ("Building...", "fa5s.hammer"),
            ConversationIntent.CLARIFICATION: ("Thinking...", "fa5s.question-circle")
        }

        status, icon = status_map.get(intent, ("Processing...", "fa5s.cog"))
        self.event_bus.emit("agent_status_changed", "Aura", status, icon)

    def _post_message(self, content: str, msg_type: MessageType) -> None:
        """Posts a message to the UI"""
        message = AuraMessage(type=msg_type, content=content)
        self.event_bus.emit("post_structured_message", message)

    def _post_error(self, error_msg: str) -> None:
        """Posts an error message"""
        self._post_message(error_msg, MessageType.ERROR)
        self.event_bus.emit("agent_status_changed", "Aura", "Error", "fa5s.exclamation-triangle")