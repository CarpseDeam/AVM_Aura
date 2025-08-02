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

    def __init__(self, model_name: str, host: str = "http://localhost:11434") -> None:
        self.model_name = model_name
        self.api_url = f"{host}/api/generate"
        logger.info(f"OllamaProvider initialized for model '{model_name}' at {self.api_url}")

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

            # --- THIS IS THE NEW, STRICTER PROMPT ---
            tool_prompt = (
                "You are the OPERATOR of a deterministic virtual machine. Your SOLE PURPOSE is to translate user requests into JSON tool calls.\n"
                "You MUST respond with ONLY a single, valid JSON object that conforms to the schema of one of the available tools. Do NOT provide any commentary, conversational text, code examples, or explanations. Your entire response must be ONLY the JSON tool call.\n"
                "If the user's request is ambiguous or you cannot fulfill it with the available tools, you must respond with a JSON object containing an 'error' key and a 'message' explaining the issue.\n\n"
                "Here are the available tools:\n"
                f"{tool_definitions}"
            )
            # --- END NEW PROMPT ---
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

            # If we requested JSON for tool-calling, attempt to parse it.
            # We are now much more confident the response WILL be JSON.
            if tools:
                try:
                    # The response from Ollama with format=json is already a parsed dict
                    # if the library handles it, but often it's a string needing parsing.
                    if isinstance(text_response, str):
                        parsed_json = json.loads(text_response)
                    else:
                        parsed_json = text_response

                    if isinstance(parsed_json, dict) and "tool_name" in parsed_json:
                        logger.info(f"Ollama simulated a tool call: {parsed_json.get('tool_name')}")
                        if "arguments" not in parsed_json:
                            parsed_json["arguments"] = {}
                        return parsed_json
                    else:
                        logger.info("Ollama returned valid JSON, but it was not a tool call. Treating as text.")
                        return json.dumps(parsed_json, indent=2)  # Return as formatted string
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