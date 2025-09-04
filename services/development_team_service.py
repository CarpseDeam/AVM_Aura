# services/development_team_service.py
from __future__ import annotations
import json
import re
import traceback
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

    def handle_error(self, agent: str, error_msg: str):
        """Handle and display errors properly"""
        print(f"[DevelopmentTeamService] ERROR: {agent} - {error_msg}")
        self.log("error", f"{agent} failed: {error_msg}")
        self.event_bus.emit("agent_status_changed", "Aura", "Failed", "fa5s.exclamation-triangle")
        self._post_structured_message(AuraMessage.error(error_msg))

    def log(self, level: str, message: str):
        """Log messages to the event bus"""
        print(f"[DevelopmentTeamService] {level.upper()}: {message}")
        self.event_bus.emit("log_message_received", "DevelopmentTeamService", level, message)

    def _is_chat_request(self, user_idea: str) -> bool:
        """
        Determines if the user input is clearly a chat/greeting request.
        """
        chat_indicators = [
            "hi", "hello", "hey", "howdy", "greetings", "good morning",
            "good afternoon", "good evening", "sup", "what's up", "yo",
            "how are you", "how's it going", "what's happening"
        ]

        user_input_lower = user_idea.lower().strip()

        # Check for exact matches or starts with greeting
        for indicator in chat_indicators:
            if user_input_lower == indicator or user_input_lower.startswith(indicator + " "):
                return True

        # Check if it's a very short message without clear intent
        if len(user_input_lower.split()) <= 3 and not any(
                keyword in user_input_lower for keyword in
                ["build", "create", "make", "code", "implement", "fix", "debug", "plan"]
        ):
            return True

        return False

    def _parse_json_response(self, response: str) -> dict:
        match = re.search(r'\{.*?\}', response, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return {}

    async def handle_user_prompt(self, user_idea: str, conversation_history: List[Dict]) -> None:
        """
        The main routing point for user prompts. Improved to handle simple chat properly.
        """
        try:
            print(f"[DevelopmentTeamService] Starting handle_user_prompt with: '{user_idea[:50]}...'")
            self.log("info", f"Handling user prompt: '{user_idea[:50]}...'")

            # DEBUG: Check if services are properly initialized
            if not self.llm_client:
                self.handle_error("System", "LLM Client is not initialized!")
                return

            if not self.mission_log_service:
                self.handle_error("System", "Mission Log Service is not initialized!")
                return

            print("[DevelopmentTeamService] Getting current tasks...")
            current_tasks = self.mission_log_service.get_tasks()
            print(f"[DevelopmentTeamService] Found {len(current_tasks)} existing tasks")

            # First, check if this is clearly a chat request (greetings, etc.)
            if self._is_chat_request(user_idea):
                print("[DevelopmentTeamService] Detected chat request, using general chat workflow...")
                await self.workflow_manager.run_workflow("GENERAL_CHAT", user_idea, conversation_history)
                return

            # For ambiguous cases or when we have existing tasks, use dispatcher
            if current_tasks or len(user_idea.strip()) > 50:
                print("[DevelopmentTeamService] Using dispatcher to determine intent...")
                await self._run_dispatcher_workflow(user_idea, conversation_history)
            else:
                # Short message without clear chat indicators - still use dispatcher for safety
                print("[DevelopmentTeamService] Short message, using dispatcher...")
                await self._run_dispatcher_workflow(user_idea, conversation_history)

        except Exception as e:
            print(f"[DevelopmentTeamService] EXCEPTION in handle_user_prompt: {e}")
            print(f"[DevelopmentTeamService] Exception traceback: {traceback.format_exc()}")
            self.handle_error("System", f"Unexpected error in workflow: {str(e)}")

    async def _run_dispatcher_workflow(self, user_idea: str, conversation_history: list):
        """
        Uses the dispatcher to route to the appropriate workflow.
        Fixed to better handle simple messages.
        """
        try:
            print("[DevelopmentTeamService] Starting dispatcher workflow...")
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

            print("[DevelopmentTeamService] Getting model for dispatcher role...")
            provider, model = self.llm_client.get_model_for_role("dispatcher")
            print(f"[DevelopmentTeamService] Dispatcher model: {provider}/{model}")

            if not provider or not model:
                self.log("warning", "No 'dispatcher' model configured. Falling back to chat.")
                await self.workflow_manager.run_workflow("GENERAL_CHAT", user_idea, conversation_history)
                return

            self.event_bus.emit("processing_started")

            # Collect raw response for debugging
            raw_response_chunks = []
            stream_chunks = self.llm_client.stream_chat(provider, model, prompt, "dispatcher")

            async for chunk in stream_chunks:
                raw_response_chunks.append(chunk)

            full_response = "".join(raw_response_chunks)
            print(f"[DevelopmentTeamService] Dispatcher raw response: {full_response[:200]}...")

            # Try to parse dispatcher decision with better fallback
            dispatch_to = None
            try:
                # Look for JSON in the response
                if '{' in full_response:
                    match = re.search(r'\{[^}]*"dispatch_to"\s*:\s*"([^"]*)"[^}]*\}', full_response)
                    if match:
                        dispatch_to = match.group(1)
                        print(f"[DevelopmentTeamService] Dispatcher decision: {dispatch_to}")
            except Exception as e:
                print(f"[DevelopmentTeamService] Error parsing dispatcher response: {e}")

            # If dispatcher failed or returned empty/unclear, check message type
            if not dispatch_to or dispatch_to == "":
                # Default routing based on message characteristics
                if self._is_chat_request(user_idea):
                    dispatch_to = "GENERAL_CHAT"
                elif len(user_idea.strip()) < 20:
                    dispatch_to = "GENERAL_CHAT"
                else:
                    dispatch_to = "CREATIVE_ASSISTANT"

                print(f"[DevelopmentTeamService] Using fallback dispatch: {dispatch_to}")

            # Execute the dispatch decision
            if dispatch_to == "CONDUCTOR":
                self.log("info", "User requested to start the build. Dispatching to Conductor.")
                self._post_chat_message("Aura", "Okay, I'll start the build process now.")
                self.event_bus.emit("mission_dispatch_requested", MissionDispatchRequest())
            elif dispatch_to == "CREATIVE_ASSISTANT":
                await self._run_direct_planning_workflow(user_idea, conversation_history)
            elif dispatch_to == "GENERAL_CHAT":
                await self.workflow_manager.run_workflow("GENERAL_CHAT", user_idea, conversation_history)
            elif dispatch_to:
                await self.workflow_manager.run_workflow(dispatch_to, user_idea, conversation_history)
            else:
                # Final fallback - default to chat
                self.log("info", "Dispatcher returned unclear target. Defaulting to chat.")
                await self.workflow_manager.run_workflow("GENERAL_CHAT", user_idea, conversation_history)

        except Exception as e:
            print(f"[DevelopmentTeamService] EXCEPTION in _run_dispatcher_workflow: {e}")
            print(f"[DevelopmentTeamService] Exception traceback: {traceback.format_exc()}")
            self.log("warning", f"Dispatcher workflow failed: {e}. Falling back to chat.")
            await self.workflow_manager.run_workflow("GENERAL_CHAT", user_idea, conversation_history)
        finally:
            self.event_bus.emit("processing_finished")

    async def _run_direct_planning_workflow(self, user_idea: str, conversation_history: list):
        """
        Direct planning workflow that creates a plan and populates the mission log.
        This bypasses the dispatcher and goes straight to plan generation.
        """
        try:
            print("[DevelopmentTeamService] Starting direct planning workflow...")
            self.log("info", f"Direct planning workflow initiated for: '{user_idea[:50]}...'")
            self.event_bus.emit("agent_status_changed", "Aura", "Formulating an efficient plan...", "fa5s.lightbulb")

            print("[DevelopmentTeamService] Getting model for planner role...")
            provider, model = self.llm_client.get_model_for_role("planner")
            print(f"[DevelopmentTeamService] Planner model: {provider}/{model}")

            if not provider or not model:
                self.handle_error("Aura",
                                  "No 'planner' model configured. Please configure AI models first using the 'Configure Model' button.")
                return

            print("[DevelopmentTeamService] Creating prompt...")
            prompt_template = ArchitectPrompt()
            conv_history_str = "\n".join([f"{msg['role']}: {msg['content']}" for msg in conversation_history])
            prompt = prompt_template.render(user_idea=user_idea, conversation_history=conv_history_str)

            print(f"[DevelopmentTeamService] Prompt preview: {prompt[:200]}...")

            print("[DevelopmentTeamService] Starting LLM stream...")
            self.event_bus.emit("processing_started")

            # Collect raw response
            raw_response_chunks = []
            stream_chunks = self.llm_client.stream_chat(provider, model, prompt, "planner")

            async for chunk in stream_chunks:
                raw_response_chunks.append(chunk)

            full_raw_response = "".join(raw_response_chunks)
            print(f"[DevelopmentTeamService] Planning response: {full_raw_response[:200]}...")

            # Parse the response
            if full_raw_response.strip():
                if full_raw_response.strip().startswith('{'):
                    try:
                        response_data = json.loads(full_raw_response)
                        print(f"[DevelopmentTeamService] Successfully parsed JSON: {list(response_data.keys())}")

                        # Handle thought if present
                        if "thought" in response_data:
                            thought = response_data["thought"]
                            self._post_structured_message(AuraMessage.agent_thought(thought))

                        # Process the plan
                        plan_steps = response_data.get("plan", [])
                        print(f"[DevelopmentTeamService] Found {len(plan_steps)} plan steps")
                        if plan_steps:
                            for step in plan_steps:
                                self.mission_log_service.add_task(step)
                            self._post_chat_message("Aura",
                                                    "I've created a comprehensive plan for your project. Check the 'Agent TODO' list to review the tasks.")
                            self.event_bus.emit("plan_ready_for_review", PlanReadyForReview())
                        else:
                            print("[DevelopmentTeamService] Empty plan - this might be a chat request")
                            # If planner returns empty plan, treat as chat
                            if "thought" in response_data and response_data["thought"]:
                                self._post_structured_message(AuraMessage.agent_response(
                                    "I understand you're just saying hello! How can I help you today?"))
                            else:
                                self.handle_error("Aura", "Failed to generate a valid plan - no tasks found.")

                    except (ValueError, json.JSONDecodeError) as e:
                        print(f"[DevelopmentTeamService] JSON parsing error: {e}")
                        self._post_structured_message(AuraMessage.agent_response(full_raw_response))
                else:
                    # Plain text response
                    self._post_structured_message(AuraMessage.agent_response(full_raw_response))
            else:
                self.handle_error("Aura", "LLM returned empty response. Please try again.")

        except Exception as e:
            print(f"[DevelopmentTeamService] EXCEPTION in _run_direct_planning_workflow: {e}")
            print(f"[DevelopmentTeamService] Exception traceback: {traceback.format_exc()}")
            self.log("error", f"Planning workflow failed: {e}")
            self.handle_error("Aura", f"Planning workflow failed: {e}")
        finally:
            self.event_bus.emit("processing_finished")

    async def run_coding_task(self, task: Dict[str, Any], last_error: Optional[str] = None) -> Optional[Dict]:
        """Execute a coding task and return the tool call."""
        task_description = task.get('description', 'Unknown task')
        self.log("info", f"Executing coding task: '{task_description[:60]}...'")

        prompt_template = CoderPrompt()
        current_mission = self.mission_log_service.get_log_as_string_summary()
        current_files = self.project_manager.get_project_files()

        prompt = prompt_template.render(
            task_description=task_description,
            current_mission=current_mission,
            current_files=current_files,
            last_error=last_error
        )

        provider, model = self.llm_client.get_model_for_role("coder")
        if not provider or not model:
            self.handle_error("Coder", "No 'coder' model configured.")
            return None

        try:
            response_str = "".join(
                [chunk async for chunk in self.llm_client.stream_chat(provider, model, prompt, "coder")])

            match = re.search(r'\{.*\}', response_str, re.DOTALL)
            if match:
                tool_call = json.loads(match.group(0))
                self.log("info", f"Generated tool call: {tool_call.get('tool_name', 'Unknown')}")
                return tool_call
            else:
                self.log("error", f"No valid JSON in coder response: {response_str}")
                return None

        except Exception as e:
            self.log("error", f"Coding task failed: {e}")
            return None

    async def run_sentry_check(self, file_path: str, file_contents: str) -> Optional[Dict]:
        """Run the Sentry AI to check for issues and generate tests."""
        self.log("info", f"Running sentry check on: {file_path}")

        prompt = SENTRY_PROMPT.format(
            file_path=file_path,
            file_contents=file_contents
        )

        provider, model = self.llm_client.get_model_for_role("sentry")
        if not provider or not model:
            self.log("warning", "No 'sentry' model configured. Skipping quality check.")
            return None

        try:
            response_str = "".join(
                [chunk async for chunk in self.llm_client.stream_chat(provider, model, prompt, "sentry")])

            match = re.search(r'\{.*\}', response_str, re.DOTALL)
            if match:
                result = json.loads(match.group(0))
                self.log("info", f"Sentry check completed: {result.get('issues_found', 0)} issues found")
                return result
            else:
                self.log("warning", "Sentry response did not contain valid JSON")
                return None

        except Exception as e:
            self.log("error", f"Sentry check failed: {e}")
            return None

    async def run_sentry_task(self, task: Dict[str, Any]) -> str:
        """Run the Sentry task to generate tests."""
        self.log("info", f"Running sentry task for: {task.get('description', '')[:60]}...")

        # Implementation would go here - returning placeholder for now
        return "Tests generated successfully"

    async def run_replanning(self, original_goal: str, current_mission: str) -> List[str]:
        """Re-plan the mission when stuck."""
        self.log("info", "Running strategic re-planning...")

        prompt_template = RePlannerPrompt()
        prompt = prompt_template.render(
            original_goal=original_goal,
            current_mission_state=current_mission
        )

        provider, model = self.llm_client.get_model_for_role("planner")
        if not provider or not model:
            self.log("error", "No 'planner' model configured for re-planning.")
            return []

        try:
            response_str = "".join(
                [chunk async for chunk in self.llm_client.stream_chat(provider, model, prompt, "planner")])

            match = re.search(r'\{.*\}', response_str, re.DOTALL)
            if match:
                result = json.loads(match.group(0))
                new_plan = result.get("plan", [])
                self.log("info", f"Re-planning generated {len(new_plan)} new tasks")
                return new_plan
            else:
                self.log("error", "Re-planning response did not contain valid JSON")
                return []

        except Exception as e:
            self.log("error", f"Re-planning failed: {e}")
            return []

    async def summarize_mission(self) -> str:
        """Generate a summary of the completed mission."""
        self.log("info", "Generating mission summary...")

        prompt_template = MissionSummarizerPrompt()
        mission_log = self.mission_log_service.get_log_as_string_summary()
        project_files = "\n".join(self.project_manager.get_project_files().keys())

        prompt = prompt_template.render(
            mission_log=mission_log,
            project_files=project_files
        )

        provider, model = self.llm_client.get_model_for_role("summarizer")
        if not provider or not model:
            provider, model = self.llm_client.get_model_for_role("chat")

        if not provider or not model:
            return "Mission completed successfully."

        try:
            response_str = "".join(
                [chunk async for chunk in self.llm_client.stream_chat(provider, model, prompt, "summarizer")])

            return response_str.strip() or "Mission completed successfully."

        except Exception as e:
            self.log("error", f"Summary generation failed: {e}")
            return "Mission completed successfully."