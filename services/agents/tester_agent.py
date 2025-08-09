# services/agents/tester_agent.py
from __future__ import annotations
import re
from typing import TYPE_CHECKING, Optional

from event_bus import EventBus
from prompts.tester import TESTER_PROMPT

if TYPE_CHECKING:
    from core.managers.service_manager import ServiceManager


class TesterAgent:
    """
    A specialized agent responsible for generating pytest tests for a given file.
    """

    def __init__(self, service_manager: "ServiceManager"):
        self.service_manager = service_manager
        self.event_bus = service_manager.event_bus
        self.llm_client = service_manager.get_llm_client()

    async def generate_tests_for_file(self, source_code_to_test: str, filename_to_test: str) -> Optional[str]:
        """
        Takes source code and generates pytest tests for it.
        """
        self.log("info", f"TesterAgent received request to generate tests for '{filename_to_test}'.")
        prompt = TESTER_PROMPT.format(
            filename_to_test=filename_to_test,
            source_code_to_test=source_code_to_test
        )

        provider, model = self.llm_client.get_model_for_role("tester")
        if not provider or not model:
            self.log("error", "No model configured for 'tester' role. Skipping test generation.")
            return None

        self.log("ai_call", f"Asking {provider}/{model} to write tests for {filename_to_test}...")

        raw_test_code = ""
        try:
            async for chunk in self.llm_client.stream_chat(provider, model, prompt, "tester"):
                raw_test_code += chunk

            cleaned_code = self._robustly_clean_llm_output(raw_test_code)
            self.log("success", f"Successfully generated tests for '{filename_to_test}'.")
            return cleaned_code
        except Exception as e:
            self.log("error", f"LLM generation failed for tests of {filename_to_test}: {e}")
            return None

    def _robustly_clean_llm_output(self, content: str) -> str:
        content = content.strip()
        code_block_regex = re.compile(r'```(?:python)?\n(.*?)\n```', re.DOTALL)
        match = code_block_regex.search(content)
        if match:
            return match.group(1).strip()
        return content

    def log(self, level: str, message: str):
        self.event_bus.emit("log_message_received", "TesterAgent", level, message)