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

    This provider simulates tool-calling by constructing a system prompt
    that instructs the model to return a JSON object when it needs to use a tool.
    It also injects contextual information (like file contents) into the system
    prompt to provide working memory for the model.
    """

    def __init__(self, model_name: str, host: str = "http://localhost:11434") -> None:
        """
        Initializes the Ollama provider.

        Args:
            model_name: The name of the model to use (e.g., "llama3").
            host: The host address of the Ollama server.
        """
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

        Args:
            context: A dictionary of contextual information (e.g., file contents).
            tools: A list of tool definitions.

        Returns:
            A formatted string to be used as the system prompt, or an empty string
            if neither context nor tools are provided.
        """
        prompt_parts = []

        if context:
            context_header = (
                "You have access to the following context from previously read files. "
                "Use this information to inform your response and actions."
            )
            context_block_parts = ["--- CONTEXT ---"]
            for key, content in context.items():
                context_block_parts.append(f"Content of file '{key}':\n```\n{content}\n```")
            context_block_parts.append("--- END CONTEXT ---")
            
            full_context_block = f"{context_header}\n\n" + "\n".join(context_block_parts)
            prompt_parts.append(full_context_block)

        if tools:
            tool_definitions = json.dumps(tools, indent=2)
            tool_prompt = (
                "You are a helpful assistant. Based on the user's prompt and the provided context, you must decide whether to call a tool or respond directly.\n\n"
                "If you choose to call a tool, you MUST respond with a single, valid JSON object with two keys: 'tool_name' and 'arguments'.\n"
                "- 'tool_name': The name of the tool to be called.\n"
                "- 'arguments': An object containing the required parameters for that tool.\n\n"
                "Your response MUST be ONLY the JSON object, with no additional text, commentary, or formatting.\n\n"
                "If you do not need to use a tool, respond with a normal text answer.\n\n"
                "Here are the available tools:\n"
                f"{tool_definitions}"
            )
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

        If context or tools are provided, it constructs a system prompt to guide the
        model. If tools are provided, it also requests a JSON response to simulate
        tool-calling.

        Args:
            prompt: The user's input prompt.
            context: An optional dictionary containing contextual information,
                     such as the content of previously read files.
            tools: An optional list of tool definitions for the model to use.

        Returns:
            A dictionary representing a tool call if the model decides to use a tool,
            the text response from the Ollama model as a string, or an error message string.
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
            payload["format"] = "json"  # Request JSON output for tool calls
            logger.debug("Tools provided. Requesting JSON format.")

        logger.debug(f"Sending payload to Ollama: {payload}")

        try:
            response = requests.post(self.api_url, json=payload, timeout=120)
            response.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)

            response_data = response.json()
            text_response = response_data.get("response", "").strip()

            if not text_response:
                logger.warning("Ollama response was empty.")
                return "Error: Received an empty response from Ollama."

            # If we requested JSON for tool-calling, attempt to parse it.
            if tools:
                try:
                    parsed_json = json.loads(text_response)
                    if isinstance(parsed_json, dict) and "tool_name" in parsed_json:
                        logger.info(f"Ollama simulated a tool call: {parsed_json.get('tool_name')}")
                        # Ensure arguments key exists, even if empty
                        if "arguments" not in parsed_json:
                            parsed_json["arguments"] = {}
                        return parsed_json
                    else:
                        # Model returned valid JSON, but not a tool call. Treat as text.
                        logger.info("Ollama returned valid JSON, but it was not a tool call. Treating as text.")
                        return text_response
                except json.JSONDecodeError:
                    # Model failed to return valid JSON despite the prompt. Fallback to text.
                    logger.warning("Ollama did not return valid JSON for a tool call. Returning as plain text.")
                    return text_response

            logger.info("Successfully received text response from Ollama.")
            return text_response

        except requests.exceptions.Timeout:
            logger.error(f"Request to Ollama timed out at {self.api_url}")
            return "Error: The request to the Ollama server timed out."
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Could not connect to Ollama server at {self.api_url}. Is it running? Error: {e}")
            return f"Error: Could not connect to Ollama server at {self.api_url}. Please ensure it is running."
        except requests.exceptions.RequestException as e:
            logger.error(f"An HTTP error occurred while communicating with Ollama: {e}", exc_info=True)
            return f"Error communicating with Ollama server: {e}"
        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON response from Ollama. Response text: {response.text}")
            return "Error: Could not decode JSON response from Ollama."
        except Exception as e:
            logger.error(f"An unexpected error occurred in OllamaProvider: {e}", exc_info=True)
            return f"An unexpected error occurred: {e}"