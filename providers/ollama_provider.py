# providers/ollama_provider.py
"""
Implement the LLMProvider interface for local models served via Ollama,
handling all HTTP request logic.
"""
import logging
import json
import requests
from typing import Any, Dict, List, Optional

from .base import LLMProvider
from prompts import ARCHITECT_SYSTEM_PROMPT, OPERATOR_SYSTEM_PROMPT
from services.config_manager import ConfigManager

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """
    An LLM provider for local models served via the Ollama API.
    """

    def __init__(self, config: ConfigManager) -> None:
        self.model_name = config.get('ollama.model')
        host = config.get('ollama.host')
        self.api_url = f"{host}/api/generate"
        self.plan_temperature = config.get('plan_temperature')
        self.build_temperature = config.get('build_temperature')
        logger.info(
            f"OllamaProvider initialized for model '{self.model_name}' at {self.api_url} with temps (Plan: {self.plan_temperature}, Build: {self.build_temperature})")

    def _create_system_prompt(self, mode: str, context: Optional[Dict[str, str]], tools: Optional[List[Dict[str, Any]]]) -> str:
        role_prompt = ARCHITECT_SYSTEM_PROMPT if mode == 'plan' else OPERATOR_SYSTEM_PROMPT
        prompt_parts = [role_prompt]
        if context:
            context_block = "\n".join([f"Content of file '{k}':\n```\n{v}\n```" for k, v in context.items()])
            prompt_parts.append(f"--- CONTEXT ---\n{context_block}\n--- END CONTEXT ---")
        if tools:
            tool_definitions = json.dumps(tools, indent=2)
            tool_block = f"Here are the available tools you can call in your JSON response:\n{tool_definitions}"
            prompt_parts.append(tool_block)
        return "\n\n".join(prompt_parts)

    def get_response(
            self,
            prompt: str,
            mode: str,
            context: Optional[Dict[str, str]] = None,
            tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Sends the prompt to the Ollama /api/generate endpoint and returns a structured response.
        """
        temp = self.plan_temperature if mode == 'plan' else self.build_temperature
        system_prompt = self._create_system_prompt(mode, context, tools)
        payload = {"model": self.model_name, "prompt": prompt, "system": system_prompt, "stream": False, "options": {"temperature": temp}}
        is_json_mode = mode == 'build' or (mode == 'plan' and tools)
        if is_json_mode:
            payload["format"] = "json"

        structured_response = {"text": None, "tool_calls": []}

        try:
            response = requests.post(self.api_url, json=payload, timeout=120)
            response.raise_for_status()
            raw_response = response.json().get("response", "").strip()

            if not raw_response:
                structured_response["text"] = "Error: Received an empty response from Ollama."
                return structured_response

            if is_json_mode:
                try:
                    data = json.loads(raw_response)
                    # For plan mode, we look for a text explanation inside the JSON
                    if mode == 'plan' and 'reasoning' in data:
                        structured_response['text'] = data.pop('reasoning')

                    # The remaining data is assumed to be a tool call or plan
                    if "tool_name" in data:
                        structured_response["tool_calls"].append(data)
                    elif "plan" in data and isinstance(data['plan'], list):
                        structured_response["tool_calls"] = data['plan']
                except json.JSONDecodeError:
                    structured_response["text"] = raw_response
            else:
                structured_response["text"] = raw_response

            return structured_response

        except requests.exceptions.RequestException as e:
            logger.error(f"An HTTP error occurred while communicating with Ollama: {e}", exc_info=True)
            structured_response["text"] = f"Error communicating with Ollama server: {e}"
            return structured_response
        except Exception as e:
            logger.error(f"An unexpected error occurred in OllamaProvider: {e}", exc_info=True)
            structured_response["text"] = f"An unexpected error occurred: {e}"
            return structured_response