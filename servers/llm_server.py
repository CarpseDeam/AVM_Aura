# servers/llm_server.py
import json
import os
import logging
import asyncio
from typing import List, Dict, Any, Optional

import yaml
import uvicorn
import aiohttp
import google.generativeai as genai
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# --- Basic Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')
load_dotenv()


# --- Configuration Loading ---
def load_config():
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config.yaml')
    try:
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logging.error(f"FATAL: config.yaml not found at {config_path}")
        raise
    except Exception as e:
        logging.error(f"FATAL: Error reading config.yaml: {e}")
        raise


config = load_config()
OLLAMA_HOST = config.get('ollama', {}).get('host', 'http://localhost:11434')
# Note: The GEMINI_MODEL from config is now just a default, not the only option.
GEMINI_MODEL_DEFAULT = config.get('gemini', {}).get('model', 'gemini-1.5-pro-latest')

# --- API Key Configuration ---
GEMINI_API_KEY = os.getenv('GOOGLE_API_KEY')
if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        logging.info("Google Gemini configured successfully.")
    except Exception as e:
        logging.error(f"Failed to configure Google Gemini: {e}")
        GEMINI_API_KEY = None
else:
    logging.warning("GOOGLE_API_KEY not found in environment. Gemini models will be unavailable.")

# --- FastAPI App ---
app = FastAPI(
    title="Aura/AvAkin LLM Server",
    description="A unified API endpoint for interacting with various LLM providers."
)


# --- Pydantic Models for API Validation ---
class StreamChatRequest(BaseModel):
    provider: str
    model: str
    prompt: str
    temperature: float = 0.7
    image_b64: Optional[str] = None
    media_type: Optional[str] = "image/png"
    history: Optional[List[Dict[str, Any]]] = []


# --- Helper Functions ---
async def _get_ollama_models() -> List[str]:
    """Fetches the list of locally available Ollama models."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{OLLAMA_HOST}/api/tags") as response:
                if response.status == 200:
                    data = await response.json()
                    return [model['name'] for model in data.get('models', [])]
                else:
                    logging.warning(f"Could not fetch Ollama models, status: {response.status}")
                    return []
    except aiohttp.ClientConnectorError:
        logging.error(f"Could not connect to Ollama at {OLLAMA_HOST}. Is Ollama running?")
        return []
    except Exception as e:
        logging.error(f"An unexpected error occurred while fetching Ollama models: {e}")
        return []


# --- Streaming Generators ---
async def _stream_ollama(request: StreamChatRequest):
    """Generator for streaming responses from Ollama."""
    payload = {
        "model": request.model,
        "prompt": request.prompt,
        "stream": True,
        "options": {"temperature": request.temperature}
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{OLLAMA_HOST}/api/generate", json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    yield f"OLLAMA_ERROR: {error_text}"
                    return
                async for line in response.content:
                    if line:
                        try:
                            json_line = json.loads(line.decode('utf-8'))
                            yield json_line.get("response", "")
                        except json.JSONDecodeError:
                            continue  # Ignore non-json lines
    except Exception as e:
        yield f"OLLAMA_ERROR: {e}"


async def _stream_google(request: StreamChatRequest):
    """Generator for streaming responses from Google Gemini."""
    if not GEMINI_API_KEY:
        yield "GEMINI_ERROR: Google API Key is not configured on the server."
        return

    try:
        model = genai.GenerativeModel(request.model)
        chat_session = model.start_chat(history=request.history)

        prompt_parts = [request.prompt]
        # Vision support can be added here if needed

        response_stream = chat_session.send_message(prompt_parts, stream=True)
        for chunk in response_stream:
            yield chunk.text
    except Exception as e:
        yield f"GEMINI_ERROR: {e}"


# --- API Endpoints ---
@app.get("/get_available_models", response_model=Dict[str, List[str]])
async def get_available_models():
    """Returns a dictionary of available models, grouped by provider."""
    ollama_models = await _get_ollama_models()

    if GEMINI_API_KEY:
        google_models = [
            "gemini-2.5-pro",
            "gemini-2.5-flash"
        ]
    else:
        google_models = []

    return {
        "ollama": ollama_models,
        "google": google_models
    }


@app.post("/stream_chat")
async def stream_chat(request: StreamChatRequest):
    """The main endpoint to stream a chat response from a selected provider."""
    provider = request.provider.lower()

    if provider == "ollama":
        return StreamingResponse(_stream_ollama(request), media_type="text/plain")
    elif provider == "google":
        return StreamingResponse(_stream_google(request), media_type="text/plain")
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")


# --- Main Execution ---
if __name__ == "__main__":
    logging.info("Starting Aura LLM Server...")
    uvicorn.run(app, host="127.0.0.1", port=8002, log_level="info")

### `services/development_team_service.py`
