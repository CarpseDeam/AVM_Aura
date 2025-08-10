# services/agents/generation_coordinator.py
from __future__ import annotations
import json
import re
from typing import TYPE_CHECKING, Dict, Any, Optional
from pathlib import Path

from event_bus import EventBus
from prompts import CODER_PROMPT, SIMPLE_FILE_PROMPT
from prompts.master_rules import RAW_CODE_OUTPUT_RULE, TYPE_HINTING_RULE, DOCSTRING_RULE

if TYPE_CHECKING:
    from core.managers.service_manager import ServiceManager


class GenerationCoordinator:
    def __init__(self, service_manager: "ServiceManager"):
        self.service_manager = service_manager
        self.event_bus = service_manager.event_bus
        self.llm_client = service_manager.get_llm_client()
        self.project_manager = service_manager.get_project_manager()

    async def coordinate_generation(self, plan: Dict[str, Any], existing_files: Optional[Dict[str, str]]) -> Optional[
        Dict[str, str]]:
        self.log("info", "Code generation phase started.")
        generated_files = {}

        # --- THIS IS THE FIX ---
        # The Coder should not be responsible for declarative dependency files.
        # This is the Finalizer's job, using the correct tool.
        files_to_generate = [f for f in plan.get("files", []) if f.get("filename") != "requirements.txt"]

        total_files = len(files_to_generate)

        for i, file_info in enumerate(files_to_generate):
            filename = file_info["filename"]
            self.event_bus.emit("agent_status_changed", "Coder", f"Writing {filename}...", "fa5s.keyboard")
            self.log("info", f"Generating file {i + 1}/{total_files}: {filename}")

            generated_content = await self._generate_single_file(file_info, plan, existing_files, generated_files)
            if generated_content is None:
                self.log("error", f"Failed to generate content for {filename}.")
                return None  # Fail the whole process if one file fails

            cleaned_content = self._robustly_clean_llm_output(generated_content)
            generated_files[filename] = cleaned_content

        self.log("success", f"Code generation phase complete. {len(generated_files)} files created.")
        return generated_files

    async def _generate_single_file(self, file_info: Dict[str, str], plan: Dict, existing_files: Dict,
                                    generated_files_this_session: Dict) -> Optional[str]:
        filename = file_info["filename"]
        file_extension = Path(filename).suffix

        prompt = self._build_prompt(file_info, plan, existing_files, generated_files_this_session)
        if not prompt:
            return None

        provider, model = self.llm_client.get_model_for_role("coder")
        if not provider or not model:
            self.log("error", f"No model for 'coder' role. Cannot generate {filename}.")
            return None

        file_content = ""
        try:
            async for chunk in self.llm_client.stream_chat(provider, model, prompt, "coder"):
                file_content += chunk
                self.event_bus.emit("stream_code_chunk", filename, chunk)
            return file_content
        except Exception as e:
            self.log("error", f"LLM generation failed for {filename}: {e}")
            return None

    def _build_prompt(self, file_info, plan, existing_files, generated_files_this_session):
        filename = file_info["filename"]
        if filename.endswith('.py'):
            is_modification = filename in (existing_files or {})
            original_code_section = ""
            if is_modification:
                original_code = existing_files.get(filename, "")
                original_code_section = f"--- ORIGINAL CODE OF `{filename}` (You are modifying this file): ---\n```python\n{original_code}\n```"

            # Rolling context of already generated files
            code_context_json = json.dumps({k: v for k, v in generated_files_this_session.items() if k != filename},
                                           indent=2)

            return CODER_PROMPT.format(
                filename=filename,
                purpose=file_info.get("purpose", ""),
                original_code_section=original_code_section,
                file_plan_json=json.dumps(plan, indent=2),
                code_context_json=code_context_json,
                TYPE_HINTING_RULE=TYPE_HINTING_RULE.strip(),
                DOCSTRING_RULE=DOCSTRING_RULE.strip(),
                RAW_CODE_OUTPUT_RULE=RAW_CODE_OUTPUT_RULE.strip()
            )
        else:
            return SIMPLE_FILE_PROMPT.format(
                filename=filename,
                purpose=file_info.get("purpose", ""),
                file_plan_json=json.dumps(plan, indent=2)
            )

    def _robustly_clean_llm_output(self, content: str) -> str:
        content = content.strip()
        code_block_regex = re.compile(r'```(?:[a-zA-Z0-9_]*)?\n(.*?)\n```', re.DOTALL)
        match = code_block_regex.search(content)
        if match:
            return match.group(1).strip()
        return content

    def log(self, level: str, message: str):
        self.event_bus.emit("log_message_received", "GenCoordinator", level, message)
