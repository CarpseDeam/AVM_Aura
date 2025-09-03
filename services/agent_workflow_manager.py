from __future__ import annotations
import json
import re
from typing import TYPE_CHECKING, Dict, List, Any, Generator, AsyncGenerator

from core.prompt_templates.creative import CreativeAssistantPrompt
from core.prompt_templates.iterative_architect import IterativeArchitectPrompt
from core.models.messages import AuraMessage, MessageType
from core.stream_parser import parse_llm_stream_async

if TYPE_CHECKING:
    from core.managers.service_manager import ServiceManager
    from event_bus import EventBus


class AgentWorkflowManager:
    """
    Manages and executes agent workflows.
    """

    def __init__(self, llm_client: Any, service_manager: "ServiceManager", event_bus: "EventBus"):
        self.llm_client = llm_client
        self.service_manager = service_manager
        self.event_bus = event_bus
        self.project_manager = service_manager.project_manager
        self.mission_log_service = service_manager.mission_log_service
        self.foundry_manager = service_manager.get_foundry_manager()
        self.tool_runner_service = service_manager.tool_runner_service

        self._agent_workflows = {
            "CREATIVE_ASSISTANT": {
                "prompt_class": CreativeAssistantPrompt,
                "role": "planner",
                "handler": self._run_creative_assistant_workflow,
            },
            "ITERATIVE_ARCHITECT": {
                "prompt_class": IterativeArchitectPrompt,
                "role": "architect",
                "handler": self._run_iterative_architect_workflow,
            },
            "GENERAL_CHAT": {
                "prompt_class": None,
                "role": "chat",
                "handler": self._run_general_chat_workflow,
            },
        }

    async def run_workflow(self, agent_key: str, user_idea: str, conversation_history: list):
        """
        Runs the specified agent workflow.
        """
        workflow = self._agent_workflows.get(agent_key)
        if not workflow:
            self.handle_error("AgentWorkflowManager", f"Unknown agent key: {agent_key}")
            return

        handler = workflow["handler"]
        await handler(user_idea, conversation_history)

    def _post_structured_message(self, message: AuraMessage):
        """Post a structured message to the command deck"""
        if message.content and message.content.strip():
            self.event_bus.emit("post_structured_message", message)
    
    def _post_chat_message(self, sender: str, message: str, is_error: bool = False):
        """Legacy method - converts to structured message"""
        if message and message.strip():
            if is_error:
                structured_msg = AuraMessage.error(message)
            else:
                structured_msg = AuraMessage.agent_response(message)
            self._post_structured_message(structured_msg)

    def handle_error(self, agent: str, error_msg: str):
        self.log("error", f"{agent} failed: {error_msg}")
        self.event_bus.emit("agent_status_changed", "Aura", "Failed", "fa5s.exclamation-triangle")
        self._post_structured_message(AuraMessage.error(error_msg))

    def log(self, level: str, message: str):
        self.event_bus.emit("log_message_received", "AgentWorkflowManager", level, message)

    async def _run_general_chat_workflow(self, user_idea: str, conversation_history: list):
        self.log("info", "Handling general chat.")
        self.event_bus.emit("agent_status_changed", "Aura", "Thinking...", "fa5s.comment-dots")
        provider, model = self.llm_client.get_model_for_role("chat")
        if not provider or not model:
            self.handle_error("Aura", "No 'chat' model configured.")
            return

        history = conversation_history + [{"role": "user", "content": user_idea}]
        prompt = """You are Aura...""" # Simplified for brevity
        
        self.event_bus.emit("processing_started")
        try:
            stream_chunks = self.llm_client.stream_chat(provider, model, prompt, "chat", history=history)
            async for message in parse_llm_stream_async(stream_chunks):
                self._post_structured_message(message)
        except Exception as e:
            self.handle_error("Aura", f"Chat workflow failed: {str(e)}")
        finally:
            self.event_bus.emit("processing_finished")

    async def _run_creative_assistant_workflow(self, user_idea: str, conversation_history: list):
        self.log("info", f"Creative assistant workflow initiated for: '{user_idea[:50]}...'")
        self.event_bus.emit("agent_status_changed", "Aura", "Brainstorming ideas...", "fa5s.lightbulb")
        provider, model = self.llm_client.get_model_for_role("planner")
        if not provider or not model:
            self.handle_error("Aura", "No 'planner' model configured.")
            return

        prompt_template = CreativeAssistantPrompt()
        prompt = prompt_template.render(user_idea=user_idea, conversation_history="")

        self.event_bus.emit("processing_started")
        try:
            stream_chunks = self.llm_client.stream_chat(provider, model, prompt, "planner")
            
            async for message in parse_llm_stream_async(stream_chunks):
                if message.type == MessageType.AGENT_PLAN_JSON:
                    try:
                        from events import PlanReadyForReview
                        response_data = json.loads(message.content)
                        
                        if "thought" in response_data:
                            self._post_structured_message(AuraMessage.agent_thought(response_data["thought"]))

                        new_tasks = response_data.get("plan", [])
                        if new_tasks:
                            for task in new_tasks:
                                self.mission_log_service.add_task(task)
                            self._post_chat_message("Aura", "I've created a plan to get started. Please review the tasks in the 'Agent TODO' list.")
                            self.event_bus.emit("plan_ready_for_review", PlanReadyForReview())

                    except (ValueError, json.JSONDecodeError) as e:
                        self.handle_error("Aura", f"Failed to parse the creative plan: {e}")
                else:
                    self._post_structured_message(message)

        except Exception as e:
            self.handle_error("Aura", f"Creative assistant workflow failed: {str(e)}")
        finally:
            self.event_bus.emit("processing_finished")

    async def _run_iterative_architect_workflow(self, user_request: str, conversation_history: list):
        self.log("info", f"Iterative architect workflow initiated for: '{user_request[:50]}...'")
        self.event_bus.emit("agent_status_changed", "Aura", "Updating the plan...", "fa5s.pencil-ruler")
        provider, model = self.llm_client.get_model_for_role("architect")
        if not provider or not model:
            self.handle_error("Aura", "No 'architect' model configured.")
            return

        file_structure = "\n".join(sorted(self.project_manager.get_project_files().keys())) or "The project is currently empty."
        available_tools = json.dumps(self.foundry_manager.get_llm_tool_definitions(), indent=2)
        prompt_template = IterativeArchitectPrompt()
        prompt = prompt_template.render(user_request=user_request, file_structure=file_structure, relevant_code_snippets="", available_tools=available_tools)

        self.event_bus.emit("processing_started")
        try:
            stream_chunks = self.llm_client.stream_chat(provider, model, prompt, "architect")
            
            async for message in parse_llm_stream_async(stream_chunks):
                if message.type == MessageType.AGENT_PLAN_JSON:
                    try:
                        from events import PlanReadyForReview
                        response_data = json.loads(message.content)

                        if "thought" in response_data:
                            self._post_structured_message(AuraMessage.agent_thought(response_data["thought"]))

                        new_tasks = response_data.get("plan", [])
                        if new_tasks:
                            for task in new_tasks:
                                self.mission_log_service.add_task(task)
                            self._post_chat_message("Aura", "I've updated the plan with your requested changes. Please review the new tasks in the 'Agent TODO' list.")
                            self.event_bus.emit("plan_ready_for_review", PlanReadyForReview())

                    except (ValueError, json.JSONDecodeError) as e:
                        self.handle_error("Aura", f"Failed to parse the updated plan: {e}")
                else:
                    self._post_structured_message(message)

        except Exception as e:
            self.handle_error("Aura", f"Iterative architect workflow failed: {str(e)}")
        finally:
            self.event_bus.emit("processing_finished")
