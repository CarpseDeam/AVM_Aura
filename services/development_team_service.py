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

        try:
            response_str = "".join(
                [chunk async for chunk in self.llm_client.stream_chat(provider, model, prompt, "dispatcher")])

            decision_data = self._parse_json_response(response_str)
            dispatch_to = decision_data.get("dispatch_to")
            self.log("info", f"Chief of Staff dispatched to: {dispatch_to}")

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

        except (ValueError, json.JSONDecodeError) as e:
            self.log("warning", f"Dispatcher failed: {e}. Falling back to direct planning.")
            await self._run_direct_planning_workflow(user_idea, conversation_history)

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
                            self.log("info", f"Processing {len(plan_steps)} plan steps...")

                            # Convert plan steps to task descriptions
                            task_descriptions = []
                            for step in plan_steps:
                                if isinstance(step, dict):
                                    # Handle tool call format from JSON plan
                                    if "tool_name" in step and "parameters" in step:
                                        # Extract task description from parameters
                                        params = step["parameters"]
                                        if "task_description" in params:
                                            task_descriptions.append(params["task_description"])
                                        elif "project_name" in params:
                                            task_descriptions.append(f"Create project: {params['project_name']}")
                                        else:
                                            task_descriptions.append(f"Execute {step['tool_name']}")
                                    elif "description" in step:
                                        task_descriptions.append(step["description"])
                                    else:
                                        # Convert dict to string representation
                                        task_descriptions.append(str(step)[:100])
                                else:
                                    # Handle string descriptions
                                    task_descriptions.append(str(step))

                            if task_descriptions:
                                # Set the initial plan in mission log
                                self.mission_log_service.set_initial_plan(task_descriptions, user_idea)
                                self.log("info", f"Added {len(task_descriptions)} tasks to mission log.")

                                # Notify user
                                self._post_chat_message("Aura",
                                                        "I've created a plan to build your project. Please review it in the 'Agent TODO' list and click 'Dispatch Aura' to begin execution.")

                                # Emit plan ready event
                                self.event_bus.emit("plan_ready_for_review", PlanReadyForReview())
                            else:
                                raise ValueError("No valid task descriptions could be extracted from plan.")
                        else:
                            raise ValueError("Plan was empty or malformed.")

                    except (ValueError, json.JSONDecodeError) as e:
                        self.handle_error("Aura", f"Failed to parse the plan: {e}")
                        self.log("error", f"Plan parsing failure. Raw JSON: {message.content}")
                else:
                    # Handle other message types (thoughts, responses, etc.)
                    self._post_structured_message(message)

        except Exception as e:
            self.handle_error("Aura", f"Direct planning workflow failed: {str(e)}")
            self.log("error", f"Direct planning failure. Error: {e}")
        finally:
            self.event_bus.emit("processing_finished")

    async def run_aura_planner_workflow(self, user_idea: str, conversation_history: list):
        """
        Legacy method - redirects to direct planning workflow.
        """
        await self._run_direct_planning_workflow(user_idea, conversation_history)

    async def run_coding_task(self, task: Dict[str, any], last_error: Optional[str] = None) -> Optional[Dict[str, str]]:
        """
        Asks the Coder AI to translate a single natural language task into an
        executable tool call, providing it with full context including past attempts.
        """
        if task.get("tool_call"):
            self.log("info", f"Using pre-defined tool call for task: {task['description']}")
            return task["tool_call"]

        current_task_description = task['description']
        self.log("info", f"Coder translating task to tool call: {current_task_description}")
        self.event_bus.emit("agent_status_changed", "Aura", f"Coding task: {current_task_description}...", "fa5s.cogs")

        log_tasks = self.mission_log_service.get_tasks()
        mission_log_history = "\n".join(
            [f"- ID {t['id']} ({'Done' if t['done'] else 'Pending'}): {t['description']}" for t in log_tasks])
        if not mission_log_history:
            mission_log_history = "The mission log is empty. This is the first task."

        if last_error:
            current_task_description += f"\n\n**PREVIOUS ATTEMPT FAILED!** The last attempt to perform this task failed with the following error: `{last_error}`. You MUST analyze this error and try a different tool or different arguments to succeed."

        vector_context = "No existing code snippets were found."
        if self.vector_context_service and self.vector_context_service.collection.count() > 0:
            try:
                retrieved_chunks = self.vector_context_service.query(current_task_description, n_results=5)
                if retrieved_chunks:
                    context_parts = [
                        f"```python\n# From: {chunk['metadata'].get('file_path', 'N/A')}\n{chunk['document']}\n```" for
                        chunk in retrieved_chunks]
                    vector_context = "\n\n".join(context_parts)
            except Exception as e:
                self.log("error", f"Failed to query vector context: {e}")

        file_structure = "\n".join(
            sorted(self.project_manager.get_project_files().keys())) or "The project is currently empty."
        available_tools = json.dumps(self.foundry_manager.get_llm_tool_definitions(), indent=2)

        prompt_template = CoderPrompt()
        prompt = prompt_template.render(
            current_task=current_task_description,
            mission_log=mission_log_history,
            available_tools=available_tools,
            file_structure=file_structure,
            relevant_code_snippets=vector_context
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
        self.event_bus.emit("agent_status_changed", "Aura", "Hitting a roadblock. Re-planning strategy...",
                            "fa5s.route")

        prompt_template = RePlannerPrompt()
        prompt = prompt_template.render(
            original_goal=original_goal,
            failed_task=failed_task,
            mission_log=mission_log
        )

        provider, model = self.llm_client.get_model_for_role("replanner")
        if not provider or not model:
            self.log("error", "No 're-planner' model configured.")
            self.handle_error("Aura", "No 're-planner' model configured.")
            return

        response_str = "".join(
            [chunk async for chunk in self.llm_client.stream_chat(provider, model, prompt, "replanner")])

        try:
            replan_data = self._parse_json_response(response_str)
            new_plan_steps = replan_data.get("new_plan", [])

            if not new_plan_steps:
                self.handle_error("Aura", "Re-planner returned an empty plan.")
                return

            failed_task_id = failed_task.get('id')
            if failed_task_id:
                self.mission_log_service.replace_tasks_from_id(failed_task_id, new_plan_steps)
                self.log("info", f"Strategic re-plan complete. Replaced tasks starting from ID {failed_task_id}.")
            else:
                self.log("error", "Failed task missing ID - cannot replace tasks.")

        except (ValueError, json.JSONDecodeError) as e:
            self.handle_error("Aura", f"Re-planner failed to create a valid plan: {e}")
            self.log("error", f"Re-planner failure. Raw response: {response_str}")

    async def generate_mission_summary(self, completed_tasks: List[Dict]) -> str:
        """
        Creates a celebratory summary when the mission is complete.
        """
        self.log("info", "Generating mission summary.")
        self.event_bus.emit("agent_status_changed", "Aura", "Generating mission summary...", "fa5s.pen-fancy")

        task_descriptions = "\n".join([f"- {task['description']}" for task in completed_tasks if task['done']])
        if not task_descriptions:
            return "Mission accomplished, although no specific tasks were marked as completed in the log."

        prompt_template = MissionSummarizerPrompt()
        prompt = prompt_template.render(completed_tasks=task_descriptions)

        provider, model = self.llm_client.get_model_for_role("chat")
        if not provider or not model:
            self.log("error", "No 'chat' model available for summary generation.")
            return "Mission accomplished!"

        summary = "".join([chunk async for chunk in self.llm_client.stream_chat(provider, model, prompt, "chat")])
        return summary.strip() if summary.strip() else "Mission accomplished!"

    def handle_error(self, agent: str, error_msg: str):
        self.log("error", f"{agent} failed: {error_msg}")
        self.event_bus.emit("agent_status_changed", "Aura", "Failed", "fa5s.exclamation-triangle")
        self._post_chat_message("Aura", error_msg, is_error=True)

    def log(self, level: str, message: str):
        self.event_bus.emit("log_message_received", "DevTeamService", level, message)