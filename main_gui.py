# main_gui.py
"""
Create the main application window and entry point for the AVM GUI, wiring it to the backend services.

This module sets up a CustomTkinter-based graphical user interface for the AVM
for a modern look and feel. It instantiates and connects the necessary backend
services like the EventBus, LLMOperator, and ExecutorService. The GUI provides
an input for user prompts and a display area for system messages, LLM responses,
and action execution status, ensuring the backend operations do not block the
UI thread.
"""

import logging
import queue
import threading
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
from services.executor import ExecutorService
from services.llm_operator import LLMOperator

logger = logging.getLogger(__name__)


# Inherit directly from ctk.CTk for a cleaner structure
class AvmGui(ctk.CTk):
    """
    The main GUI application for the Autonomous Vision Machine (AVM).
    """

    def __init__(self) -> None:
        """
        Initializes the GUI, widgets, and backend services.
        """
        super().__init__()

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

    def _setup_widgets(self) -> None:
        """Creates and arranges the CustomTkinter widgets for the application."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        main_frame = ctk.CTkFrame(self)
        main_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(0, weight=1)

        self.output_text = ctk.CTkTextbox(
            main_frame, wrap="word", state="disabled", font=self.mono_font
        )
        self.output_text.grid(row=0, column=0, sticky="nsew", pady=(0, 5))

        # --- Configure Color Tags for Aider-Style Chat ---
        self.output_text.tag_config("system_message", foreground="#FFAB00")  # Amber
        self.output_text.tag_config("user_prompt", foreground="#A5D6A7")      # Light Green
        self.output_text.tag_config("avm_comment", foreground="#CE93D8")     # Light Purple
        self.output_text.tag_config("avm_executing", foreground="#81D4FA")   # Light Blue
        self.output_text.tag_config("avm_error", foreground="#EF9A9A")       # Light Red

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

    def _start_backend_setup(self) -> None:
        """Starts the backend initialization in a separate, non-blocking thread."""
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
            console = Console()  # For backend logging
            foundry_manager = FoundryManager()

            # --- LLM Provider Configuration ---
            provider_name = config_manager.get("llm_provider")
            provider: Optional[LLMProvider] = None
            logger.info(f"Attempting to configure LLM provider: '{provider_name}'")

            if provider_name == "ollama":
                model = config_manager.get("ollama.model", "llama3")
                base_url = config_manager.get("ollama.base_url")
                logger.info(f"Using Ollama provider with model '{model}' and base URL '{base_url}'.")
                provider = OllamaProvider(model_name=model, base_url=base_url)
            elif provider_name == "gemini":
                api_key = config_manager.get("gemini.api_key")
                if not api_key or api_key == "YOUR_GEMINI_API_KEY_HERE":
                    error_msg = "Gemini API key is missing or is a placeholder. Please update config.yaml."
                    logger.error(error_msg)
                    raise ValueError(error_msg)
                logger.info("Using Gemini provider.")
                provider = GeminiProvider(api_key=api_key)
            else:
                error_msg = f"Unsupported LLM provider specified in config.yaml: '{provider_name}'"
                logger.error(error_msg)
                raise ValueError(error_msg)

            if not provider:
                # This case should not be reached due to the checks above, but it's a good safeguard.
                error_msg = "LLM provider could not be initialized."
                logger.error(error_msg)
                raise RuntimeError(error_msg)
            # --- End LLM Provider Configuration ---

            llm_operator = LLMOperator(
                console=console,
                provider=provider,
                event_bus=self.event_bus,
                foundry_manager=foundry_manager,
                display_callback=self._display_message,
            )
            self.event_bus.subscribe(UserPromptEntered, llm_operator.handle)
            logger.info("LLMOperator subscribed to UserPromptEntered events.")

            ExecutorService(
                event_bus=self.event_bus, display_callback=self._display_message
            )

            logger.info("Backend services initialized successfully.")
            self._display_message("System: Backend ready. Please enter a prompt.", "system_message")
            self.backend_ready.set()
        except Exception as e:
            logger.error("Failed to initialize backend services: %s", e, exc_info=True)
            self._display_message(f"FATAL ERROR: Could not initialize backend: {e}", "avm_error")

    def _display_message(self, message: str, tag: str) -> None:
        """
        Thread-safely adds a tagged message to the UI queue for display.
        """
        self.ui_queue.put((message, tag))

    def _process_queue(self) -> None:
        """
        Processes messages from the UI queue and updates the text widget.
        """
        try:
            while not self.ui_queue.empty():
                message, tag = self.ui_queue.get_nowait()
                self.output_text.configure(state="normal")
                self.output_text.insert("end", message + "\n\n", (tag,))
                self.output_text.configure(state="disabled")
                self.output_text.see("end")
        finally:
            self.after(100, self._process_queue)

    def _submit_prompt(self, event: Optional[object] = None) -> None:
        """
        Handles the submission of a user prompt.
        """
        prompt_text = self.prompt_entry.get().strip()
        if not prompt_text:
            return

        if not self.backend_ready.is_set():
            self._display_message("System: Please wait, backend is not ready yet.", "system_message")
            return

        self.prompt_entry.delete(0, "end")
        self._display_message(f"👤 You:\n{prompt_text}", "user_prompt")

        threading.Thread(
            target=self._publish_prompt_event, args=(prompt_text,), daemon=True
        ).start()

    def _publish_prompt_event(self, prompt_text: str) -> None:
        """
        Creates and publishes a UserPromptEntered event.
        """
        if self.event_bus:
            event = UserPromptEntered(prompt_text=prompt_text)
            self.event_bus.publish(event)
        else:
            logger.error("Event bus not initialized, cannot publish prompt.")
            self._display_message("ERROR: Event bus not available.", "avm_error")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler("avm_gui.log"), logging.StreamHandler()],
    )
    logger.info("Starting AVM GUI application...")
    app = AvmGui()
    app.mainloop()
    logger.info("AVM GUI application closed.")