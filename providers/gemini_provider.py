# providers/gemini_provider.py
"""
Implement the LLMProvider interface for Google's Gemini models,
encapsulating all API-specific logic, including native tool-calling.
"""
import logging
from typing import Any, Dict, List, Optional, Union

import google.generativeai as genai
from .base import LLMProvider
from prompts import ARCHITECT_SYSTEM_PROMPT, OPERATOR_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class GeminiProvider(LLMProvider):
    """
    An LLM provider for Google's Gemini models that supports tool-calling.
    """

    def __init__(self, api_key: str, model_name: str = "gemini-1.5-pro", temperature: float = 0.1) -> None:
        if not api_key:
            raise ValueError("Google API key is required for GeminiProvider.")

        try:
            genai.configure(api_key=api_key)
            self.model_name = model_name
            self.temperature = temperature
            logger.info(
                f"GeminiProvider initialized for model: {self.model_name} with temperature {self.temperature}.")
        except Exception as e:
            logger.error(f"Failed to configure Gemini: {e}", exc_info=True)
            raise RuntimeError(f"Could not initialize GeminiProvider: {e}") from e

    def get_response(
            self,
            prompt: str,
            mode: str,
            context: Optional[Dict[str, str]] = None,
            tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Union[str, Dict[str, Any]]:
        """
        Sends the prompt to the Gemini API and returns the response.
        """
        if mode == 'plan':
            system_instruction = ARCHITECT_SYSTEM_PROMPT
        elif mode == 'build':
            system_instruction = OPERATOR_SYSTEM_PROMPT
        else:
            raise ValueError(f"Unknown mode '{mode}' provided to GeminiProvider.")

        final_prompt = prompt
        if context:
            context_parts = ["--- CONTEXT ---"]
            for key, content in context.items():
                context_parts.append(f"Content of file '{key}':\n```\n{content}\n```")
            context_parts.append("--- END CONTEXT ---")
            context_str = "\n\n".join(context_parts)
            final_prompt = f"{context_str}\n\nUser Prompt: {prompt}"
            logger.info(f"Injecting context for {len(context)} files into the Gemini prompt.")
        else:
            logger.debug("No context provided for Gemini prompt.")

        logger.debug(f"Sending prompt to Gemini model in '{mode}' mode: '{final_prompt[:200]}...'")

        try:
            generation_config = genai.GenerationConfig(temperature=self.temperature)
            model = genai.GenerativeModel(
                self.model_name,
                system_instruction=system_instruction,
                generation_config=generation_config
            )

            response = model.generate_content(final_prompt, tools=tools)

            if (
                    response.candidates
                    and response.candidates[0].content.parts
                    and hasattr(response.candidates[0].content.parts[0], "function_call")
            ):
                tool_call = response.candidates[0].content.parts[0].function_call
                if tool_call and tool_call.name:
                    arguments = dict(tool_call.args)
                    logger.info(f"Gemini model invoked tool: '{tool_call.name}' with args: {arguments}")
                    if tool_call.name == 'plan':
                        return arguments

                    return {
                        "tool_name": tool_call.name,
                        "arguments": arguments,
                    }

            if hasattr(response, "text"):
                # In 'plan' mode, a text response is acceptable.
                if mode == 'plan':
                    return response.text
                logger.warning("Gemini returned a text response despite strict tool-use instructions in 'build' mode.")
                return response.text

            if response.prompt_feedback and response.prompt_feedback.block_reason:
                reason = response.prompt_feedback.block_reason.name
                logger.warning(f"Gemini response was blocked. Reason: {reason}")
                return f"Error: Gemini response blocked due to safety filters. Reason: {reason}"

            logger.warning(f"Gemini response did not contain text or a tool call. Full response: {response}")
            return "Error: Gemini response was empty."

        except Exception as e:
            logger.error(f"An error occurred with the Gemini API: {e}", exc_info=True)
            return f"An error occurred with the Gemini API: {e}"