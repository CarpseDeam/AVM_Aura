# services/development_team_service.py
from __future__ import annotations
import re
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

from event_bus import EventBus
from prompts import CREATIVE_ASSISTANT_PROMPT
from services.agents import ArchitectService, GenerationCoordinator, ReviewerService, FinalizerAgent
from services.agents.tester_agent import TesterAgent

if TYPE_CHECKING:
    from core.managers.service_manager import ServiceManager


class DevelopmentTeamService:
    """
    Orchestrates the AI agent team in two distinct phases:
    1. Planning (Architect): Creates a high-level plan for user approval.
    2. Execution (Coder, Tester, Finalizer): Generates code and a detailed tool plan
       only after the user dispatches the mission.
    """

    def __init__(self, event_bus: EventBus, service_manager: "ServiceManager"):
        self.event_bus = event_bus
        self.service_manager = service_manager
        self.llm_client = service_manager.get_llm_client()
        self.project_manager = service_manager.get_project_manager()
        self.mission_log_service = service_manager.mission_log_service

        # Initialize the agent team
        self.architect = ArchitectService(service_manager)
        self.coordinator = GenerationCoordinator(service_manager)
        self.tester = TesterAgent(service_manager)
        self.reviewer = ReviewerService(self.event_bus, self.llm_client)
        self.finalizer = FinalizerAgent(service_manager)

    async def run_architect_phase(self, prompt: str, existing_files: Optional[Dict[str, str]] = None):
        """
        Phase 1: Run the architect to generate a high-level plan for user approval.
        """
        self.log("info", f"Architect phase initiated for prompt: '{prompt[:50]}...'")
        self.event_bus.emit("agent_status_changed", "Architect", "Planning project...", "fa5s.pencil-ruler")

        plan = await self.architect.generate_plan(prompt, existing_files)
        if not plan:
            self.handle_error("Architect", "Failed to generate a valid plan.")
            return

        self.mission_log_service.clear_all_tasks()

        # Create human-readable tasks for user review. These have no tool calls.
        for dependency in plan.get("dependencies", []):
            self.mission_log_service.add_task(f"Add dependency: {dependency}")

        for file_to_create in plan.get("files", []):
            self.mission_log_service.add_task(f"Generate file: {file_to_create['filename']}")

        # Add a single, special task at the end to trigger the execution phase.
        self.mission_log_service.add_task(
            description="Authorize and Begin Execution",
            tool_call={
                "tool_name": "execute_full_generation_plan",
                "arguments": {"plan": plan, "existing_files": existing_files or {}}
            }
        )

        self.log("success", "Architect plan created. Awaiting user dispatch from Agent TODO.")
        self.event_bus.emit("agent_status_changed", "Aura", "Plan ready for your approval", "fa5s.rocket")

    async def run_execution_phase(self, plan: dict, existing_files: dict) -> Optional[List[dict]]:
        """
        Phase 2: Called by the Conductor after approval. Runs Coder, Tester, and Finalizer.
        """
        self.log("info", "Execution phase initiated by Conductor.")

        # 1. Coder Phase
        self.event_bus.emit("agent_status_changed", "Coder", "Generating code...", "fa5s.keyboard")
        generated_files = await self.coordinator.coordinate_generation(plan, existing_files)
        if not generated_files:
            self.handle_error("Coder", "Code generation failed to produce files.")
            return None

        # 2. Tester Phase
        self.event_bus.emit("agent_status_changed", "Tester", "Writing tests...", "fa5s.vial")
        test_files = {}
        for filename, content in generated_files.items():
            if filename.endswith(".py") and not filename.startswith("test_"):
                test_filename = f"test_{Path(filename).name}"
                test_code = await self.tester.generate_tests_for_file(content, filename)
                if test_code:
                    test_files[test_filename] = test_code
        generated_files.update(test_files)
        if test_files:
            self.log("success", f"TesterAgent generated {len(test_files)} test file(s).")

        # 3. Finalizer Phase
        self.event_bus.emit("agent_status_changed", "Finalizer", "Creating execution plan...", "fa5s.clipboard-list")
        tool_plan = await self.finalizer.create_tool_plan(generated_files, existing_files, plan.get('dependencies', []))
        if tool_plan is None:
            self.handle_error("Finalizer", "Failed to create an executable tool plan.")
            return None

        return tool_plan

    async def run_chat_workflow(self, user_idea: str, conversation_history: list, image_bytes: Optional[bytes],
                                image_media_type: Optional[str]):
        """Runs the 'Aura' creative assistant persona for planning and brainstorming."""
        # This function remains unchanged
        self.log("info", f"Aura chat workflow processing: '{user_idea[:50]}...'")
        self.event_bus.emit("agent_status_changed", "Aura", "Thinking...", "fa5s.lightbulb")
        aura_prompt = CREATIVE_ASSISTANT_PROMPT.format(
            conversation_history="\n".join([f"{msg['role']}: {msg['content']}" for msg in conversation_history]),
            user_idea=user_idea
        )
        provider, model = self.llm_client.get_model_for_role("chat")
        if not provider or not model:
            self.event_bus.emit("streaming_chunk", "Sorry, no 'chat' model is configured for Aura.")
            return
        self.event_bus.emit("streaming_start", "Aura")
        try:
            stream = self.llm_client.stream_chat(
                provider, model, aura_prompt, "chat",
                image_bytes, image_media_type,
                history=conversation_history
            )
            async for chunk in stream:
                self.event_bus.emit("streaming_chunk", chunk)
        except Exception as e:
            self.event_bus.emit("streaming_chunk", f"\n\nAura encountered an error: {e}")
            self.log("error", f"Error during Aura streaming: {e}")
        finally:
            self.event_bus.emit("streaming_end")

    def _summarize_tool_call(self, tool_call: dict) -> str:
        # This function is now used by the Conductor
        tool_name = tool_call.get('tool_name', 'unknown_tool')
        args = tool_call.get('arguments', {})
        if not isinstance(args, dict): args = {}
        summary = ' '.join(word.capitalize() for word in tool_name.split('_'))
        path = args.get('path') or args.get('source_path')
        if path:
            summary += f": '{Path(path).name}'"
        elif 'project_name' in args:
            summary += f": '{args['project_name']}'"
        elif 'dependency' in args:
            summary += f": '{args['dependency']}'"
        return summary

    def handle_error(self, agent: str, error_msg: str):
        self.log("error", f"{agent} failed: {error_msg}")
        self.event_bus.emit("agent_status_changed", agent, "Failed", "fa5s.exclamation-triangle")

    def log(self, level: str, message: str):
        self.event_bus.emit("log_message_received", "DevTeamService", level, message)