# main_gui.py

# (All the top imports and the AvmGui class definition are the same)
# The only change is in the _setup_backend method.
# ... (imports and AvmGui class start) ...
import logging
import queue
import threading
import os # <-- Import os to get environment variables
from typing import Optional, Tuple

import customtkinter as ctk
from rich.console import Console

from event_bus import EventBus
from events import UserPromptEntered
from foundry.foundry_manager import FoundryManager
from providers.base import LLMProvider
from providers.gemini_provider import GeminiProvider
from providers.ollama_provider import OllamaProvider
from services.config_manager import ConfigManager
from services.context_manager import ContextManager
from services.executor import ExecutorService
from services.llm_operator import LLMOperator

logger = logging.getLogger(__name__)

class AvmGui(ctk.CTk):
    # ... (the __init__, _setup_widgets, etc. methods are identical) ...
    # The only method we change is _setup_backend

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # ... (rest of __init__ is the same) ...
        self.title("AVM Cockpit")
        self.geometry("1200x800")

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.ui_queue = queue.Queue()
        self.event_bus: Optional[EventBus] = None
        self.backend_ready = threading.Event()
        self.mono_font = ctk.CTkFont(family="Consolas", size=14)

        self._setup_widgets()
        self._start_backend_setup()
        self.after(100, self._process_queue)

    def _setup_widgets(self):
        # This method is unchanged from the previous correct version
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        # ... and so on ...
        main_frame = ctk.CTkFrame(self)
        main_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(0, weight=1)
        self.output_text = ctk.CTkTextbox(
            main_frame, wrap="word", state="disabled", font=self.mono_font
        )
        self.output_text.grid(row=0, column=0, sticky="nsew", pady=(0, 5))
        self.output_text.tag_config("system_message", foreground="#FFAB00")
        self.output_text.tag_config("user_prompt", foreground="#A5D6A7")
        self.output_text.tag_config("avm_comment", foreground="#CE93D8")
        self.output_text.tag_config("avm_executing", foreground="#81D4FA")
        self.output_text.tag_config("avm_error", foreground="#EF9A9A")
        self.output_text.tag_config("avm_response", foreground="#FFFFFF") # For LLM text response
        self.output_text.tag_config("avm_output", foreground="#80CBC4") # For tool output
        self.output_text.tag_config("avm_info", foreground="#B0BEC5") # For context updates etc.

        input_frame = ctk.CTkFrame(main_frame)
        input_frame.grid(row=1, column=0, sticky="ew")
        input_frame.grid_columnconfigure(0, weight=1)
        self.prompt_entry = ctk.CTkEntry(
            input_frame,
            font=self.mono_font,
            placeholder_text="Enter your prompt for the AVM...",
        )
        self.prompt_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5), pady=5)
        self.prompt_entry.bind("<Return>", self._submit_prompt)
        self.submit_button = ctk.CTkButton(
            input_frame, text="Send", command=self._submit_prompt, width=80
        )
        self.submit_button.grid(row=0, column=1, sticky="e", padx=(0, 0), pady=5)
        self.prompt_entry.focus_set()

    def _start_backend_setup(self):
        self._display_message("System: Initializing backend services...", "system_message")
        backend_thread = threading.Thread(target=self._setup_backend, daemon=True)
        backend_thread.start()

    def _setup_backend(self) -> None:
        """
        Initializes and wires up all backend services based on config.yaml.
        """
        try:
            logger.info("Setting up backend services...")
            config_manager = ConfigManager()
            self.event_bus = EventBus()
            console = Console()
            foundry_manager = FoundryManager()
            context_manager = ContextManager() # Instantiate the new context manager

            provider_name = config_manager.get("llm_provider")
            provider: Optional[LLMProvider] = None
            logger.info(f"Configuring LLM provider from config: '{provider_name}'")

            if provider_name == "ollama":
                settings = config_manager.get("ollama", {})
                model = settings.get("model", "Qwen3-coder")
                host = settings.get("host", "http://localhost:11434")
                logger.info(f"Using Ollama provider with model '{model}' and host '{host}'.")
                provider = OllamaProvider(model_name=model, host=host)

            elif provider_name == "gemini":
                api_key = os.getenv("GOOGLE_API_KEY") # Read from environment
                if not api_key:
                    error_msg = "GOOGLE_API_KEY environment variable not set. It is required for the Gemini provider."
                    logger.critical(error_msg)
                    raise ValueError(error_msg)

                settings = config_manager.get("gemini", {})
                model = settings.get("model", "gemini-1.5-pro-latest")
                logger.info(f"Using Gemini provider with model '{model}'.")
                provider = GeminiProvider(api_key=api_key, model_name=model)

            else:
                error_msg = f"Unsupported LLM provider in config.yaml: '{provider_name}'"
                logger.critical(error_msg)
                raise ValueError(error_msg)

            # Inject ContextManager into LLMOperator
            llm_operator = LLMOperator(
                console=console,
                provider=provider,
                event_bus=self.event_bus,
                foundry_manager=foundry_manager,
                context_manager=context_manager,
                display_callback=self._display_message,
            )
            self.event_bus.subscribe(UserPromptEntered, llm_operator.handle)

            # Inject ContextManager into ExecutorService
            ExecutorService(
                event_bus=self.event_bus,
                context_manager=context_manager,
                display_callback=self._display_message,
            )

            logger.info("Backend services initialized successfully.")
            self._display_message("System: Backend ready. Please enter a prompt.", "system_message")
            self.backend_ready.set()
        except Exception as e:
            logger.error("Failed to initialize backend services: %s", e, exc_info=True)
            self._display_message(f"FATAL ERROR: Could not initialize backend: {e}", "avm_error")

    # ... (rest of the AvmGui class is the same)
    def _display_message(self, message: str, tag: str):
        self.ui_queue.put((message, tag))

    def _process_queue(self):
        try:
            while not self.ui_queue.empty():
                message, tag = self.ui_queue.get_nowait()
                self.output_text.configure(state="normal")
                self.output_text.insert("end", message + "\n\n", (tag,))
                self.output_text.configure(state="disabled")
                self.output_text.see("end")
        finally:
            self.after(100, self._process_queue)

    def _submit_prompt(self, event: Optional[object] = None):
        prompt_text = self.prompt_entry.get().strip()
        if not prompt_text: return
        if not self.backend_ready.is_set():
            self._display_message("System: Please wait...", "system_message")
            return
        self.prompt_entry.delete(0, "end")
        self._display_message(f"👤 You:\n{prompt_text}", "user_prompt")
        threading.Thread(target=self._publish_prompt_event, args=(prompt_text,), daemon=True).start()

    def _publish_prompt_event(self, prompt_text: str):
        if self.event_bus:
            self.event_bus.publish(UserPromptEntered(prompt_text=prompt_text))
        else:
            self._display_message("ERROR: Event bus not available.", "avm_error")


if __name__ == "__main__":
    # ... (main entry point is the same) ...
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler("avm_gui.log"), logging.StreamHandler()],
    )
    logger.info("Starting AVM GUI application...")
    app = AvmGui()
    app.mainloop()
    logger.info("AVM GUI application closed.")