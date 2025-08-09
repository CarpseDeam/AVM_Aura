# services/agents/architect_service.py
from __future__ import annotations
import json
import re
from typing import TYPE_CHECKING, Dict, Optional

from event_bus import EventBus
from prompts import HIERARCHICAL_PLANNER_PROMPT, MODIFICATION_PLANNER_PROMPT

if TYPE_CHECKING:
    from core.managers.service_manager import ServiceManager


class ArchitectService:
    def __init__(self, service_manager: "ServiceManager"):
        self.service_manager = service_manager
        self.event_bus = service_manager.event_bus
        self.llm_client = service_manager.get_llm_client()

    async def generate_plan(self, prompt: str, existing_files: Optional[Dict[str, str]] = None) -> Optional[Dict]:
        """
        Generates a structured plan for either a new project or modifying an existing one.
        """
        self.log("info", "Architect phase started.")

        if existing_files:
            plan_prompt = MODIFICATION_PLANNER_PROMPT.format(
                prompt=prompt,
                full_code_context=json.dumps(existing_files, indent=2)
            )
        else:
            plan_prompt = HIERARCHICAL_PLANNER_PROMPT.format(prompt=prompt)

        return await self._get_plan_from_llm(plan_prompt)

    async def _get_plan_from_llm(self, plan_prompt: str) -> Optional[Dict]:
        provider, model = self.llm_client.get_model_for_role("architect")
        if not provider or not model:
            self.log("error", "No model configured for architect role.")
            return None

        raw_plan_response = ""
        try:
            async for chunk in self.llm_client.stream_chat(provider, model, plan_prompt, "architect"):
                raw_plan_response += chunk

            plan = self._parse_json_response(raw_plan_response)
            if not plan or not isinstance(plan.get("files"), list):
                raise ValueError("AI did not return a valid file plan in JSON format.")

            self.log("success", f"Architect created plan with {len(plan['files'])} file(s).")
            return plan
        except (json.JSONDecodeError, ValueError) as e:
            self.log("error", f"Plan creation failed: {e}\nResponse: {raw_plan_response}")
            return None
        except Exception as e:
            self.log("error", f"An unexpected error during planning: {e}")
            return None

    def _parse_json_response(self, response: str) -> dict:
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if not match:
            raise ValueError("No JSON object found in the response.")
        return json.loads(match.group(0))

    def log(self, level: str, message: str):
        self.event_bus.emit("log_message_received", "ArchitectService", level, message)