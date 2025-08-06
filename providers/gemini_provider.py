# providers/gemini_provider.py
"""
Implement the LLMProvider interface for Google's Gemini models,
encapsulating all API-specific logic, including native tool-calling.
"""
import logging
from typing import Any, Dict, List, Optional

import google.generativeai as genai
from .base import LLMProvider
from prompts import ARCHITECT_SYSTEM_PROMPT, OPERATOR_SYSTEM_PROMPT
from services.config_manager import ConfigManager

logger = logging.getLogger(__name__)


class GeminiProvider(LLMProvider):
    """
    An LLM provider for Google's Gemini models that supports tool-calling.
    """

    def __init__(self, api_key: str, config: ConfigManager) -> None:
        if not api_key:
            raise ValueError("Google API key is required for GeminiProvider.")

        try:
            genai.configure(api_key=api_key)
            self.model_name = config.get('gemini.model')
            self.plan_temperature = config.get('plan_temperature')
            self.build_temperature = config.get('build_temperature')
            logger.info(
                f"GeminiProvider initialized for model: {self.model_name} with temps (Plan: {self.plan_temperature}, Build: {self.build_temperature}).")
        except Exception as e:
            logger.error(f"Failed to configure Gemini: {e}", exc_info=True)
            raise RuntimeError(f"Could not initialize GeminiProvider: {e}") from e

    def get_response(
            self,
            prompt: str,
            mode: str,
            context: Optional[Dict[str, str]] = None,
            tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Sends the prompt to the Gemini API and returns a structured response dictionary.
        """
        system_instruction = ARCHITECT_SYSTEM_PROMPT if mode == 'plan' else OPERATOR_SYSTEM_PROMPT
        temp = self.plan_temperature if mode == 'plan' else self.build_temperature

        final_prompt = prompt
        if context:
            context_str = "\n\n".join([f"Content of file '{k}':\n```\n{v}\n```" for k, v in context.items()])
            final_prompt = f"--- CONTEXT ---\n{context_str}\n--- END CONTEXT ---\n\nUser Prompt: {prompt}"
            logger.info(f"Injecting context for {len(context)} files into the Gemini prompt.")

        logger.debug(f"Sending prompt to Gemini in '{mode}' mode (temp: {temp}): '{final_prompt[:200]}...'")

        try:
            generation_config = genai.GenerationConfig(temperature=temp)
            model = genai.GenerativeModel(self.model_name, system_instruction=system_instruction, generation_config=generation_config)
            response = model.generate_content(final_prompt, tools=tools)

            structured_response = {"text": None, "tool_calls": []}

            if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, "function_call"):
                        fc = part.function_call
                        # --- THIS IS THE FIX ---
                        # Explicitly check if the function call has a name before processing.
                        if fc.name:
                            arguments = dict(fc.args) if fc.args else {}
                            tool_call_dict = {"tool_name": fc.name, "arguments": arguments}
                            structured_response["tool_calls"].append(tool_call_dict)
                            logger.info(f"Gemini response included a tool call: {fc.name}")
                        else:
                            logger.warning("Gemini API returned a malformed tool call with no name. Discarding.")

            try:
                if hasattr(response, "text") and response.text:
                    structured_response["text"] = response.text
            except ValueError as e:
                logger.debug(f"Suppressed Gemini API ValueError - response was tool-call only: {e}")
                if not structured_response["tool_calls"]:
                    structured_response["text"] = f"Warning: Could not extract text from Gemini response. {e}"


            if response.prompt_feedback and response.prompt_feedback.block_reason:
                reason = response.prompt_feedback.block_reason.name
                structured_response["text"] = f"Error: Gemini response blocked due to safety filters. Reason: {reason}"
                logger.warning(f"Gemini response blocked. Reason: {reason}")

            return structured_response

        except Exception as e:
            logger.error(f"An error occurred with the Gemini API: {e}", exc_info=True)
            return {"text": f"An error occurred with the Gemini API: {e}", "tool_calls": []}