# main_gui.py
import logging
import queue
import threading
import os
from typing import Optional, Tuple

import customtkinter as ctk
from rich.console import Console

from event_bus import EventBus
from events import UserPromptEntered, PauseExecutionForUserInput
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title("Aura")
        self.geometry("1200x800")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.ui_queue = queue.Queue()
        self.event_bus: Optional[EventBus] = None
        self.backend_ready = threading.Event()
        self.mono_font = ctk.CTkFont(family="Consolas", size=14)

        # New state variable to track if we're waiting for an answer
        self.paused_question: Optional[str] = None

        self._setup_widgets()
        self._start_backend_setup()
        self.after(100, self._process_queue)

    def _setup_widgets(self):
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
        self.output_text.tag_config("system_message", foreground="#FFAB00")
        self.output_text.tag_config("user_prompt", foreground="#A5D6A7")
        # New tag for Aura's questions
        self.output_text.tag_config("aura_question", foreground="#FFD700")  # A nice gold color
        self.output_text.tag_config("avm_comment", foreground="#CE93D8")
        self.output_text.tag_config("avm_executing", foreground="#81D4FA")
        self.output_text.tag_config("avm_error", foreground="#EF9A9A")
        self.output_text.tag_config("avm_response", foreground="#FFFFFF")
        self.output_text.tag_config("avm_output", foreground="#80CBC4")
        self.output_text.tag_config("avm_info", foreground="#B0BEC5")
        input_frame = ctk.CTkFrame(main_frame)
        input_frame.grid(row=1, column=0, sticky="ew")
        input_frame.grid_columnconfigure(0, weight=1)
        self.prompt_entry = ctk.CTkEntry(
            input_frame,
            font=self.mono_font,
            placeholder_text="Enter your prompt for Aura...",  # Renamed for our new project!
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
        try:
            logger.info("Setting up backend services...")
            config_manager = ConfigManager()
            self.event_bus = EventBus()
            console = Console()
            foundry_manager = FoundryManager()
            context_manager = ContextManager()
            provider_name = config_manager.get("llm_provider")
            temperature = config_manager.get("temperature")
            logger.info(f"Using temperature setting: {temperature}")
            provider: Optional[LLMProvider] = None
            logger.info(f"Configuring LLM provider from config: '{provider_name}'")
            if provider_name == "ollama":
                model = config_manager.get("ollama.model")
                host = config_manager.get("ollama.host")
                logger.info(f"Using Ollama provider with model '{model}' and host '{host}'.")
                provider = OllamaProvider(model_name=model, host=host, temperature=temperature)
            elif provider_name == "gemini":
                api_key = os.getenv("GOOGLE_API_KEY")
                if not api_key:
                    raise ValueError("GOOGLE_API_KEY environment variable not set.")
                model = config_manager.get("gemini.model")
                logger.info(f"Using Gemini provider with model '{model}'.")
                provider = GeminiProvider(api_key=api_key, model_name=model, temperature=temperature)
            else:
                raise ValueError(f"Unsupported LLM provider in config.yaml: '{provider_name}'")
            llm_operator = LLMOperator(
                console=console,
                provider=provider,
                event_bus=self.event_bus,
                foundry_manager=foundry_manager,
                context_manager=context_manager,
                display_callback=self._display_message,
            )
            self.event_bus.subscribe(UserPromptEntered, llm_operator.handle)
            # Subscribe to the new pause event
            self.event_bus.subscribe(PauseExecutionForUserInput, self._handle_pause_for_input)
            ExecutorService(
                event_bus=self.event_bus,
                context_manager=context_manager,
                foundry_manager=foundry_manager,
                display_callback=self._display_message,
            )
            logger.info("Backend services initialized successfully.")
            self._display_message("System: Backend ready. Please enter a prompt.", "system_message")
            self.backend_ready.set()
        except Exception as e:
            logger.error("Failed to initialize backend services: %s", e, exc_info=True)
            self._display_message(f"FATAL ERROR: Could not initialize backend: {e}", "avm_error")

    def _display_message(self, message: str, tag: str):
        # This now handles simple messages
        self.ui_queue.put(('MESSAGE', message, tag))

    def _handle_pause_for_input(self, event: PauseExecutionForUserInput):
        # This handles the pause event from a backend thread
        logger.info(f"GUI received pause event. Question: {event.question}")
        self.ui_queue.put(('PAUSE', event.question))

    def _process_queue(self):
        try:
            while not self.ui_queue.empty():
                task_type, *data = self.ui_queue.get_nowait()

                if task_type == 'MESSAGE':
                    message, tag = data
                    self.output_text.configure(state="normal")
                    self.output_text.insert("end", message + "\n\n", (tag,))
                    self.output_text.configure(state="disabled")

                elif task_type == 'PAUSE':
                    question, = data
                    self.paused_question = question
                    self.output_text.configure(state="normal")
                    self.output_text.insert("end", f"🤔 Aura Asks:\n{question}\n\n", ("aura_question",))
                    self.output_text.configure(state="disabled")
                    self.prompt_entry.configure(placeholder_text="Enter your answer...", state="normal")
                    self.submit_button.configure(state="normal")
                    self.prompt_entry.focus_set()

                self.output_text.see("end")
        finally:
            self.after(100, self._process_queue)

    def _submit_prompt(self, event: Optional[object] = None):
        prompt_text = self.prompt_entry.get().strip()
        if not prompt_text or not self.backend_ready.is_set():
            return

        self.prompt_entry.delete(0, "end")
        self.prompt_entry.configure(state="disabled")
        self.submit_button.configure(state="disabled")

        if self.paused_question:
            self._display_message(f"👤 You (Answer):\n{prompt_text}", "user_prompt")
            # Construct a special prompt that gives context to the LLM
            final_prompt = (
                f"I previously asked: '{self.paused_question}'. "
                f"The user has now replied: '{prompt_text}'. "
                "Please continue the task based on this new information."
            )
            self.paused_question = None
            self.prompt_entry.configure(placeholder_text="Enter your prompt for Aura...")
        else:
            self._display_message(f"👤 You:\n{prompt_text}", "user_prompt")
            final_prompt = prompt_text

        threading.Thread(target=self._publish_prompt_event, args=(final_prompt,), daemon=True).start()

    def _publish_prompt_event(self, prompt_text: str):
        if self.event_bus:
            self.event_bus.publish(UserPromptEntered(prompt_text=prompt_text))
        else:
            self._display_message("ERROR: Event bus not available.", "avm_error")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler("aura_gui.log"), logging.StreamHandler()],  # Renamed log file
    )
    logger.info("Starting Aura GUI application...")
    app = AvmGui()
    app.mainloop()
    logger.info("Aura GUI application closed.")