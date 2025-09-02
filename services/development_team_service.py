# services/development_team_service.py
from __future__ import annotations
import json
import re
from typing import TYPE_CHECKING, Dict, List, Optional, Any

from event_bus import EventBus
from core.prompt_templates.architect import ArchitectPrompt
from core.prompt_templates.creative import CreativeAssistantPrompt
from core.prompt_templates.iterative_architect import IterativeArchitectPrompt
from core.prompt_templates.coder import CoderPrompt
from core.prompt_templates.replan import RePlannerPrompt
from core.prompt_templates.sentry import SENTRY_PROMPT
from core.prompt_templates.summarizer import MissionSummarizerPrompt
from events import PlanReadyForReview, MissionDispatchRequest, PostChatMessage

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

    def _post_chat_message(self, sender: str, message: str, is_error: bool = False):
        if message and message.strip():
            self.event_bus.emit("post_chat_message", PostChatMessage(sender, message, is_error))

    def _parse_json_response(self, response: str) -> dict:
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if not match:
            raise ValueError(f"No JSON object found in the response. Raw response: {response}")
        return json.loads(match.group(0))

    async def handle_user_prompt(self, user_idea: str, conversation_history: list):
        """
        Primary entry point for a user's message.
        Routes to the appropriate workflow based on the mission log's state.
        """
        pending_tasks = self.mission_log_service.get_tasks(done=False)
        if not pending_tasks:
            self.log("info", "No pending tasks. Starting creative assistant workflow.")
            await self.run_creative_assistant_workflow(user_idea, conversation_history)
        else:
            self.log("info", "Pending tasks exist. Starting iterative architect workflow.")
            await self.run_iterative_architect_workflow(user_idea, conversation_history)

    async def run_creative_assistant_workflow(self, user_idea: str, conversation_history: list):
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

        # Look for a tool call block
        tool_call_match = re.search(r'\[TOOL_CALL\](.*?)\[/TOOL_CALL\]', response_str, re.DOTALL)
        conversational_text = re.sub(r'\[TOOL_CALL\].*?\[/TOOL_CALL\]', '', response_str).strip()

        # Post the conversational part back to the user
        if conversational_text:
            self._post_chat_message("Aura", conversational_text)

        # If a tool call was found, execute it
        if tool_call_match:
            try:
                tool_call_str = tool_call_match.group(1)
                tool_call_data = json.loads(tool_call_str)
                self.log("info", f"Creative assistant identified a task: {tool_call_data}")
                # This will add the task to the mission log
                await self.tool_runner_service.run_tool_by_dict(tool_call_data)
                self.event_bus.emit("plan_ready_for_review", PlanReadyForReview())
            except (json.JSONDecodeError, KeyError) as e:
                self.handle_error("Aura", f"Invalid tool call format from creative assistant: {e}")
                self.log("error", f"Creative assistant tool call failure. Raw block: {tool_call_match.group(0)}")


    async def run_iterative_architect_workflow(self, user_request: str, conversation_history: list):
        """
        Handles a user's request to modify an existing plan or codebase.
        """
        self.log("info", f"Iterative architect workflow initiated for: '{user_request[:50]}...'")
        self.event_bus.emit("agent_status_changed", "Aura", "Updating the plan...", "fa5s.pencil-ruler")

        provider, model = self.llm_client.get_model_for_role("architect")
        if not provider or not model:
            self.handle_error("Aura", "No 'architect' model configured.")
            return

        # Gather context
        file_structure = "\n".join(sorted(self.project_manager.get_project_files().keys())) or "The project is currently empty."
        available_tools = json.dumps(self.foundry_manager.get_llm_tool_definitions(), indent=2)
        
        # For now, we'll pass an empty string for RAG snippets. This can be enhanced later.
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


    async def run_aura_planner_workflow(self, user_idea: str, conversation_history: list):
        """
        The main entry point for a user request. It generates a new plan.
        """
        self.log("info", f"Aura planner workflow initiated for: '{user_idea[:50]}...'")

        provider, model = self.llm_client.get_model_for_role("planner")
        if not provider or not model:
            self.handle_error("Aura", "No 'planner' model configured.")
            return

        self.event_bus.emit("agent_status_changed", "Aura", "Formulating an efficient plan...", "fa5s.lightbulb")
        
        prompt_template = ArchitectPrompt()
        conv_history_str = "\n".join([f"{msg['role']}: {msg['content']}" for msg in conversation_history])
        prompt = prompt_template.render(user_idea=user_idea, conversation_history=conv_history_str)

        response_str = "".join(
            [chunk async for chunk in self.llm_client.stream_chat(provider, model, prompt, "planner")])

        try:
            plan_data = self._parse_json_response(response_str)
            plan_steps = plan_data.get("plan", [])
            if not plan_steps:
                raise ValueError("Aura's plan was empty or malformed.")
            self.mission_log_service.set_initial_plan(plan_steps, user_idea)
            self._post_chat_message("Aura",
                                    "I've created a plan to build your project. Please review it in the 'Agent TODO' list and click 'Dispatch Aura' to begin execution.")
            self.event_bus.emit("plan_ready_for_review", PlanReadyForReview())
        except (ValueError, json.JSONDecodeError) as e:
            self.handle_error("Aura", f"Failed to create a valid plan: {e}.")
            self.log("error", f"Aura planner failure. Raw response: {response_str}")

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

        response_str = "".join([chunk async for chunk in self.llm_client.stream_chat(provider, model, prompt, "sentry")])

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
        self.event_bus.emit("agent_status_changed", "Aura", "Hitting a roadblock. Rethinking the plan...",
                            "fa5s.search")

        mission_log_str = "\n".join(
            [f"- ID {t['id']} ({'Done' if t['done'] else 'Pending'}): {t['description']}" for t in mission_log])
        failed_task_str = f"ID {failed_task['id']}: {failed_task['description']}"
        error_message = failed_task.get('last_error', 'No specific error message was recorded.')

        prompt_template = RePlannerPrompt()
        prompt = prompt_template.render(
            user_goal=original_goal,
            mission_log=mission_log_str,
            failed_task=failed_task_str,
            error_message=error_message
        )

        provider, model = self.llm_client.get_model_for_role("planner")
        if not provider or not model:
            self.handle_error("Aura", "No 'planner' model available for re-planning.")
            return

        response_str = "".join(
            [chunk async for chunk in self.llm_client.stream_chat(provider, model, prompt, "planner")])

        try:
            new_plan_data = self._parse_json_response(response_str)
            new_plan_steps = new_plan_data.get("plan", [])
            if not new_plan_steps:
                raise ValueError("Re-planner returned an empty or malformed plan.")

            self.mission_log_service.replace_tasks_from_id(failed_task['id'], new_plan_steps)
            self.log("success", f"Successfully replaced failed task with a new plan of {len(new_plan_steps)} steps.")
        except (ValueError, json.JSONDecodeError) as e:
            self.handle_error("Aura", f"I failed to create a valid recovery plan: {e}")
            self.log("error", f"Aura re-planner failure. Raw response: {response_str}")

    async def generate_mission_summary(self, completed_tasks: List[Dict]) -> str:
        """Generates a final summary of the completed mission."""
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
