"""
Implement the LLMProvider interface for local models served via Ollama,
handling all HTTP request logic.
"""
import logging
import json
import requests
from .base import LLMProvider

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """An LLM provider for local models served via the Ollama API."""

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

    def get_response(self, prompt: str, context: dict) -> str:
        """
        Sends the prompt to the Ollama /api/generate endpoint and returns the response.

        Args:
            prompt: The user's input prompt.
            context: A dictionary containing any relevant context (currently unused by Ollama).

        Returns:
            The text response from the Ollama model or an error message.
        """
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,  # We want a single, complete response
        }
        logger.debug(f"Sending payload to Ollama: {payload}")

        try:
            response = requests.post(self.api_url, json=payload, timeout=120)
            response.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)

            response_data = response.json()
            text_response = response_data.get("response", "").strip()

            if not text_response:
                logger.warning("Ollama response was empty.")
                return "Error: Received an empty response from Ollama."

            logger.info("Successfully received response from Ollama.")
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