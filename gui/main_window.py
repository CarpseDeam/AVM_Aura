# gui/main_window.py
import logging
import queue
import threading
import os
import re
from typing import Optional, List

import customtkinter as ctk
from rich.console import Console

from event_bus import EventBus
# --- MODIFIED: Import all the new events for the approval workflow ---
from events import (
    UserPromptEntered,
    PauseExecutionForUserInput,
    PlanReadyForApproval,
    PlanApproved,
    PlanDenied,
    BlueprintInvocation
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

logger = logging.getLogger(__name__)

ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")
FONT_PATH = os.path.join(ASSETS_DIR, "fonts", "JetBrainsMono-Regular.ttf")
ICON_PATH = os.path.join(ASSETS_DIR, "Ava_icon.ico")


class AuraMainWindow(ctk.CTk):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title("Aura")
        self.geometry("1200x800")

        try:
            if os.path.exists(ICON_PATH):
                self.iconbitmap(ICON_PATH)
                logger.info(f"Successfully set window icon from {ICON_PATH}")
        except Exception as e:
            logger.warning(f"Could not set window icon from {ICON_PATH}: {e}")

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        try:
            if os.path.exists(FONT_PATH):
                ctk.FontManager.load_font(FONT_PATH)
                self.mono_font = ctk.CTkFont(family="JetBrains Mono", size=14)
                logger.info("Successfully loaded custom font: JetBrains Mono")
            else:
                logger.warning(f"Custom font not found at {FONT_PATH}. Falling back to default.")
                self.mono_font = ctk.CTkFont(family="Consolas", size=14)
        except Exception as e:
            logger.error(f"Failed to load custom font: {e}")
            self.mono_font = ctk.CTkFont(family="Consolas", size=14)

        self.ui_queue = queue.Queue()
        self.event_bus: Optional[EventBus] = None
        self.backend_ready = threading.Event()

        self.paused_question: Optional[str] = None
        # --- NEW: Attribute to hold a plan while waiting for user approval ---
        self.plan_for_approval: Optional[List[BlueprintInvocation]] = None

        self.highlighter = SyntaxHighlighter(style_name='monokai')
        self.code_block_regex = re.compile(r"```python\n(.*?)\n```", re.DOTALL)

        self._setup_widgets()
        self._start_backend_setup()
        self.after(100, self._process_queue)

    def _setup_widgets(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        main_frame = ctk.CTkFrame(self)
        main_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        main_frame.grid_columnconfigure(0, weight=1)
        # --- MODIFIED: Adjusted grid rows for the new approval frame ---
        main_frame.grid_rowconfigure(0, weight=1)  # Output text
        main_frame.grid_rowconfigure(1, weight=0)  # Approval frame
        main_frame.grid_rowconfigure(2, weight=0)  # Input frame

        # Output Text Box
        self.output_text = ctk.CTkTextbox(main_frame, wrap="word", state="disabled", font=self.mono_font)
        self.output_text.grid(row=0, column=0, sticky="nsew", pady=(0, 5))
        self.output_text.tag_config("system_message", foreground="#FFAB00")
        self.output_text.tag_config("user_prompt", foreground="#A5D6A7")
        self.output_text.tag_config("aura_question", foreground="#FFD700")
        self.output_text.tag_config("avm_executing", foreground="#81D4FA")
        self.output_text.tag_config("avm_error", foreground="#EF9A9A")
        self.output_text.tag_config("avm_output", foreground="#80CBC4")
        self.output_text.tag_config("avm_info", foreground="#B0BEC5")
        # --- NEW: A tag for displaying the plan to the user ---
        self.output_text.tag_config("plan_display", foreground="#C39BD3",
                                    font=ctk.CTkFont(family="JetBrains Mono", size=14, slant="italic"))
        self._setup_highlighting_tags()

        # --- NEW: Approval Frame ---
        self.approval_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        self.approval_frame.grid(row=1, column=0, pady=5, sticky="ew")
        self.approval_frame.grid_columnconfigure((0, 2), weight=1)
        self.approve_button = ctk.CTkButton(self.approval_frame, text="✅ Approve Plan", command=self._approve_plan)
        self.approve_button.grid(row=0, column=0, sticky="e", padx=(0, 5))
        self.deny_button = ctk.CTkButton(self.approval_frame, text="❌ Deny Plan", command=self._deny_plan,
                                         fg_color="#E57373", hover_color="#EF5350")
        self.deny_button.grid(row=0, column=2, sticky="w", padx=(5, 0))
        self.approval_frame.grid_remove()  # Hidden by default

        # Input Frame
        self.input_frame = ctk.CTkFrame(main_frame)
        self.input_frame.grid(row=2, column=0, sticky="ew")
        self.input_frame.grid_columnconfigure(0, weight=1)
        self.prompt_entry = ctk.CTkTextbox(self.input_frame, font=self.mono_font, height=100)
        self.prompt_entry.grid(row=0, column=0, columnspan=3, sticky="nsew", padx=5, pady=5)
        self.prompt_entry.bind("<Control-Return>", self._submit_prompt)
        self.shortcut_label = ctk.CTkLabel(self.input_frame, text="Ctrl+Enter to Send", font=ctk.CTkFont(size=10))
        self.shortcut_label.grid(row=1, column=0, sticky="w", padx=10, pady=5)
        self.auto_approve_switch = ctk.CTkSwitch(self.input_frame, text="Auto-Approve Plan", font=ctk.CTkFont(size=12))
        self.auto_approve_switch.grid(row=1, column=1, sticky="e", padx=10, pady=5)
        self.submit_button = ctk.CTkButton(self.input_frame, text="Send", command=self._submit_prompt, width=80)
        self.submit_button.grid(row=1, column=2, sticky="e", padx=10, pady=5)
        self.input_frame.grid_columnconfigure(1, weight=1)

        self._set_placeholder()
        self.prompt_entry.bind("<FocusIn>", self._clear_placeholder)
        self.prompt_entry.bind("<FocusOut>", self._set_placeholder)
        self.prompt_entry.focus_set()

    def _setup_highlighting_tags(self):
        """Configure CTkTextbox tags based on the highlighter's style."""
        for tag in self.highlighter.token_map.values():
            style = self.highlighter.get_style_for_tag(tag)
            if style:
                self.output_text.tag_config(tag, **style)

    def _set_placeholder(self, event=None):
        if not self.prompt_entry.get("1.0", "end-1c").strip():
            self.prompt_entry.delete("1.0", "end")
            self.prompt_entry.insert("1.0", "Enter your prompt for Aura...", ("placeholder",))
            self.prompt_entry.tag_config("placeholder", foreground="gray")

    def _clear_placeholder(self, event=None):
        if "placeholder" in self.prompt_entry.tag_names("1.0"):
            self.prompt_entry.delete("1.0", "end")

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
            vector_context_service = VectorContextService()

            provider_name = config_manager.get("llm_provider")
            temperature = config_manager.get("temperature")
            provider: Optional[LLMProvider] = None
            if provider_name == "ollama":
                model = config_manager.get("ollama.model")
                host = config_manager.get("ollama.host")
                provider = OllamaProvider(model_name=model, host=host, temperature=temperature)
            elif provider_name == "gemini":
                api_key = os.getenv("GOOGLE_API_KEY")
                if not api_key:
                    raise ValueError("GOOGLE_API_KEY environment variable not set.")
                model = config_manager.get("gemini.model")
                provider = GeminiProvider(api_key=api_key, model_name=model, temperature=temperature)
            else:
                raise ValueError(f"Unsupported LLM provider in config.yaml: '{provider_name}'")

            llm_operator = LLMOperator(
                console=console,
                provider=provider,
                event_bus=self.event_bus,
                foundry_manager=foundry_manager,
                context_manager=context_manager,
                vector_context_service=vector_context_service,
                display_callback=self._display_message,
            )
            self.event_bus.subscribe(UserPromptEntered, llm_operator.handle)
            self.event_bus.subscribe(PauseExecutionForUserInput, self._handle_pause_for_input)
            # --- NEW: Subscribe to the events for the approval workflow ---
            self.event_bus.subscribe(PlanReadyForApproval, self._handle_plan_for_approval)
            self.event_bus.subscribe(PlanDenied, self._handle_plan_denied)

            ExecutorService(
                event_bus=self.event_bus,
                context_manager=context_manager,
                foundry_manager=foundry_manager,
                vector_context_service=vector_context_service,
                display_callback=self._display_message,
            )
            logger.info("Backend services initialized successfully.")

            self._display_message(get_aura_banner(), "system_message")
            self._display_message("System: Backend ready. Please enter a prompt.", "system_message")
            self.backend_ready.set()
        except Exception as e:
            logger.error("Failed to initialize backend services: %s", e, exc_info=True)
            self._display_message(f"FATAL ERROR: Could not initialize backend: {e}", "avm_error")

    def _display_message(self, message: str, tag: str):
        self.ui_queue.put(('MESSAGE', message, tag))

    def _handle_pause_for_input(self, event: PauseExecutionForUserInput):
        logger.info(f"GUI received pause event. Question: {event.question}")
        self.ui_queue.put(('PAUSE', event.question))

    def _handle_plan_for_approval(self, event: PlanReadyForApproval):
        logger.info(f"GUI received a plan with {len(event.plan)} steps for approval.")
        self.ui_queue.put(('APPROVAL', event.plan))

    def _handle_plan_denied(self, event: PlanDenied):
        self._display_message("Plan denied by user.", "system_message")

    def _process_queue(self):
        try:
            while not self.ui_queue.empty():
                task_type, *data = self.ui_queue.get_nowait()
                self.output_text.configure(state="normal")

                if task_type == 'MESSAGE':
                    message, tag = data
                    self._insert_formatted_message(message, tag)

                elif task_type == 'PAUSE':
                    question, = data
                    self.paused_question = question
                    self.output_text.insert("end", f"🤔 Aura Asks:\n{question}\n\n", ("aura_question",))
                    self.prompt_entry.configure(state="normal")
                    self.submit_button.configure(state="normal")
                    self._set_placeholder()
                    self.prompt_entry.focus_set()

                # --- NEW: Logic to display the plan and show approval buttons ---
                elif task_type == 'APPROVAL':
                    plan, = data
                    self.plan_for_approval = plan
                    self.input_frame.grid_remove()  # Hide the normal input

                    plan_text = "Aura's Plan requires your approval:\n"
                    for i, invocation in enumerate(plan):
                        params = ", ".join(f"{k}='{v}'" for k, v in invocation.parameters.items())
                        plan_text += f"  {i + 1}. {invocation.blueprint.id}({params})\n"

                    self.output_text.insert("end", plan_text, ("plan_display",))
                    self.approval_frame.grid()  # Show the Approve/Deny buttons

                self.output_text.configure(state="disabled")
                self.output_text.see("end")
        finally:
            self.after(100, self._process_queue)

    def _insert_formatted_message(self, message, base_tag):
        """Parses message for code blocks and inserts with syntax highlighting."""
        parts = self.code_block_regex.split(message)

        for i, part in enumerate(parts):
            if not part:
                continue

            is_code = (i % 2 == 1)

            if is_code:
                self.output_text.insert("end", "\n")
                for text, tag in self.highlighter.get_tokens(part):
                    self.output_text.insert("end", text, (tag,))
                self.output_text.insert("end", "\n\n")
            else:
                self.output_text.insert("end", part, (base_tag,))

        if not self.code_block_regex.search(message):
            self.output_text.insert("end", "\n\n")

    def _submit_prompt(self, event: Optional[object] = None):
        prompt_text = self.prompt_entry.get("1.0", "end-1c").strip()
        if not prompt_text or "placeholder" in self.prompt_entry.tag_names("1.0") or not self.backend_ready.is_set():
            return

        self.prompt_entry.delete("1.0", "end")
        self.prompt_entry.configure(state="disabled")
        self.submit_button.configure(state="disabled")

        is_auto_approved = self.auto_approve_switch.get() == 1
        logger.info(f"Submitting prompt with auto_approve_plan = {is_auto_approved}")

        if self.paused_question:
            self._display_message(f"👤 You (Answer):\n{prompt_text}", "user_prompt")
            final_prompt = (
                f"I previously asked: '{self.paused_question}'. "
                f"The user has now replied: '{prompt_text}'. "
                "Please continue the task based on this new information."
            )
            self.paused_question = None
        else:
            self._display_message(f"👤 You:\n{prompt_text}", "user_prompt")
            final_prompt = prompt_text

        self._set_placeholder()
        threading.Thread(target=self._publish_prompt_event, args=(final_prompt, is_auto_approved), daemon=True).start()

    def _publish_prompt_event(self, prompt_text: str, auto_approve: bool):
        if self.event_bus:
            self.event_bus.publish(UserPromptEntered(prompt_text=prompt_text, auto_approve_plan=auto_approve))
        else:
            self._display_message("ERROR: Event bus not available.", "avm_error")

    def _cleanup_approval_ui(self):
        """Hides approval buttons and re-enables the main prompt."""
        self.approval_frame.grid_remove()
        self.input_frame.grid()
        self.plan_for_approval = None
        self.prompt_entry.focus_set()

    def _approve_plan(self):
        """Publishes the PlanApproved event when the user clicks approve."""
        if not self.plan_for_approval:
            return
        logger.info("User approved the plan.")
        self.event_bus.publish(PlanApproved(plan=self.plan_for_approval))
        self._cleanup_approval_ui()

    def _deny_plan(self):
        """Publishes the PlanDenied event and cleans up the UI."""
        if not self.plan_for_approval:
            return
        logger.info("User denied the plan.")
        self.event_bus.publish(PlanDenied())
        self._cleanup_approval_ui()