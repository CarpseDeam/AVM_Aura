from __future__ import annotations
import json
import re
from typing import TYPE_CHECKING, Dict, List, Any

from core.prompt_templates.creative import CreativeAssistantPrompt
from core.prompt_templates.iterative_architect import IterativeArchitectPrompt

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

    def _post_chat_message(self, sender: str, message: str, is_error: bool = False):
        from events import PostChatMessage
        if message and message.strip():
            self.event_bus.emit("post_chat_message", PostChatMessage(sender, message, is_error))

    def _parse_json_response(self, response: str) -> dict:
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if not match:
            raise ValueError(f"No JSON object found in the response. Raw response: {response}")
        return json.loads(match.group(0))

    def handle_error(self, agent: str, error_msg: str):
        self.log("error", f"{agent} failed: {error_msg}")
        self.event_bus.emit("agent_status_changed", "Aura", "Failed", "fa5s.exclamation-triangle")
        self._post_chat_message("Aura", error_msg, is_error=True)

    def log(self, level: str, message: str):
        self.event_bus.emit("log_message_received", "AgentWorkflowManager", level, message)

    async def _run_general_chat_workflow(self, user_idea: str, conversation_history: list):
        """Handles a general conversational turn that isn't a direct command."""
        self.log("info", "Handling general chat.")
        self.event_bus.emit("agent_status_changed", "Aura", "Thinking...", "fa5s.comment-dots")

        provider, model = self.llm_client.get_model_for_role("chat")
        if not provider or not model:
            self.handle_error("Aura", "No 'chat' model configured.")
            return

        history = conversation_history + [{"role": "user", "content": user_idea}]
        prompt = "You are Aura, a helpful AI assistant. Respond to the user conversationally."
        
        response_str = "".join(
            [chunk async for chunk in self.llm_client.stream_chat(provider, model, prompt, "chat", history=history)])
        
        self._post_chat_message("Aura", response_str)

    async def _run_creative_assistant_workflow(self, user_idea: str, conversation_history: list):
        """
        Handles the initial brainstorming and collaborative planning with the user.
        """
        self.log("info", f"Creative assistant workflow initiated for: '{user_idea[:50]}...'")
        self.event_bus.emit("agent_status_changed", "Aura", "Brainstorming ideas...", "fa5s.lightbulb")

        provider, model = self.llm_client.get_model_for_role("planner")
        if not provider or not model:
            self.handle_error("Aura", "No 'planner' model configured.")
            return

        prompt_template = CreativeAssistantPrompt()
        conv_history_str = "\n".join([f"{msg['role']}: {msg['content']}" for msg in conversation_history])
        prompt = prompt_template.render(user_idea=user_idea, conversation_history=conv_history_str)

        response_str = "".join(
            [chunk async for chunk in self.llm_client.stream_chat(provider, model, prompt, "planner")])

        tool_call_match = re.search(r'\[TOOL_CALL\](.*?)\[/TOOL_CALL\]', response_str, re.DOTALL)
        conversational_text = re.sub(r'\[TOOL_CALL\].*?\[/TOOL_CALL\]', '', response_str).strip()

        if conversational_text:
            self._post_chat_message("Aura", conversational_text)

        if tool_call_match:
            try:
                from events import PlanReadyForReview
                tool_call_str = tool_call_match.group(1)
                tool_call_data = json.loads(tool_call_str)
                self.log("info", f"Creative assistant identified a task: {tool_call_data}")
                await self.tool_runner_service.run_tool_by_dict(tool_call_data)
                self.event_bus.emit("plan_ready_for_review", PlanReadyForReview())
            except (json.JSONDecodeError, KeyError) as e:
                self.handle_error("Aura", f"Invalid tool call format from creative assistant: {e}")
                self.log("error", f"Creative assistant tool call failure. Raw block: {tool_call_match.group(0)}")

    async def _run_iterative_architect_workflow(self, user_request: str, conversation_history: list):
        """
        Handles a user's request to modify an existing plan or codebase.
        """
        self.log("info", f"Iterative architect workflow initiated for: '{user_request[:50]}...'")
        self.event_bus.emit("agent_status_changed", "Aura", "Updating the plan...", "fa5s.pencil-ruler")

        provider, model = self.llm_client.get_model_for_role("architect")
        if not provider or not model:
            self.handle_error("Aura", "No 'architect' model configured.")
            return

        file_structure = "\n".join(sorted(self.project_manager.get_project_files().keys())) or "The project is currently empty."
        available_tools = json.dumps(self.foundry_manager.get_llm_tool_definitions(), indent=2)
        
        relevant_code_snippets = "No relevant code snippets were retrieved for this modification."

        prompt_template = IterativeArchitectPrompt()
        prompt = prompt_template.render(
            user_request=user_request,
            file_structure=file_structure,
            relevant_code_snippets=relevant_code_snippets,
            available_tools=available_tools
        )

        response_str = "".join(
            [chunk async for chunk in self.llm_client.stream_chat(provider, model, prompt, "architect")])

        try:
            from events import PlanReadyForReview
            response_data = self._parse_json_response(response_str)
            new_tasks = response_data.get("plan", [])
            if not new_tasks:
                raise ValueError("Iterative architect returned an empty plan.")

            for task in new_tasks:
                self.mission_log_service.add_task(task)
            
            self._post_chat_message("Aura", "I've updated the plan with your requested changes. Please review the new tasks in the 'Agent TODO' list.")
            self.event_bus.emit("plan_ready_for_review", PlanReadyForReview())

        except (ValueError, json.JSONDecodeError) as e:
            self.handle_error("Aura", f"Failed to update the plan: {e}")
            self.log("error", f"Iterative architect failure. Raw response: {response_str}")
