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

    def _parse_json_response(self, response: str) -> dict:
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if not match:
            raise ValueError(f"No JSON object found in the response. Raw response: {response}")
        return json.loads(match.group(0))

    def _is_chat_request(self, user_input: str) -> bool:
        """Detect if this is a casual chat vs a build request"""
        user_lower = user_input.lower().strip()

        # Common greetings and chat phrases
        chat_patterns = [
            'hi', 'hello', 'hey', 'good morning', 'good afternoon', 'good evening',
            'how are you', 'what\'s up', 'thanks', 'thank you', 'bye', 'goodbye',
            'what can you do', 'help me understand', 'tell me about', 'explain',
            'what is', 'who are you', 'what are you'
        ]

        # Build-related keywords
        build_patterns = [
            'build', 'create', 'make', 'develop', 'code', 'write', 'implement',
            'design', 'app', 'application', 'program', 'script', 'tool', 'system',
            'website', 'api', 'database', 'project'
        ]

        # Check for chat patterns
        for pattern in chat_patterns:
            if pattern in user_lower:
                return True

        # Check for build patterns (if found, it's likely a build request)
        for pattern in build_patterns:
            if pattern in user_lower:
                return False

        # If very short and no build keywords, likely chat
        if len(user_input.strip()) < 20 and not any(pattern in user_lower for pattern in build_patterns):
            return True

        return False

    async def handle_user_prompt(self, user_idea: str, conversation_history: list):
        """
        Primary entry point for a user's message.
        Intelligently routes between chat and build workflows.
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

            # First, check if this is clearly a chat request
            if self._is_chat_request(user_idea):
                print("[DevelopmentTeamService] Detected chat request, using general chat workflow...")
                await self.workflow_manager.run_workflow("GENERAL_CHAT", user_idea, conversation_history)
                return

            # For ambiguous cases or when we have existing tasks, use dispatcher
            if current_tasks or len(user_idea.strip()) > 50:
                print("[DevelopmentTeamService] Using dispatcher to determine intent...")
                await self._run_dispatcher_workflow(user_idea, conversation_history)
            else:
                # Short message, no tasks, might be build request - go to planning
                print("[DevelopmentTeamService] Short message without clear intent, trying planning...")
                await self._run_direct_planning_workflow(user_idea, conversation_history)

        except Exception as e:
            print(f"[DevelopmentTeamService] EXCEPTION in handle_user_prompt: {e}")
            print(f"[DevelopmentTeamService] Exception traceback: {traceback.format_exc()}")
            self.handle_error("System", f"Unexpected error in workflow: {str(e)}")

    async def _run_dispatcher_workflow(self, user_idea: str, conversation_history: list):
        """
        Uses the dispatcher to route to the appropriate workflow.
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

            # Try to parse dispatcher decision
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
                # No clear dispatch target - default to chat for ambiguous requests
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
        self.log("info", f"Running Sentry check on: {file_path}")

        prompt = SENTRY_PROMPT.format(file_path=file_path, file_contents=file_contents)

        provider, model = self.llm_client.get_model_for_role("sentry")
        if not provider or not model:
            self.log("warning", "No 'sentry' model configured. Skipping quality check.")
            return None

        try:
            response_str = "".join(
                [chunk async for chunk in self.llm_client.stream_chat(provider, model, prompt, "sentry")])

            tool_call = self._parse_json_response(response_str)

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
            self.handle_error("Aura", "No 'replanner' model configured.")
            return

        try:
            response_str = "".join(
                [chunk async for chunk in self.llm_client.stream_chat(provider, model, prompt, "replanner")])

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
            self.log("warning", "No 'summarizer' model configured. Using basic summary.")
            return f"Mission with {len(mission_log)} tasks"

        try:
            response_str = "".join(
                [chunk async for chunk in self.llm_client.stream_chat(provider, model, prompt, "summarizer")])

            return response_str.strip()

        except Exception as e:
            self.log("error", f"Mission summarizer failed: {e}")
            return f"Mission with {len(mission_log)} tasks"