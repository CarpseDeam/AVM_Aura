"""
Implement the LLMProvider interface for Google's Gemini models,
encapsulating all API-specific logic.
"""
import logging
import google.generativeai as genai
from .base import LLMProvider

logger = logging.getLogger(__name__)


class GeminiProvider(LLMProvider):
    """An LLM provider for Google's Gemini models."""

    def __init__(self, api_key: str, model_name: str = "gemini-pro") -> None:
        """
        Initializes the Gemini provider.

        Args:
            api_key: The Google API key.
            model_name: The specific Gemini model to use (e.g., "gemini-pro").

        Raises:
            ValueError: If the API key is not provided.
        """
        if not api_key:
            raise ValueError("Google API key is required for GeminiProvider.")
        
        try:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel(model_name)
            logger.info(f"GeminiProvider initialized with model: {model_name}")
        except Exception as e:
            logger.error(f"Failed to configure Gemini or initialize model: {e}", exc_info=True)
            raise RuntimeError(f"Could not initialize GeminiProvider: {e}") from e


    def get_response(self, prompt: str, context: dict) -> str:
        """
        Sends the prompt to the Gemini API and returns the response.

        Args:
            prompt: The user's input prompt.
            context: A dictionary containing any relevant context (currently unused).

        Returns:
            The text response from the Gemini model or an error message.
        """
        logger.debug(f"Sending prompt to Gemini model: '{prompt[:100]}...'")
        try:
            response = self.model.generate_content(prompt)
            # The response object might not have a 'text' attribute if generation fails
            # due to safety settings or other reasons.
            if hasattr(response, 'text'):
                logger.info("Successfully received response from Gemini.")
                return response.text
            else:
                # Log the full response for debugging if text is missing
                logger.warning(f"Gemini response did not contain text. Full response: {response}")
                return "Error: Gemini response did not contain any text. This may be due to safety filters."
        except Exception as e:
            logger.error(f"An error occurred with the Gemini API: {e}", exc_info=True)
            return f"An error occurred with the Gemini API: {e}"