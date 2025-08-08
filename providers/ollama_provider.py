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

    def get_response(
            self,
            prompt: str,
            mode: str,
            context: Optional[Dict[str, str]] = None,
            tools: Optional[List[Dict[str, Any]]] = None,
            system_instruction_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Sends the prompt to the Ollama /api/generate endpoint and returns a structured response.
        """
        if not system_instruction_override:
            raise ValueError("A system_instruction_override must be provided by the calling service.")
        system_prompt = system_instruction_override

        temp = self.plan_temperature if mode == 'plan' else self.build_temperature

        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "system": system_prompt,
            "stream": False,
            "options": {"temperature": temp}
        }

        is_json_mode = mode == 'build'
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
                    if mode == 'plan' and 'reasoning' in data:
                        structured_response['text'] = data.pop('reasoning')

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