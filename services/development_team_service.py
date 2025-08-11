# services/development_team_service.py
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

from event_bus import EventBus
from prompts.creative import AURA_PLANNER_PROMPT
from services.agents import ReviewerService, CoderService
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

        # Instantiate specialist services
        self.reviewer = ReviewerService(self.event_bus, self.llm_client)
        self.coder = CoderService(
            self.event_bus,
            self.llm_client,
            self.service_manager.vector_context_service,
            self.project_manager,
            self.service_manager.foundry_manager,
        )

    def _post_chat_message(self, sender: str, message: str, is_error: bool = False):
        self.event_bus.emit("post_chat_message", PostChatMessage(sender, message, is_error))

    def _parse_json_response(self, response: str) -> dict:
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if not match:
            raise ValueError("No JSON object found in the response.")
        return json.loads(match.group(0))

    async def run_aura_planner_workflow(self, user_idea: str, conversation_history: list):
        """Phase 1: Aura creates the initial high-level, human-readable plan."""
        self.log("info", f"Aura Planner workflow initiated for: '{user_idea[:50]}...'")
        self.event_bus.emit("agent_status_changed", "Aura", "Formulating a plan...", "fa5s.lightbulb")

        prompt = AURA_PLANNER_PROMPT.format(
            conversation_history="\n".join([f"{msg['role']}: {msg['content']}" for msg in conversation_history]),
            user_idea=user_idea
        )
        provider, model = self.llm_client.get_model_for_role("chat")
        if not provider or not model:
            self.handle_error("Aura", "No 'chat' model configured.")
            return

        response_str = "".join([chunk async for chunk in self.llm_client.stream_chat(provider, model, prompt, "chat")])

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
            self.log("error", f"Aura planning failure. Raw response: {response_str}")

    async def run_coding_task(
        self,
        current_task: str
    ) -> Optional[Dict[str, str]]:
        """Delegates the coding task to the specialized CoderService."""
        return await self.coder.run_coding_task(current_task)

    async def run_review_and_fix_phase(self, error_report: str, git_diff: str, full_code_context: Dict[str, str]):
        self.log("info", "Review and Fix phase initiated.")
        self.event_bus.emit("agent_status_changed", "Reviewer", "Analyzing failure...", "fa5s.search")

        fix_json_str = await self.reviewer.review_and_correct_code(error_report, git_diff,
                                                                   json.dumps(full_code_context))
        if not fix_json_str:
            self.handle_error("Reviewer", "Failed to generate a code fix.")
            return

        try:
            corrected_files = self._parse_json_response(fix_json_str)
            if not isinstance(corrected_files, dict):
                raise ValueError("Reviewer's fix was not a valid file dictionary.")
        except (json.JSONDecodeError, ValueError) as e:
            self.handle_error("Reviewer", f"Proposed fix was not valid JSON or was malformed: {e}")
            return

        self._post_chat_message("Reviewer",
                                "I've analyzed the error and proposed a fix. I will now create a new execution plan to apply it.")

        # Convert the fix into a simple tool plan directly
        fix_tool_plan = []
        for path, content in corrected_files.items():
            fix_tool_plan.append({
                "tool_name": "write_file",
                "arguments": {"path": path, "content": content}
            })

        if not fix_tool_plan:
            self.handle_error("Reviewer", "The proposed fix resulted in an empty execution plan.")
            return

        self.mission_log_service.replace_all_tasks_with_tool_plan(fix_tool_plan)
        self._post_chat_message("Conductor",
                                "A new plan to apply the fix has been created. Re-engaging autonomous execution.")
        self.event_bus.emit("mission_dispatch_requested", MissionDispatchRequest())

    def handle_error(self, agent: str, error_msg: str):
        self.log("error", f"{agent} failed: {error_msg}")
        self.event_bus.emit("agent_status_changed", agent, "Failed", "fa5s.exclamation-triangle")
        self._post_chat_message(agent, error_msg, is_error=True)

    def log(self, level: str, message: str):
        self.event_bus.emit("log_message_received", "DevTeamService", level, message)