"""
Agent Workflow Manager - Fixed version with proper chat handling
"""
import json
import logging
from typing import TYPE_CHECKING, List, Dict, Any

from core.models.messages import AuraMessage, MessageType
from core.prompt_templates import CreativeAssistantPrompt, IterativeArchitectPrompt
from event_bus import EventBus


if TYPE_CHECKING:
    from services import MissionLogService
    from core.managers import ProjectManager
    from foundry import FoundryManager

logger = logging.getLogger(__name__)


class AgentWorkflowManager:
    """
    Manages different agent workflows for various types of interactions.
    Fixed to properly handle simple chat messages.
    """

    def __init__(
            self,
            event_bus: EventBus,
            llm_client: "LLMClient",
            mission_log_service: "MissionLogService",
            project_manager: "ProjectManager",
            foundry_manager: "FoundryManager"
    ):
        self.event_bus = event_bus
        self.llm_client = llm_client
        self.mission_log_service = mission_log_service
        self.project_manager = project_manager
        self.foundry_manager = foundry_manager

        # Define available workflows
        self._agent_workflows = {
            "GENERAL_CHAT": {
                "name": "General Chat",
                "handler": self._run_general_chat_workflow
            },
            "CREATIVE_ASSISTANT": {
                "name": "Creative Assistant",
                "handler": self._run_creative_assistant_workflow
            },
            "ITERATIVE_ARCHITECT": {
                "name": "Iterative Architect",
                "handler": self._run_iterative_architect_workflow
            }
        }

        logger.info("AgentWorkflowManager initialized with chat fix")

    async def run_workflow(self, agent_key: str, user_idea: str, conversation_history: List[Dict]) -> None:
        """
        Run a specific workflow based on the agent key.
        """
        workflow = self._agent_workflows.get(agent_key)
        if not workflow:
            self.handle_error("AgentWorkflowManager", f"Unknown agent key: {agent_key}")
            return

        handler = workflow["handler"]
        await handler(user_idea, conversation_history)

    async def _run_general_chat_workflow(self, user_idea: str, conversation_history: List[Dict]) -> None:
        """
        Handle general chat interactions with improved response generation.
        """
        try:
            self.log("info", f"Handling general chat for: '{user_idea[:50]}...'")
            self.event_bus.emit("agent_status_changed", "Aura", "Thinking...", "fa5s.comment-dots")

            # Get chat model
            provider, model = self.llm_client.get_model_for_role("chat")
            if not provider or not model:
                # Fallback to any available model
                models = self.llm_client.get_available_models()
                if models:
                    provider = list(models.keys())[0]
                    model = models[provider][0] if models[provider] else None

                if not provider or not model:
                    self.handle_error("Aura", "No AI models configured. Please configure models first.")
                    return

            # Build conversation context
            history = conversation_history + [{"role": "user", "content": user_idea}]

            # Create an engaging chat prompt
            prompt = self._build_chat_prompt(user_idea, conversation_history)

            self.event_bus.emit("processing_started")

            try:
                # Stream the response
                response_text = ""
                has_content = False

                stream_chunks = self.llm_client.stream_chat(provider, model, prompt, "chat", history=history)

                # Collect and display response
                async for chunk in stream_chunks:
                    if chunk and chunk.strip():
                        response_text += chunk
                        has_content = True

                # Post the complete response
                if has_content and response_text.strip():
                    self._post_structured_message(AuraMessage.agent_response(response_text.strip()))
                else:
                    # Fallback response if nothing was generated
                    fallback_response = self._generate_fallback_response(user_idea)
                    self._post_structured_message(AuraMessage.agent_response(fallback_response))

            except Exception as e:
                self.log("error", f"Stream processing error: {e}")
                # Provide a helpful error response
                error_response = (
                    "I encountered a small hiccup while processing that. "
                    "Let me try again - what would you like to talk about or build?"
                )
                self._post_structured_message(AuraMessage.agent_response(error_response))

        except Exception as e:
            self.handle_error("Aura", f"Chat workflow error: {str(e)}")
        finally:
            self.event_bus.emit("processing_finished")
            self.event_bus.emit("agent_status_changed", "Aura", "Ready", "fa5s.check-circle")

    def _build_chat_prompt(self, user_input: str, history: List[Dict]) -> str:
        """
        Build an effective chat prompt that ensures good responses.
        """
        # Format recent history
        recent_history = ""
        if history:
            for msg in history[-5:]:  # Last 5 messages
                role = "Human" if msg.get("role") == "user" else "Assistant"
                recent_history += f"{role}: {msg.get('content', '')}\n"

        prompt = f"""You are Aura, an enthusiastic and helpful AI coding assistant. You love helping developers build amazing software!

Your personality traits:
- Friendly, encouraging, and supportive
- Expert in software development
- Clear and concise in explanations
- Enthusiastic about solving problems
- Always ready to help with coding or chat

{f"Recent conversation:{recent_history}" if recent_history else "This is the start of our conversation."}"""