# services/development_team_service.py
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

from event_bus import EventBus
from prompts.creative import AURA_PLANNER_PROMPT, CREATIVE_ASSISTANT_PROMPT
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
        self.foundry_manager = service_manager.foundry_manager

        # Instantiate specialist services
        self.reviewer = ReviewerService(self.event_bus, self.llm_client)

    def _post_chat_message(self, sender: str, message: str, is_error: bool = False):
        if message and message.strip():
            self.event_bus.emit("post_chat_message", PostChatMessage(sender, message, is_error))

    def _parse_json_response(self, response: str) -> dict:
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if not match:
            raise ValueError("No JSON object found in the response.")
        return json.loads(match.group(0))

    async def run_aura_planner_workflow(self, user_idea: str, conversation_history: list):
        """
        Dynamically chooses a planning mode based on the user's prompt.
        - "One-Shot Mode": For detailed prompts, generates a full plan at once.
        - "Conversational Mode": For open-ended prompts, engages in a dialogue to help the user build a plan.
        """
        self.log("info", f"Aura workflow initiated for: '{user_idea[:50]}...'")

        one_shot_keywords = ["create a", "build a", "make a", "write a", "generate a", "scaffold a", "i need a project", "cli-calculator", "implement"]
        is_one_shot = any(user_idea.lower().strip().startswith(kw) for kw in one_shot_keywords)

        provider, model = self.llm_client.get_model_for_role("planner")
        if not provider or not model:
            self.handle_error("Aura", "No 'planner' model configured.")
            return

        if is_one_shot:
            # --- ONE-SHOT PLANNER MODE ---
            self.log("info", "Activating One-Shot Planner mode.")
            self.event_bus.emit("agent_status_changed", "Aura", "Formulating a plan...", "fa5s.lightbulb")
            prompt = AURA_PLANNER_PROMPT.format(
                conversation_history="\n".join([f"{msg['role']}: {msg['content']}" for msg in conversation_history]),
                user_idea=user_idea
            )
            response_str = "".join([chunk async for chunk in self.llm_client.stream_chat(provider, model, prompt, "planner")])
            try:
                plan_data = self._parse_json_response(response_str)
                plan_steps = plan_data.get("plan", [])
                if not plan_steps:
                    raise ValueError("Aura's plan was empty or malformed.")
                self.mission_log_service.set_initial_plan(plan_steps)
                self._post_chat_message("Aura",
                                        "I've created a high-level plan. Please review it in the 'Agent TODO' list. When you're ready, click 'Dispatch Aura' to begin the build.")
                self.event_bus.emit("plan_ready_for_review", PlanReadyForReview())
            except (ValueError, json.JSONDecodeError) as e:
                self.handle_error("Aura", f"Failed to create a valid plan: {e}. Raw response logged for debugging.")
                self.log("error", f"Aura one-shot planning failure. Raw response: {response_str}")

        else:
            # --- CONVERSATIONAL ASSISTANT MODE ---
            self.log("info", "Activating Conversational Assistant mode.")
            self.event_bus.emit("agent_status_changed", "Aura", "Thinking...", "fa5s.comment-dots")
            prompt = CREATIVE_ASSISTANT_PROMPT.format(
                conversation_history="\n".join([f"{msg['role']}: {msg['content']}" for msg in conversation_history]),
                user_idea=user_idea
            )
            response_str = "".join([chunk async for chunk in self.llm_client.stream_chat(provider, model, prompt, "chat")])

            tool_call_match = re.search(r'\[TOOL_CALL\](.*?\[/TOOL_CALL\])', response_str, re.DOTALL)
            conversation_reply = response_str
            tool_call = None

            if tool_call_match:
                tool_call_str = tool_call_match.group(1).replace("[/TOOL_CALL]", "").strip()
                conversation_reply = response_str[:tool_call_match.start()].strip()
                try:
                    tool_call = json.loads(tool_call_str)
                except json.JSONDecodeError as e:
                    self.log("error", f"Failed to parse tool call from conversational response: {e}. Raw block: {tool_call_str}")

            self._post_chat_message("Aura", conversation_reply)

            if tool_call:
                self.log("info", f"Conversational assistant identified a task: {tool_call}")
                tool_runner = self.service_manager.tool_runner_service
                if tool_runner:
                    await tool_runner.run_tool_by_dict(tool_call)
                else:
                    self.log("error", "ToolRunnerService not available to execute conversational tool call.")


    async def run_coding_task(
        self,
        current_task: str
    ) -> Optional[Dict[str, str]]:
        """
        Phase 2: The Coder translates a single task into a tool call using RAG.
        """
        self.log("info", f"Coder translating task to tool call: {current_task}")
        self.event_bus.emit("agent_status_changed", "Aura", f"Coding task: {current_task}...", "fa5s.cogs")

        relevant_context = "No existing code snippets were found. You are likely creating a new file or starting a new project."
        try:
            if self.vector_context_service and self.vector_context_service.collection.count() > 0:
                retrieved_chunks = self.vector_context_service.query(current_task, n_results=5)
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

        file_structure = "\n".join(sorted(list(self.project_manager.get_project_files().keys()))) or "The project is currently empty."
        available_tools = json.dumps(self.foundry_manager.get_llm_tool_definitions(), indent=2)

        prompt = CODER_PROMPT.format(
            current_task=current_task,
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
            self.handle_error("Aura", f"I failed to generate a valid tool call for the task. The raw response from the AI has been logged for debugging. Error: {e}")
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
                "tool_name": "write_file",
                "arguments": {"path": path, "content": content}
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