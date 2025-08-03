# gui/main_window.py
import logging
import threading
import os
import re
from typing import Optional

import customtkinter as ctk
from rich.console import Console

from event_bus import EventBus
from events import (
    UserPromptEntered,
    PauseExecutionForUserInput,
    PlanReadyForApproval,
    PlanDenied
)
from foundry import FoundryManager
from providers import LLMProvider, GeminiProvider, OllamaProvider
from services import (
    ConfigManager,
    ContextManager,
    ExecutorService,
    LLMOperator,
    VectorContextService
)
from .syntax_highlighter import SyntaxHighlighter
from .utils import get_aura_banner
from .controller import GUIController

logger = logging.getLogger(__name__)

ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")
FONT_PATH = os.path.join(ASSETS_DIR, "fonts", "JetBrainsMono-Regular.ttf")
ICON_PATH = os.path.join(ASSETS_DIR, "Ava_icon.ico")


class AuraMainWindow(ctk.CTk):
    """
    The main GUI window for Aura. This class is responsible for creating and
    arranging all widgets. All application logic and event handling is
    delegated to the GUIController.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title("Aura")
        self.geometry("1200x800")

        try:
            if os.path.exists(ICON_PATH): self.iconbitmap(ICON_PATH)
        except Exception as e:
            logger.warning(f"Could not set window icon: {e}")

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        try:
            if os.path.exists(FONT_PATH):
                ctk.FontManager.load_font(FONT_PATH)
                self.mono_font = ctk.CTkFont(family="JetBrains Mono", size=14)
            else:
                self.mono_font = ctk.CTkFont(family="Consolas", size=14)
        except Exception as e:
            self.mono_font = ctk.CTkFont(family="Consolas", size=14)

        self.backend_ready = threading.Event()
        self.highlighter = SyntaxHighlighter(style_name='monokai')
        self.code_block_regex = re.compile(r"```python\n(.*?)\n```", re.DOTALL)

        self.event_bus = EventBus()
        # --- THIS IS THE FIX: Widgets MUST be created before the controller ---
        self._setup_widgets()
        self.controller = GUIController(self, self.event_bus)

        self._start_backend_setup()
        self.controller.start_ui_loop()

    def _setup_widgets(self):
        """Creates and arranges all the widgets in the window."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        main_frame = ctk.CTkFrame(self)
        main_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(0, weight=1)
        main_frame.grid_rowconfigure(1, weight=0)
        main_frame.grid_rowconfigure(2, weight=0)

        self.output_text = ctk.CTkTextbox(main_frame, wrap="word", state="disabled", font=self.mono_font)
        self.output_text.grid(row=0, column=0, sticky="nsew", pady=(0, 5))
        self.output_text.tag_config("system_message", foreground="#FFAB00")
        self.output_text.tag_config("user_prompt", foreground="#A5D6A7")
        self.output_text.tag_config("aura_question", foreground="#FFD700")
        self.output_text.tag_config("avm_executing", foreground="#81D4FA")
        self.output_text.tag_config("avm_error", foreground="#EF9A9A")
        self.output_text.tag_config("avm_output", foreground="#80CBC4")
        self.output_text.tag_config("avm_info", foreground="#B0BEC5")
        self.output_text.tag_config("plan_display", foreground="#C39BD3", underline=True)
        self._setup_highlighting_tags()

        self.approval_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        self.approval_frame.grid(row=1, column=0, pady=5, sticky="ew")
        self.approval_frame.grid_columnconfigure((0, 2), weight=1)
        # Note: We can't assign controller methods here directly if controller doesn't exist yet.
        # So we create the widgets and assign commands later or use lambdas.
        # The current fixed __init__ order makes direct assignment safe.
        self.approve_button = ctk.CTkButton(self.approval_frame, text="✅ Approve Plan")
        self.approve_button.grid(row=0, column=0, sticky="e", padx=(0, 5))
        self.deny_button = ctk.CTkButton(self.approval_frame, text="❌ Deny Plan", fg_color="#E57373",
                                         hover_color="#EF5350")
        self.deny_button.grid(row=0, column=2, sticky="w", padx=(5, 0))
        self.approval_frame.grid_remove()

        self.input_frame = ctk.CTkFrame(main_frame)
        self.input_frame.grid(row=2, column=0, sticky="ew")
        self.input_frame.grid_columnconfigure(0, weight=1)
        self.prompt_entry = ctk.CTkTextbox(self.input_frame, font=self.mono_font, height=100)
        self.prompt_entry.grid(row=0, column=0, columnspan=3, sticky="nsew", padx=5, pady=5)

        self.shortcut_label = ctk.CTkLabel(self.input_frame, text="Ctrl+Enter to Send", font=ctk.CTkFont(size=10))
        self.shortcut_label.grid(row=1, column=0, sticky="w", padx=10, pady=5)
        self.auto_approve_switch = ctk.CTkSwitch(self.input_frame, text="Auto-Approve Plan", font=ctk.CTkFont(size=12))
        self.auto_approve_switch.grid(row=1, column=1, sticky="e", padx=10, pady=5)
        self.submit_button = ctk.CTkButton(self.input_frame, text="Send", width=80)
        self.submit_button.grid(row=1, column=2, sticky="e", padx=10, pady=5)
        self.input_frame.grid_columnconfigure(1, weight=1)

        self._set_placeholder()
        self.prompt_entry.bind("<FocusIn>", self._clear_placeholder)
        self.prompt_entry.bind("<FocusOut>", self._set_placeholder)
        self.prompt_entry.focus_set()

    def _setup_widget_commands(self):
        """Assigns commands to widgets that require the controller."""
        self.approve_button.configure(command=self.controller.approve_plan)
        self.deny_button.configure(command=self.controller.deny_plan)
        self.submit_button.configure(command=self.controller.submit_prompt)
        self.prompt_entry.bind("<Control-Return>", self.controller.submit_prompt)

    def _setup_highlighting_tags(self):
        for tag in self.highlighter.token_map.values():
            style = self.highlighter.get_style_for_tag(tag)
            if style: self.output_text.tag_config(tag, **style)

    def _set_placeholder(self, event=None):
        if not self.prompt_entry.get("1.0", "end-1c").strip():
            self.prompt_entry.delete("1.0", "end")
            self.prompt_entry.insert("1.0", "Enter your prompt for Aura...", ("placeholder",))
            self.prompt_entry.tag_config("placeholder", foreground="gray")

    def _clear_placeholder(self, event=None):
        if "placeholder" in self.prompt_entry.tag_names("1.0"):
            self.prompt_entry.delete("1.0", "end")

    def _start_backend_setup(self):
        # We need to assign commands after the controller is created.
        self._setup_widget_commands()
        self.controller.display_message("System: Initializing backend services...", "system_message")
        backend_thread = threading.Thread(target=self._setup_backend, daemon=True)
        backend_thread.start()

    def _setup_backend(self) -> None:
        try:
            logger.info("Setting up backend services...")
            config_manager = ConfigManager()
            console = Console()
            foundry_manager = FoundryManager()
            context_manager = ContextManager()
            vector_context_service = VectorContextService()
            provider_name = config_manager.get("llm_provider")
            temperature = config_manager.get("temperature")
            provider: Optional[LLMProvider] = None
            if provider_name == "ollama":
                model, host = config_manager.get("ollama.model"), config_manager.get("ollama.host")
                provider = OllamaProvider(model_name=model, host=host, temperature=temperature)
            elif provider_name == "gemini":
                api_key = os.getenv("GOOGLE_API_KEY")
                if not api_key: raise ValueError("GOOGLE_API_KEY environment variable not set.")
                model = config_manager.get("gemini.model")
                provider = GeminiProvider(api_key=api_key, model_name=model, temperature=temperature)
            else:
                raise ValueError(f"Unsupported LLM provider: '{provider_name}'")

            llm_operator = LLMOperator(
                console, provider, self.event_bus, foundry_manager,
                context_manager, vector_context_service, self.controller.display_message,
            )
            ExecutorService(
                self.event_bus, context_manager, foundry_manager,
                vector_context_service, self.controller.display_message,
            )

            self.event_bus.subscribe(UserPromptEntered, llm_operator.handle)
            self.event_bus.subscribe(PauseExecutionForUserInput, self.controller.handle_pause_for_input)
            self.event_bus.subscribe(PlanReadyForApproval, self.controller.handle_plan_for_approval)
            self.event_bus.subscribe(PlanDenied, self.controller.handle_plan_denied)

            logger.info("Backend services initialized successfully.")
            self.controller.display_message(get_aura_banner(), "system_message")
            self.controller.display_message("System: Backend ready. Please enter a prompt.", "system_message")
            self.backend_ready.set()
        except Exception as e:
            logger.error("Failed to initialize backend services: %s", e, exc_info=True)
            self.controller.display_message(f"FATAL ERROR: Could not initialize backend: {e}", "avm_error")