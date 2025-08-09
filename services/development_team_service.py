# services/development_team_service.py
from __future__ import annotations
from typing import TYPE_CHECKING, Dict, List, Optional

from event_bus import EventBus
from prompts import CREATIVE_ASSISTANT_PROMPT
from services.agents import ArchitectService, GenerationCoordinator, ReviewerService, FinalizerAgent

if TYPE_CHECKING:
    from core.managers.service_manager import ServiceManager


class DevelopmentTeamService:
    """
    Orchestrates the AI agent team (Architect, Coder, Reviewer, Finalizer)
    to turn a user prompt into an executable plan for the Mission Log.
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
        self.reviewer = ReviewerService(self.event_bus, self.llm_client)
        self.finalizer = FinalizerAgent(service_manager)

    async def run_build_workflow(self, prompt: str, existing_files: Optional[Dict[str, str]] = None):
        """
        Executes the full build pipeline: Plan -> Code -> Review -> Finalize -> Log.
        """
        self.log("info", f"Build workflow initiated for prompt: '{prompt[:50]}...'")

        # 1. Architect Phase
        self.event_bus.emit("agent_status_changed", "Architect", "Planning project...", "fa5s.pencil-ruler")
        plan = await self.architect.generate_plan(prompt, existing_files)
        if not plan:
            self.handle_error("Architect", "Failed to generate a valid plan.")
            return

        # 2. Coder Phase (coordinated)
        self.event_bus.emit("agent_status_changed", "Coder", "Generating code...", "fa5s.keyboard")
        generated_files = await self.coordinator.coordinate_generation(plan, existing_files)
        if not generated_files:
            self.handle_error("Coder", "Code generation failed to produce files.")
            return

        # 3. Finalizer Phase
        self.event_bus.emit("agent_status_changed", "Finalizer", "Creating execution plan...", "fa5s.clipboard-list")
        tool_plan = await self.finalizer.create_tool_plan(generated_files, existing_files, plan.get('dependencies', []))
        if tool_plan is None:
            self.handle_error("Finalizer", "Failed to create an executable tool plan.")
            return

        # 4. Populate Mission Log
        self.mission_log_service.clear_pending_tasks()
        for tool_call in tool_plan:
            summary = self._summarize_tool_call(tool_call)
            self.mission_log_service.add_task(summary, tool_call)

        self.log("success", "Build plan successfully generated and loaded into Mission Log.")
        self.event_bus.emit("agent_status_changed", "Aura", "Plan ready for dispatch", "fa5s.rocket")

    async def run_chat_workflow(self, user_idea: str, conversation_history: list, image_bytes: Optional[bytes],
                                image_media_type: Optional[str]):
        """Runs the 'Aura' creative assistant persona for planning and brainstorming."""
        self.log("info", f"Aura chat workflow processing: '{user_idea[:50]}...'")
        self.event_bus.emit("agent_status_changed", "Aura", "Thinking...", "fa5s.lightbulb")

        # The creative prompt doesn't need the full project context, just the conversation.
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
        """Creates a human-readable summary of a tool call for the Mission Log."""
        tool_name = tool_call.get('tool_name', 'unknown_tool')
        args = tool_call.get('arguments', {})
        if not isinstance(args, dict): args = {}

        summary = ' '.join(word.capitalize() for word in tool_name.split('_'))
        path = args.get('path') or args.get('source_path')
        if path:
            summary += f": '{path}'"
        elif 'project_name' in args:
            summary += f": '{args['project_name']}'"
        elif 'dependency' in args:
            summary += f": '{args['dependency']}'"

        return summary

    def handle_error(self, agent: str, error_msg: str):
        self.log("error", f"{agent} failed: {error_msg}")
        self.event_bus.emit("agent_status_changed", agent, "Failed", "fa5s.exclamation-triangle")
        # Optionally, send a message to the chat UI
        # self.event_bus.emit("streaming_chunk", f"Sorry, the {agent} failed: {error_msg}")

    def log(self, level: str, message: str):
        self.event_bus.emit("log_message_received", "DevTeamService", level, message)