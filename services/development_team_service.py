# services/development_team_service.py
from __future__ import annotations
import json
import re
from typing import TYPE_CHECKING, Dict, List, Optional, Any

from event_bus import EventBus
from core.prompt_templates.architect import ArchitectPrompt
from core.prompt_templates.coder import CoderPrompt
from core.prompt_templates.replan import RePlannerPrompt
from core.prompt_templates.sentry import SENTRY_PROMPT
from core.prompt_templates.summarizer import MissionSummarizerPrompt
from core.prompt_templates.dispatcher import ChiefOfStaffDispatcherPrompt
from events import PlanReadyForReview, MissionDispatchRequest, PostChatMessage
from services.agent_workflow_manager import AgentWorkflowManager
from core.stream_parser import parse_llm_stream_async
from core.models.messages import AuraMessage, MessageType

if TYPE_CHECKING:
    from core.managers.service_manager import ServiceManager


class DevelopmentTeamService:
    """
    Orchestrates the main AI workflows by delegating to specialized services
    and handling different planning and execution modes.
    """

    def __init__(self, event_bus: EventBus, service_manager: "ServiceManager"):
        self.event_bus = event_bus
        self.service_manager = service_manager
        self.llm_client = service_manager.get_llm_client()
        self.project_manager = service_manager.project_manager
        self.mission_log_service = service_manager.mission_log_service
        self.vector_context_service = service_manager.vector_context_service
        self.foundry_manager = service_manager.get_foundry_manager()
        self.tool_runner_service = service_manager.tool_runner_service
        self.workflow_manager = AgentWorkflowManager(self.llm_client, self.service_manager, self.event_bus)

    def _post_chat_message(self, sender: str, message: str, is_error: bool = False):
        if message and message.strip():
            self.event_bus.emit("post_chat_message", PostChatMessage(sender, message, is_error))

    def _post_structured_message(self, message: AuraMessage):
        """Post a structured message to the command deck"""
        if message.content and message.content.strip():
            self.event_bus.emit("post_structured_message", message)

    def _parse_json_response(self, response: str) -> dict:
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if not match:
            raise ValueError(f"No JSON object found in the response. Raw response: {response}")
        return json.loads(match.group(0))

    async def handle_user_prompt(self, user_idea: str, conversation_history: list):
        """
        Primary entry point for a user's message.
        Simplified version that goes directly to planning workflow for new projects.
        """
        self.log("info", f"Handling user prompt: '{user_idea[:50]}...'")

        # Check if we have tasks already - if empty, go straight to planning
        current_tasks = self.mission_log_service.get_tasks()

        if not current_tasks:
            # No existing tasks - user wants to start a new project
            self.log("info", "No existing tasks found. Starting new project planning workflow.")
            await self._run_direct_planning_workflow(user_idea, conversation_history)
        else:
            # Has existing tasks - try to use dispatcher to determine intent
            self.log("info", "Existing tasks found. Using dispatcher to determine user intent.")
            await self._run_dispatcher_workflow(user_idea, conversation_history)

    async def _run_dispatcher_workflow(self, user_idea: str, conversation_history: list):
        """
        Uses the dispatcher to route to the appropriate workflow.
        """
        self.log("info", "Chief of Staff analyzing user intent...")
        self.event_bus.emit("agent_status_changed", "Chief of Staff", "Analyzing request...", "fa5s.user-tie")

        conv_history_str = "\n".join([f"{msg['role']}: {msg['content']}" for msg in conversation_history])
        mission_log_summary = self.mission_log_service.get_log_as_string_summary()

        prompt_template = ChiefOfStaffDispatcherPrompt()
        prompt = prompt_template.render(
            user_prompt=user_idea,
            conversation_history=conv_history_str,
            mission_log_state=mission_log_summary
        )

        provider, model = self.llm_client.get_model_for_role("dispatcher")
        if not provider or not model:
            self.log("warning", "No 'dispatcher' model configured. Falling back to direct planning.")
            await self._run_direct_planning_workflow(user_idea, conversation_history)
            return

        self.event_bus.emit("processing_started")

        try:
            stream_chunks = self.llm_client.stream_chat(provider, model, prompt, "dispatcher")
            dispatch_to = None

            async for message in parse_llm_stream_async(stream_chunks):
                if message.type == MessageType.AGENT_THOUGHT:
                    # Display the dispatcher's reasoning
                    self._post_structured_message(message)
                elif message.type == MessageType.AGENT_PLAN_JSON:
                    # Process the dispatcher's JSON decision internally
                    try:
                        decision_data = json.loads(message.content)
                        dispatch_to = decision_data.get("dispatch_to")
                        self.log("info", f"Chief of Staff dispatched to: {dispatch_to}")
                    except (ValueError, json.JSONDecodeError) as e:
                        self.log("warning", f"Dispatcher JSON parsing failed: {e}")
                        break
                else:
                    # Display other message types normally
                    self._post_structured_message(message)

            # Execute the dispatch decision
            if dispatch_to == "CONDUCTOR":
                self.log("info", "User requested to start the build. Dispatching to Conductor.")
                self._post_chat_message("Aura", "Okay, I'll start the build process now.")
                self.event_bus.emit("mission_dispatch_requested", MissionDispatchRequest())
            elif dispatch_to == "CREATIVE_ASSISTANT":
                await self._run_direct_planning_workflow(user_idea, conversation_history)
            elif dispatch_to:
                await self.workflow_manager.run_workflow(dispatch_to, user_idea, conversation_history)
            else:
                self.log("warning", "Dispatcher returned unknown target. Falling back to planning.")
                await self._run_direct_planning_workflow(user_idea, conversation_history)

        except Exception as e:
            self.log("warning", f"Dispatcher workflow failed: {e}. Falling back to direct planning.")
            await self._run_direct_planning_workflow(user_idea, conversation_history)
        finally:
            self.event_bus.emit("processing_finished")

    async def _run_direct_planning_workflow(self, user_idea: str, conversation_history: list):
        """
        Direct planning workflow that creates a plan and populates the mission log.
        This bypasses the dispatcher and goes straight to plan generation.
        """
        self.log("info", f"Direct planning workflow initiated for: '{user_idea[:50]}...'")
        self.event_bus.emit("agent_status_changed", "Aura", "Formulating an efficient plan...", "fa5s.lightbulb")

        provider, model = self.llm_client.get_model_for_role("planner")
        if not provider or not model:
            self.handle_error("Aura", "No 'planner' model configured.")
            return

        prompt_template = ArchitectPrompt()
        conv_history_str = "\n".join([f"{msg['role']}: {msg['content']}" for msg in conversation_history])
        prompt = prompt_template.render(user_idea=user_idea, conversation_history=conv_history_str)

        self.event_bus.emit("processing_started")
        try:
            stream_chunks = self.llm_client.stream_chat(provider, model, prompt, "planner")

            async for message in parse_llm_stream_async(stream_chunks):
                if message.type == MessageType.AGENT_PLAN_JSON:
                    try:
                        response_data = json.loads(message.content)
                        self.log("info", f"Received plan JSON: {response_data}")

                        # Handle thought if present
                        if "thought" in response_data:
                            self._post_structured_message(AuraMessage.agent_thought(response_data["thought"]))

                        # Process the plan
                        plan_steps = response_data.get("plan", [])
                        if plan_steps:
                            for step in plan_steps:
                                self.mission_log_service.add_task(step)
                            self._post_chat_message("Aura",
                                                    "I've created a comprehensive plan for your project. Check the 'Agent TODO' list to review the tasks.")
                            self.event_bus.emit("plan_ready_for_review", PlanReadyForReview())
                        else:
                            self.handle_error("Aura", "Failed to generate a valid plan - no tasks found.")

                    except (ValueError, json.JSONDecodeError) as e:
                        self.handle_error("Aura", f"Failed to parse the plan: {e}")
                else:
                    self._post_structured_message(message)

        except Exception as e:
            self.handle_error("Aura", f"Direct planning workflow failed: {str(e)}")
        finally:
            self.event_bus.emit("processing_finished")

    def log(self, level: str, message: str):
        self.event_bus.emit("log_message_received", "DevelopmentTeamService", level, message)

    def handle_error(self, agent: str, error_msg: str):
        self.log("error", f"{agent} failed: {error_msg}")
        self.event_bus.emit("agent_status_changed", "Aura", "Failed", "fa5s.exclamation-triangle")
        self._post_structured_message(AuraMessage.error(error_msg))

    async def run_architect_task(self, task: Dict[str, any]) -> Optional[Dict[str, str]]:
        """
        Invokes the Architect AI to plan a specific file based on the task description.
        """
        file_path = task.get("file_path")
        description = task.get("description", "No description provided.")

        if not file_path:
            self.log("error", "Architect task requires a 'file_path' in the task arguments.")
            return None

        self.log("info", f"Architect planning file: {file_path}")
        self.event_bus.emit("agent_status_changed", "Aura", f"Planning: {file_path}...", "fa5s.pencil-ruler")

        file_structure = "\n".join(sorted(self.project_manager.get_project_files().keys()))
        available_tools = json.dumps(self.foundry_manager.get_llm_tool_definitions(), indent=2)

        prompt_template = ArchitectPrompt()
        prompt = prompt_template.render(
            user_idea=description,
            conversation_history="",
            file_structure=file_structure,
            available_tools=available_tools
        )

        provider, model = self.llm_client.get_model_for_role("architect")
        if not provider or not model:
            self.log("error", "No 'architect' model configured.")
            self.handle_error("Aura", "No 'architect' model configured.")
            return None

        response_str = "".join(
            [chunk async for chunk in self.llm_client.stream_chat(provider, model, prompt, "architect")])

        try:
            tool_call = self._parse_json_response(response_str)
            if "tool_name" not in tool_call or "arguments" not in tool_call:
                raise ValueError("Architect response must be a JSON object with 'tool_name' and 'arguments' keys.")

            if tool_call.get("tool_name") != "stream_and_write_file":
                self.log("warning", f"Architect returned an unexpected tool: {tool_call.get('tool_name')}")

            return tool_call
        except (ValueError, json.JSONDecodeError) as e:
            self.log("error", f"Architect generation failure. Raw response: {response_str}. Error: {e}")
            self.handle_error("Aura", f"Failed to generate a valid architecture plan: {e}")
            return None

    async def run_coder_task(self, task: Dict[str, any]) -> Optional[Dict[str, str]]:
        """
        Invokes the Coder AI to generate code for a specific file based on the task description.
        """
        file_path = task.get("file_path")
        description = task.get("description", "No description provided.")

        if not file_path:
            self.log("error", "Coder task requires a 'file_path' in the task arguments.")
            return None

        self.log("info", f"Coder generating code for: {file_path}")
        self.event_bus.emit("agent_status_changed", "Aura", f"Coding: {file_path}...", "fa5s.code")

        # Get context from project files
        relevant_code_snippets = self.vector_context_service.get_relevant_context(description, max_results=5)
        file_structure = "\n".join(sorted(self.project_manager.get_project_files().keys()))

        prompt_template = CoderPrompt()
        prompt = prompt_template.render(
            file_path=file_path,
            description=description,
            relevant_code_snippets=relevant_code_snippets,
            file_structure=file_structure
        )

        provider, model = self.llm_client.get_model_for_role("coder")
        if not provider or not model:
            self.log("error", "No 'coder' model configured.")
            self.handle_error("Aura", "No 'coder' model configured.")
            return None

        response_str = "".join(
            [chunk async for chunk in self.llm_client.stream_chat(provider, model, prompt, "coder")])

        try:
            tool_call = self._parse_json_response(response_str)
            if "tool_name" not in tool_call or "arguments" not in tool_call:
                raise ValueError("Coder response must be a JSON object with 'tool_name' and 'arguments' keys.")

            if tool_call.get("tool_name") != "stream_and_write_file":
                self.log("warning", f"Coder returned an unexpected tool: {tool_call.get('tool_name')}")

            return tool_call
        except (ValueError, json.JSONDecodeError) as e:
            self.log("error", f"Coder generation failure. Raw response: {response_str}. Error: {e}")
            return None

    async def run_sentry_task(self, task: Dict[str, any]) -> Optional[Dict[str, str]]:
        """
        Asks the Sentry AI to analyze a file for bugs and generate a failing test.
        """
        file_path = task.get("file_path")
        if not file_path:
            self.log("error", "Sentry task requires a 'file_path' in the task arguments.")
            return None

        self.log("info", f"Sentry analyzing file for bugs: {file_path}")
        self.event_bus.emit("agent_status_changed", "Aura", f"Analyzing for bugs: {file_path}...", "fa5s.search")

        code_content = self.project_manager.read_file(file_path)
        if code_content is None:
            self.log("error", f"Sentry could not read the file: {file_path}")
            self.handle_error("Sentry", f"Could not read file: {file_path}")
            return None

        prompt = SENTRY_PROMPT.format(
            file_path=file_path,
            code_content=code_content
        )

        provider, model = self.llm_client.get_model_for_role("sentry")
        if not provider or not model:
            self.log("error", "No 'sentry' model configured.")
            self.handle_error("Sentry", "No 'sentry' model configured.")
            return None

        response_str = "".join(
            [chunk async for chunk in self.llm_client.stream_chat(provider, model, prompt, "sentry")])

        try:
            tool_call = self._parse_json_response(response_str)
            if "tool_name" not in tool_call or "arguments" not in tool_call:
                raise ValueError("Sentry response must be a JSON object with 'tool_name' and 'arguments' keys.")

            if tool_call.get("tool_name") != "stream_and_write_file":
                self.log("warning", f"Sentry returned an unexpected tool: {tool_call.get('tool_name')}")

            return tool_call
        except (ValueError, json.JSONDecodeError) as e:
            self.log("error", f"Sentry generation failure. Raw response: {response_str}. Error: {e}")
            self.handle_error("Sentry", f"Failed to generate a valid test: {e}")
            return None

    async def run_strategic_replan(self, original_goal: str, failed_task: Dict, mission_log: List[Dict]):
        """
        Invokes the Re-Planner AI to create a new plan when a task fails repeatedly.
        """
        self.log("info", "Strategic re-plan initiated.")
        self.event_bus.emit("agent_status_changed", "Aura", "Hitting a roadblock. Re-planning...", "fa5s.route")

        prompt_template = RePlannerPrompt()
        prompt = prompt_template.render(
            original_goal=original_goal,
            failed_task=json.dumps(failed_task, indent=2),
            mission_log=json.dumps(mission_log, indent=2)
        )

        provider, model = self.llm_client.get_model_for_role("replanner")
        if not provider or not model:
            self.log("error", "No 're-planner' model configured.")
            self.handle_error("Aura", "No 're-planner' model configured.")
            return

        response_str = "".join(
            [chunk async for chunk in self.llm_client.stream_chat(provider, model, prompt, "replanner")])

        try:
            response_data = self._parse_json_response(response_str)
            self.log("info", f"Re-planning complete: {response_data}")

            if "thought" in response_data:
                self._post_structured_message(AuraMessage.agent_thought(response_data["thought"]))

            new_plan = response_data.get("plan", [])
            if new_plan:
                self.mission_log_service.clear_tasks()
                for step in new_plan:
                    self.mission_log_service.add_task(step)
                self._post_chat_message("Aura",
                                        "I've created a new strategy to overcome the roadblock. Check the updated plan in the 'Agent TODO' list.")
                self.event_bus.emit("plan_ready_for_review", PlanReadyForReview())

        except (ValueError, json.JSONDecodeError) as e:
            self.log("error", f"Re-planner generation failure. Raw response: {response_str}. Error: {e}")
            self.handle_error("Aura", f"Failed to create a new plan: {e}")

    async def run_mission_summarizer(self, mission_log: List[Dict]) -> str:
        """
        Uses the Mission Summarizer AI to create a concise summary of the mission log.
        Returns the summary as a string.
        """
        self.log("info", "Mission summarization initiated.")

        prompt_template = MissionSummarizerPrompt()
        prompt = prompt_template.render(mission_log=json.dumps(mission_log, indent=2))

        provider, model = self.llm_client.get_model_for_role("summarizer")
        if not provider or not model:
            self.log("warning", "No 'summarizer' model configured. Using raw mission log.")
            return str(mission_log)

        response_str = "".join(
            [chunk async for chunk in self.llm_client.stream_chat(provider, model, prompt, "summarizer")])

        try:
            response_data = self._parse_json_response(response_str)
            summary = response_data.get("summary", "Summary generation failed.")
            self.log("info", f"Mission summary created: {len(summary)} characters")
            return summary
        except (ValueError, json.JSONDecodeError) as e:
            self.log("warning", f"Summarizer failed: {e}. Using raw mission log.")
            return str(mission_log)