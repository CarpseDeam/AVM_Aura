# services/development_team_service.py
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

from event_bus import EventBus
# Import the new router prompt
from prompts.creative import AURA_PLANNER_PROMPT, CREATIVE_ASSISTANT_PROMPT, AURA_ROUTER_PROMPT
from prompts.coder import CODER_PROMPT
from prompts.master_rules import JSON_OUTPUT_RULE
from services.agents import ReviewerService
from events import PlanReadyForReview, MissionDispatchRequest, PostChatMessage

if TYPE_CHECKING:
    from core.managers.service_manager import ServiceManager


class DevelopmentTeamService:
    """
    Orchestrates the main AI workflows by delegating to specialized services
    like the CoderService and ReviewerService.
    """

    def __init__(self, event_bus: EventBus, service_manager: "ServiceManager"):
        self.event_bus = event_bus
        self.service_manager = service_manager
        self.llm_client = service_manager.get_llm_client()
        self.project_manager = service_manager.get_project_manager()
        self.mission_log_service = service_manager.mission_log_service
        self.vector_context_service = service_manager.vector_context_service
        self.foundry_manager = service_manager.get_foundry_manager()

        self.reviewer = ReviewerService(self.event_bus, self.llm_client)

    def _post_chat_message(self, sender: str, message: str, is_error: bool = False):
        if message and message.strip():
            self.event_bus.emit("post_chat_message", PostChatMessage(sender, message, is_error))

    def _parse_json_response(self, response: str) -> dict:
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if not match:
            raise ValueError("No JSON object found in the response.")
        return json.loads(match.group(0))

    async def _get_user_intent(self, user_idea: str) -> str:
        """Uses the Router prompt to determine if the user needs a planner or a conversational guide."""
        self.log("info", "Routing user intent...")
        prompt = AURA_ROUTER_PROMPT.format(user_idea=user_idea)

        provider, model = self.llm_client.get_model_for_role("chat")
        if not provider or not model:
            self.log("warning", "No 'chat' model configured for router, falling back to 'planner' model.")
            provider, model = self.llm_client.get_model_for_role("planner")

        if not provider or not model:
            self.log("error", "No model available for router. Defaulting to 'planner' intent.")
            return "planner"

        response_str = "".join([chunk async for chunk in self.llm_client.stream_chat(provider, model, prompt, "chat")])

        try:
            intent_data = self._parse_json_response(response_str)
            intent = intent_data.get("intent", "planner")
            self.log("info", f"User intent routed to: '{intent}'")
            return intent
        except (ValueError, json.JSONDecodeError):
            self.log("warning", f"Could not parse router response. Defaulting to 'planner'. Raw: {response_str}")
            return "planner"

    async def run_aura_planner_workflow(self, user_idea: str, conversation_history: list):
        """
        The definitive workflow. It first routes the user's intent and then calls the
        appropriate specialist AI to either generate a plan or start a conversation.
        """
        self.log("info", f"Aura workflow initiated for: '{user_idea[:50]}...'")

        intent = await self._get_user_intent(user_idea)

        provider, model = self.llm_client.get_model_for_role("planner")  # Use planner for main tasks
        if not provider or not model:
            self.handle_error("Aura", "No 'planner' model configured.")
            return

        if intent == "planner":
            self.event_bus.emit("agent_status_changed", "Aura", "Formulating an efficient TDD plan...",
                                "fa5s.lightbulb")
            prompt = AURA_PLANNER_PROMPT.format(
                conversation_history="\n".join([f"{msg['role']}: {msg['content']}" for msg in conversation_history]),
                user_idea=user_idea
            )
            response_str = "".join(
                [chunk async for chunk in self.llm_client.stream_chat(provider, model, prompt, "planner")])
            try:
                plan_data = self._parse_json_response(response_str)
                plan_steps = plan_data.get("plan", [])
                if not plan_steps: raise ValueError("Aura's plan was empty or malformed.")
                self.mission_log_service.set_initial_plan(plan_steps)
                self._post_chat_message("Aura",
                                        "I've created an efficient, Test-Driven Design plan. Please review it in the 'Agent TODO' list and click 'Dispatch Aura' to begin execution.")
                self.event_bus.emit("plan_ready_for_review", PlanReadyForReview())
            except (ValueError, json.JSONDecodeError) as e:
                self.handle_error("Aura", f"Failed to create a valid plan: {e}. Raw response logged for debugging.")
                self.log("error", f"Aura planner failure. Raw response: {response_str}")

        else:  # intent == "conversational"
            self.event_bus.emit("agent_status_changed", "Aura", "Thinking...", "fa5s.comment-dots")
            provider, model = self.llm_client.get_model_for_role("chat")  # Use chat model for conversation
            prompt = CREATIVE_ASSISTANT_PROMPT.format(
                conversation_history="\n".join([f"{msg['role']}: {msg['content']}" for msg in conversation_history]),
                user_idea=user_idea
            )
            response_str = "".join(
                [chunk async for chunk in self.llm_client.stream_chat(provider, model, prompt, "chat")])
            tool_call_match = re.search(r'\[TOOL_CALL\](.*?\[/TOOL_CALL\])', response_str, re.DOTALL)
            conversation_reply = response_str
            if tool_call_match:
                tool_call_str = tool_call_match.group(1).replace("[/TOOL_CALL]", "").strip()
                conversation_reply = response_str[:tool_call_match.start()].strip()
                try:
                    tool_call = json.loads(tool_call_str)
                    if self.service_manager.tool_runner_service:
                        await self.service_manager.tool_runner_service.run_tool_by_dict(tool_call)
                except json.JSONDecodeError as e:
                    self.log("error",
                             f"Failed to parse tool call from conversational response: {e}. Raw block: {tool_call_str}")
            self.log("info", "Posting conversational reply to chat.")
            self._post_chat_message("Aura", conversation_reply)

    async def run_coding_task(
            self,
            task: Dict[str, any]
    ) -> Optional[Dict[str, str]]:
        if task.get("tool_call"):
            self.log("info", f"Using pre-defined tool call for task: {task['description']}")
            return task["tool_call"]

        current_task_description = task['description']
        self.log("info", f"Coder translating task to tool call: {current_task_description}")
        self.event_bus.emit("agent_status_changed", "Aura", f"Coding task: {current_task_description}...", "fa5s.cogs")

        relevant_context = "No existing code snippets were found. You are likely creating a new file or starting a new project."
        try:
            if self.vector_context_service and self.vector_context_service.collection.count() > 0:
                retrieved_chunks = self.vector_context_service.query(current_task_description, n_results=5)
                if retrieved_chunks:
                    context_parts = ["Here are the most relevant code snippets based on the task:\n"]
                    for chunk in retrieved_chunks:
                        metadata = chunk['metadata']
                        source_info = f"From file: {metadata.get('file_path', 'N/A')} ({metadata.get('node_type', 'N/A')}: {metadata.get('node_name', 'N/A')})"
                        context_parts.append(f"```python\n# {source_info}\n{chunk['document']}\n```")
                    relevant_context = "\n\n".join(context_parts)
            else:
                self.log("warning", "Vector database is empty. Proceeding without RAG context.")
        except Exception as e:
            self.log("error", f"Failed to query vector context: {e}")
            relevant_context = f"Error: Could not retrieve context from the vector database. Details: {e}"

        file_structure = "\n".join(
            sorted(list(self.project_manager.get_project_files().keys()))) or "The project is currently empty."
        available_tools = json.dumps(self.foundry_manager.get_llm_tool_definitions(), indent=2)

        # --- *** THE FIX IS HERE *** ---
        # The 'current_task' key was missing from this format call, causing the crash.
        prompt = CODER_PROMPT.format(
            current_task=current_task_description,
            available_tools=available_tools,
            file_structure=file_structure,
            relevant_code_snippets=relevant_context,
            JSON_OUTPUT_RULE=JSON_OUTPUT_RULE.strip()
        )

        provider, model = self.llm_client.get_model_for_role("coder")
        if not provider or not model:
            self.log("error", "No 'coder' model configured.")
            return None

        response_str = "".join([chunk async for chunk in self.llm_client.stream_chat(provider, model, prompt, "coder")])

        try:
            tool_call = self._parse_json_response(response_str)
            if "tool_name" not in tool_call or "arguments" not in tool_call:
                raise ValueError("Coder response must be a JSON object with 'tool_name' and 'arguments' keys.")
            return tool_call
        except (ValueError, json.JSONDecodeError) as e:
            self.log("error", f"Coder generation failure. Raw response: {response_str}. Error: {e}")
            self.handle_error("Aura",
                              f"I failed to generate a valid tool call for the task. The raw response from the AI has been logged for debugging. Error: {e}")
            return None

    async def run_review_and_fix_phase(self, error_report: str, git_diff: str, full_code_context: Dict[str, str]):
        self.log("info", "Review and Fix phase initiated.")
        self.event_bus.emit("agent_status_changed", "Aura", "Analyzing failure and proposing a fix...", "fa5s.search")

        fix_json_str = await self.reviewer.review_and_correct_code(error_report, git_diff,
                                                                   json.dumps(full_code_context))
        if not fix_json_str:
            self.handle_error("Aura", "I was unable to generate a code fix for the error.")
            return

        try:
            corrected_files = self._parse_json_response(fix_json_str)
            if not isinstance(corrected_files, dict):
                raise ValueError("Reviewer's fix was not a valid file dictionary.")
        except (json.JSONDecodeError, ValueError) as e:
            self.handle_error("Aura", f"My proposed fix was not valid JSON or was malformed: {e}")
            return

        self._post_chat_message("Aura",
                                "I've analyzed the error and proposed a fix. I will now create a new execution plan to apply it.")

        fix_tool_plan = []
        for path, content in corrected_files.items():
            fix_tool_plan.append({
                "tool_name": "stream_and_write_file",
                "arguments": {"path": path,
                              "task_description": f"Write the following corrected code to the file:\n\n```python\n{content}\n```"}
            })

        if not fix_tool_plan:
            self.handle_error("Aura", "My proposed fix resulted in an empty execution plan.")
            return

        self.mission_log_service.replace_all_tasks_with_tool_plan(fix_tool_plan)
        self._post_chat_message("Aura",
                                "A new plan to apply the fix has been created. Re-engaging autonomous execution.")
        self.event_bus.emit("mission_dispatch_requested", MissionDispatchRequest())

    def handle_error(self, agent: str, error_msg: str):
        self.log("error", f"{agent} failed: {error_msg}")
        self.event_bus.emit("agent_status_changed", "Aura", "Failed", "fa5s.exclamation-triangle")
        self._post_chat_message("Aura", error_msg, is_error=True)

    def log(self, level: str, message: str):
        self.event_bus.emit("log_message_received", "DevTeamService", level, message)