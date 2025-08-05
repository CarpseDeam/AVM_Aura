# providers/ollama_provider.py
"""
Implement the LLMProvider interface for local models served via Ollama,
handling all HTTP request logic.
"""
import logging
import json
import requests
from typing import Any, Dict, List, Optional, Union
from .base import LLMProvider
from prompts import ARCHITECT_SYSTEM_PROMPT, OPERATOR_SYSTEM_PROMPT
from services.config_manager import ConfigManager

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """
    An LLM provider for local models served via the Ollama API.

    This provider simulates tool-calling by constructing a strict system prompt
    that instructs the model to return a JSON object when it needs to use a tool.
    """

    def __init__(self, config: ConfigManager) -> None:
        self.model_name = config.get('ollama.model')
        host = config.get('ollama.host')
        self.api_url = f"{host}/api/generate"
        self.plan_temperature = config.get('plan_temperature')
        self.build_temperature = config.get('build_temperature')
        logger.info(
            f"OllamaProvider initialized for model '{self.model_name}' at {self.api_url} with temps (Plan: {self.plan_temperature}, Build: {self.build_temperature})")

    def _create_system_prompt(
            self,
            mode: str,
            context: Optional[Dict[str, str]],
            tools: Optional[List[Dict[str, Any]]],
    ) -> str:
        """
        Creates a system prompt incorporating role, context, and/or tool instructions.
        """
        if mode == 'plan':
            role_prompt = ARCHITECT_SYSTEM_PROMPT
        elif mode == 'build':
            role_prompt = OPERATOR_SYSTEM_PROMPT
        else:
            raise ValueError(f"Unknown mode '{mode}' provided to OllamaProvider.")

        prompt_parts = [role_prompt]

        if context:
            context_header = "You have the following information in your working memory. Use it to inform your actions."
            context_block_parts = ["--- CONTEXT ---"]
            for key, content in context.items():
                context_block_parts.append(f"Content of file '{key}':\n```\n{content}\n```")
            context_block_parts.append("--- END CONTEXT ---")

            full_context_block = f"{context_header}\n\n" + "\n".join(context_block_parts)
            prompt_parts.append(full_context_block)

        if tools:
            tool_definitions = json.dumps(tools, indent=2)
            tool_block = f"Here are the available tools:\n{tool_definitions}"
            prompt_parts.append(tool_block)

        return "\n\n".join(prompt_parts)

    def get_response(
            self,
            prompt: str,
            mode: str,
            context: Optional[Dict[str, str]] = None,
            tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Union[str, Dict[str, Any]]:
        """
        Sends the prompt to the Ollama /api/generate endpoint and returns the response.
        """
        temp = self.plan_temperature if mode == 'plan' else self.build_temperature

        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temp
            }
        }

        system_prompt = self._create_system_prompt(mode, context, tools)
        if system_prompt:
            payload["system"] = system_prompt
            logger.debug(f"Injecting system prompt for mode '{mode}'.")

        if mode == 'build':
            payload["format"] = "json"
            logger.debug("Build mode active. Requesting JSON format.")

        logger.debug(f"Sending payload to Ollama: {payload}")

        try:
            response = requests.post(self.api_url, json=payload, timeout=120)
            response.raise_for_status()

            response_data = response.json()
            text_response = response_data.get("response", "").strip()

            if not text_response:
                logger.warning("Ollama response was empty.")
                return "Error: Received an empty response from Ollama."

            if payload.get("format") == "json":
                try:
                    if isinstance(text_response, str):
                        parsed_json = json.loads(text_response)
                    else:
                        parsed_json = text_response

                    if isinstance(parsed_json, dict) and ("tool_name" in parsed_json or "plan" in parsed_json):
                        logger.info("Ollama simulated a tool call or plan.")
                        return parsed_json
                    else:
                        logger.info("Ollama returned valid JSON, but it was not a tool call. Treating as text.")
                        return json.dumps(parsed_json, indent=2)
                except json.JSONDecodeError:
                    if mode == 'build':
                        logger.warning("Ollama did not return valid JSON for a tool call in 'build' mode.")
                    return text_response

            logger.info("Successfully received text response from Ollama.")
            return text_response

        except requests.exceptions.RequestException as e:
            logger.error(f"An HTTP error occurred while communicating with Ollama: {e}", exc_info=True)
            return f"Error communicating with Ollama server: {e}"
        except Exception as e:
            logger.error(f"An unexpected error occurred in OllamaProvider: {e}", exc_info=True)
            return f"An unexpected error occurred: {e}"