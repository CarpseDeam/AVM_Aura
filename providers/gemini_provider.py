"""
Implement the LLMProvider interface for Google's Gemini models,
encapsulating all API-specific logic, including native tool-calling.
"""
import logging
from typing import Any, Dict, List, Optional, Union

import google.generativeai as genai
from .base import LLMProvider

logger = logging.getLogger(__name__)


class GeminiProvider(LLMProvider):
    """
    An LLM provider for Google's Gemini models that supports tool-calling.
    """

    def __init__(self, api_key: str, model_name: str = "gemini-pro") -> None:
        """
        Initializes the Gemini provider.

        Args:
            api_key: The Google API key.
            model_name: The specific Gemini model to use (e.g., "gemini-pro").

        Raises:
            ValueError: If the API key is not provided.
            RuntimeError: If the Gemini client fails to initialize.
        """
        if not api_key:
            raise ValueError("Google API key is required for GeminiProvider.")

        try:
            genai.configure(api_key=api_key)
            # For gemini-pro, tool calling is enabled by default.
            # For newer models like 1.5, you might specify generation_config.
            self.model = genai.GenerativeModel(model_name)
            logger.info(f"GeminiProvider initialized with model: {model_name}")
        except Exception as e:
            logger.error(f"Failed to configure Gemini or initialize model: {e}", exc_info=True)
            raise RuntimeError(f"Could not initialize GeminiProvider: {e}") from e

    def get_response(
        self,
        prompt: str,
        context: Optional[Dict[str, str]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Union[str, Dict[str, Any]]:
        """
        Sends the prompt to the Gemini API and returns the response.

        If context is provided, it is prepended to the user's prompt to provide
        working memory for the LLM. If tools are provided, it enables
        tool-calling capabilities. If the model decides to use a tool, it returns
        a structured dictionary representing the tool call. Otherwise, it returns
        a standard text response.

        Args:
            prompt: The user's input prompt.
            context: An optional dictionary containing contextual information,
                     such as the content of previously read files.
            tools: An optional list of tool definitions that the LLM can use.
                   The format should be compatible with the Google AI Python SDK.

        Returns:
            A string containing the text response from the LLM, or a dictionary
            representing a tool call in the format:
            {'tool_name': str, 'arguments': dict}.
            Returns an error message string on failure.
        """
        final_prompt = prompt
        if context:
            context_parts = ["--- CONTEXT ---"]
            for key, content in context.items():
                context_parts.append(f"Content of file '{key}':\n```\n{content}\n```")
            context_parts.append("--- END CONTEXT ---")
            context_str = "\n\n".join(context_parts)
            final_prompt = f"{context_str}\n\n{prompt}"
            logger.info(f"Injecting context for {len(context)} files into the Gemini prompt.")
        else:
            logger.debug("No context provided for Gemini prompt.")

        logger.debug(f"Sending prompt to Gemini model: '{final_prompt[:200]}...'")
        if tools:
            tool_names = [
                tool.get("function_declaration", {}).get("name", "unknown")
                for tool in tools
            ]
            logger.debug(f"Providing tools to Gemini: {tool_names}")

        try:
            response = self.model.generate_content(final_prompt, tools=tools)

            # The response object's structure varies. We must inspect it carefully.
            # Check for a function call first.
            if (
                response.candidates
                and response.candidates[0].content.parts
                and hasattr(response.candidates[0].content.parts[0], "function_call")
            ):
                tool_call = response.candidates[0].content.parts[0].function_call
                if tool_call and tool_call.name:
                    arguments = dict(tool_call.args)
                    logger.info(f"Gemini model invoked tool: '{tool_call.name}' with args: {arguments}")
                    return {
                        "tool_name": tool_call.name,
                        "arguments": arguments,
                    }

            # If no tool call, check for a text response.
            if hasattr(response, "text"):
                logger.info("Successfully received text response from Gemini.")
                return response.text

            # If no text and no tool call, it's likely a blocked response.
            if response.prompt_feedback and response.prompt_feedback.block_reason:
                reason = response.prompt_feedback.block_reason.name
                logger.warning(f"Gemini response was blocked. Reason: {reason}")
                return f"Error: Gemini response blocked due to safety filters. Reason: {reason}"

            logger.warning(f"Gemini response did not contain text or a tool call. Full response: {response}")
            return "Error: Gemini response was empty. This may be due to content filtering or other issues."

        except Exception as e:
            logger.error(f"An error occurred with the Gemini API: {e}", exc_info=True)
            return f"An error occurred with the Gemini API: {e}"