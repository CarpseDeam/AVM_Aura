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

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """
    An LLM provider for local models served via the Ollama API.

    This provider simulates tool-calling by constructing a strict system prompt
    that instructs the model to return a JSON object when it needs to use a tool.
    """

    # <-- MODIFIED: Add temperature to the constructor
    def __init__(self, model_name: str, host: str = "http://localhost:11434", temperature: float = 0.1) -> None:
        self.model_name = model_name
        self.api_url = f"{host}/api/generate"
        self.temperature = temperature # <-- NEW: Store temperature
        logger.info(f"OllamaProvider initialized for model '{model_name}' at {self.api_url} with temperature {self.temperature}")

    def _create_system_prompt(
            self,
            context: Optional[Dict[str, str]],
            tools: Optional[List[Dict[str, Any]]],
    ) -> str:
        """
        Creates a system prompt incorporating context and/or tool instructions.
        """
        prompt_parts = []

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

            # --- MODIFIED: Updated system prompt to include multi-step planning ---
            tool_prompt = (
                "You are the OPERATOR of a deterministic virtual machine. You are a component in a deterministic program. "
                "Your SOLE PURPOSE is to translate user requests into JSON tool calls. "
                "You MUST respond with ONLY a single, valid JSON object. "
                "For simple, single-step tasks, this will be a tool call object. "
                "For complex requests that require multiple steps, you MUST respond with a single JSON object containing a 'plan' key. The value of 'plan' must be a list of tool call objects, to be executed in order. "
                "Do NOT provide any commentary, conversational text, code examples, or explanations. Your entire response must be ONLY the JSON object.\n"
                "If you cannot fulfill the request, respond with: {\"tool_name\": \"error\", \"arguments\": {\"message\": \"Request cannot be fulfilled.\"}}\n\n"
                "Here are the available tools:\n"
                f"{tool_definitions}"
            )
            # --- END MODIFIED PROMPT ---
            prompt_parts.append(tool_prompt)

        return "\n\n".join(prompt_parts)

    def get_response(
            self,
            prompt: str,
            context: Optional[Dict[str, str]] = None,
            tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Union[str, Dict[str, Any]]:
        """
        Sends the prompt to the Ollama /api/generate endpoint and returns the response.
        """
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            # <-- NEW: Add options to the payload, including temperature
            "options": {
                "temperature": self.temperature
            }
        }

        system_prompt = self._create_system_prompt(context, tools)
        if system_prompt:
            payload["system"] = system_prompt
            logger.debug("Injecting system prompt with context and/or tool definitions.")

        if tools:
            payload["format"] = "json"
            logger.debug("Tools provided. Requesting JSON format.")

        logger.debug(f"Sending payload to Ollama: {payload}")

        try:
            response = requests.post(self.api_url, json=payload, timeout=120)
            response.raise_for_status()

            response_data = response.json()
            text_response = response_data.get("response", "").strip()

            if not text_response:
                logger.warning("Ollama response was empty.")
                return "Error: Received an empty response from Ollama."

            if tools:
                try:
                    if isinstance(text_response, str):
                        parsed_json = json.loads(text_response)
                    else:
                        parsed_json = text_response

                    if isinstance(parsed_json, dict) and ("tool_name" in parsed_json or "plan" in parsed_json):
                        logger.info(f"Ollama simulated a tool call or plan.")
                        return parsed_json
                    else:
                        logger.info("Ollama returned valid JSON, but it was not a tool call. Treating as text.")
                        return json.dumps(parsed_json, indent=2)
                except json.JSONDecodeError:
                    logger.warning("Ollama did not return valid JSON for a tool call. Returning as plain text.")
                    return text_response

            logger.info("Successfully received text response from Ollama.")
            return text_response

        except requests.exceptions.RequestException as e:
            logger.error(f"An HTTP error occurred while communicating with Ollama: {e}", exc_info=True)
            return f"Error communicating with Ollama server: {e}"
        except Exception as e:
            logger.error(f"An unexpected error occurred in OllamaProvider: {e}", exc_info=True)
            return f"An unexpected error occurred: {e}"