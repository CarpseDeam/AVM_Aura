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
from typing import Optional

import customtkinter as ctk
from rich.console import Console

from event_bus import EventBus
from events import UserPromptEntered
from foundry.foundry_manager import FoundryManager
from providers.ollama_provider import OllamaProvider
from services.executor import ExecutorService
from services.llm_operator import LLMOperator

logger = logging.getLogger(__name__)


class AvmGui:
    """
    The main GUI application for the Autonomous Vision Machine (AVM).

    This class encapsulates the entire graphical user interface, including widget
    setup, backend service initialization, and the logic for communication
    between the UI and the backend services in a thread-safe manner using
    CustomTkinter for a modern UI.
    """

    def __init__(self, root: ctk.CTk) -> None:
        """
        Initializes the GUI, widgets, and backend services.

        Args:
            root: The root CustomTkinter window.
        """
        self.root = root
        self.root.title("Autonomous Vision Machine (AVM)")
        self.root.geometry("800x600")

        ctk.set_appearance_mode("System")  # Modes: "System" (default), "Dark", "Light"
        ctk.set_default_color_theme(
            "blue"
        )  # Themes: "blue" (default), "green", "dark-blue"

        self.ui_queue = queue.Queue()
        self.event_bus: Optional[EventBus] = None
        self.backend_ready = threading.Event()

        self._setup_widgets()
        self._start_backend_setup()
        self.root.after(100, self._process_queue)

    def _setup_widgets(self) -> None:
        """Creates and arranges the CustomTkinter widgets for the application."""
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        main_frame = ctk.CTkFrame(self.root)
        main_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(0, weight=1)

        self.output_text = ctk.CTkTextbox(
            main_frame, wrap="word", state="disabled", font=("Helvetica", 12)
        )
        self.output_text.grid(row=0, column=0, sticky="nsew", pady=(0, 5))

        input_frame = ctk.CTkFrame(main_frame)
        input_frame.grid(row=1, column=0, sticky="ew")
        input_frame.grid_columnconfigure(0, weight=1)

        self.prompt_entry = ctk.CTkEntry(
            input_frame, font=("Helvetica", 12), placeholder_text="Enter your prompt..."
        )
        self.prompt_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5), pady=5)
        self.prompt_entry.bind("<Return>", self._submit_prompt)

        self.submit_button = ctk.CTkButton(
            input_frame, text="Submit", command=self._submit_prompt
        )
        self.submit_button.grid(row=0, column=1, sticky="e", padx=(0, 5), pady=5)

        self.prompt_entry.focus_set()

    def _start_backend_setup(self) -> None:
        """Starts the backend initialization in a separate, non-blocking thread."""
        self._display_message("System: Initializing backend services...")
        backend_thread = threading.Thread(target=self._setup_backend, daemon=True)
        backend_thread.start()

    def _setup_backend(self) -> None:
        """
        Initializes and wires up all backend services.

        This method is run in a background thread to avoid freezing the GUI.
        It sets up the event bus, instantiates the LLM and executor services,
        and subscribes the appropriate handlers to events.
        """
        try:
            logger.info("Setting up backend services...")
            self.event_bus = EventBus()
            console = Console()
            foundry_manager = FoundryManager()
            provider = OllamaProvider()

            llm_operator = LLMOperator(
                console=console,
                provider=provider,
                event_bus=self.event_bus,
                foundry_manager=foundry_manager,
                display_callback=self._display_message,
            )
            # The LLMOperator class requires its handler to be manually subscribed.
            self.event_bus.subscribe(UserPromptEntered, llm_operator.handle)
            logger.info("LLMOperator subscribed to UserPromptEntered events.")

            # The ExecutorService subscribes to its own events upon initialization.
            ExecutorService(
                event_bus=self.event_bus, display_callback=self._display_message
            )

            logger.info("Backend services initialized successfully.")
            self._display_message("System: Backend ready. Please enter a prompt.")
            self.backend_ready.set()  # Signal that the backend is ready.
        except Exception as e:
            logger.error("Failed to initialize backend services: %s", e, exc_info=True)
            self._display_message(f"FATAL ERROR: Could not initialize backend: {e}")

    def _display_message(self, message: str) -> None:
        """
        Thread-safely adds a message to the UI queue for display.

        This method can be called from any thread.

        Args:
            message: The string message to display in the output area.
        """
        self.ui_queue.put(message)

    def _process_queue(self) -> None:
        """
        Processes messages from the UI queue and updates the text widget.

        This method is run on the main GUI thread.
        """
        try:
            while not self.ui_queue.empty():
                message = self.ui_queue.get_nowait()
                self.output_text.configure(state="normal")
                self.output_text.insert("end", message + "\n\n")
                self.output_text.configure(state="disabled")
                self.output_text.see("end")  # Auto-scroll to the bottom
        finally:
            self.root.after(100, self._process_queue)

    def _submit_prompt(self, event: Optional[object] = None) -> None:
        """
        Handles the submission of a user prompt from the entry widget.

        It retrieves text from the input field, displays it, and then publishes
        the prompt to the event bus in a background thread.

        Args:
            event: The tkinter event object (optional, used for key bindings).
        """
        prompt_text = self.prompt_entry.get().strip()
        if not prompt_text:
            return

        if not self.backend_ready.is_set():
            self._display_message("System: Please wait, backend is not ready yet.")
            return

        self.prompt_entry.delete(0, "end")
        self._display_message(f"👤 You:\n{prompt_text}")

        # Run the event publishing in a separate thread to avoid blocking the GUI
        threading.Thread(
            target=self._publish_prompt_event, args=(prompt_text,), daemon=True
        ).start()

    def _publish_prompt_event(self, prompt_text: str) -> None:
        """
        Creates and publishes a UserPromptEntered event to the event bus.

        This method is designed to be run in a background thread.

        Args:
            prompt_text: The user's prompt to publish.
        """
        if self.event_bus:
            event = UserPromptEntered(prompt_text=prompt_text)
            self.event_bus.publish(event)
        else:
            logger.error("Event bus not initialized, cannot publish prompt.")
            self._display_message("ERROR: Event bus not available.")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler("avm_gui.log"), logging.StreamHandler()],
    )
    logger.info("Starting AVM GUI application...")
    root = ctk.CTk()
    app = AvmGui(root)
    root.mainloop()
    logger.info("AVM GUI application closed.")