# providers/gemini_provider.py

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

    def __init__(self, api_key: str, model_name: str = "gemini-1.5-pro") -> None:
        if not api_key:
            raise ValueError("Google API key is required for GeminiProvider.")

        try:
            genai.configure(api_key=api_key)

            # --- THIS IS THE FINAL, IRON-CLAD INSTRUCTION ---
            system_instruction = (
                "You are the Operator of a deterministic virtual machine. Your ONLY function is to translate user requests into a single, valid tool call from the provided list. "
                "You MUST select one of the provided tools. Do NOT invent tools. Do NOT deviate from the provided tool schemas. "
                "Your entire response MUST be a single, valid JSON object representing the tool call, and nothing else. "
                "If the user's request cannot be fulfilled by any of the available tools, you MUST respond with a JSON object containing an error: {\"tool_name\": \"error\", \"arguments\": {\"message\": \"Request cannot be fulfilled with available tools.\"}}"
            )
            # --- END NEW INSTRUCTION ---

            self.model = genai.GenerativeModel(
                model_name,
                system_instruction=system_instruction
            )
            logger.info(f"GeminiProvider initialized with model: {model_name} and IRON-CLAD system instructions.")
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
        """
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

        logger.debug(f"Sending prompt to Gemini model: '{final_prompt[:200]}...'")

        try:
            response = self.model.generate_content(final_prompt, tools=tools)

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

            if hasattr(response, "text"):
                logger.warning("Gemini returned a text response despite strict tool-use instructions.")
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