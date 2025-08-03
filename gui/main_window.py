# gui/main_window.py
import logging
import threading
import os
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QTextEdit, QLineEdit, QToolBar
)
from PySide6.QtGui import QIcon, QAction
from PySide6.QtCore import Qt

from .controller import GUIController
from event_bus import EventBus

# Import all the Aura services we need to run
from services import (
    LLMOperator,
    CommandHandler,
    ExecutorService,
    ConfigManager,
    ContextManager,
    VectorContextService,
    format_as_box,
)
from foundry import FoundryManager
from providers import GeminiProvider, OllamaProvider
from events import UserPromptEntered, UserCommandEntered

logger = logging.getLogger(__name__)


class AuraMainWindow(QMainWindow):
    """
    The main Command Deck for Aura. It provides the central chat/CLI interface
    and a docking station to launch specialized viewer windows.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Aura - Command Deck")
        self.setGeometry(100, 100, 1000, 800)

        # The Event Bus is the central nervous system
        self.event_bus = EventBus()

        # --- THIS IS THE FIX: Setup the UI widgets BEFORE creating the controller ---
        self._setup_ui()

        # Now that the widgets exist, create the controller that manages them
        self.controller = GUIController(self, self.event_bus)

        # Kick off the backend services and post the welcome message
        self._start_backend_setup()

    def _setup_ui(self):
        """Builds the main user interface."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        self.output_log = QTextEdit()
        self.output_log.setReadOnly(True)
        self.output_log.setObjectName("OutputLog")
        layout.addWidget(self.output_log, 1)

        self.command_input = QLineEdit()
        self.command_input.setObjectName("CommandInput")
        self.command_input.setPlaceholderText("Enter a prompt or /command...")
        # We connect the signal here, but the controller is assigned its method later
        self.command_input.returnPressed.connect(lambda: self.controller.submit_input())
        layout.addWidget(self.command_input)

        self.dock = QToolBar("Tools")
        self.dock.setObjectName("Dock")
        self.addToolBar(Qt.ToolBarArea.RightToolBarArea, self.dock)

        # We create the actions here and connect them after the controller exists
        node_viewer_action = QAction(QIcon(), "Node Viewer", self)
        node_viewer_action.triggered.connect(lambda: self.controller.toggle_node_viewer())
        self.dock.addAction(node_viewer_action)

        code_viewer_action = QAction(QIcon(), "Code Viewer", self)
        code_viewer_action.triggered.connect(lambda: self.controller.toggle_code_viewer())
        self.dock.addAction(code_viewer_action)

    def _start_backend_setup(self):
        """Initializes all the core Aura services in a background thread."""
        self.controller.post_welcome_message()
        backend_thread = threading.Thread(target=self._setup_backend_services, daemon=True)
        backend_thread.start()

    def _setup_backend_services(self):
        """Instantiates and wires up all the non-UI services."""
        try:
            logger.info("Setting up backend services...")
            display_callback = self.controller.get_display_callback()

            config_manager = ConfigManager()
            foundry_manager = FoundryManager()
            context_manager = ContextManager()
            vector_context_service = VectorContextService()

            provider_name = config_manager.get("llm_provider")
            temperature = config_manager.get("temperature")
            provider = None  # Initialize provider to None
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
                console=None,
                provider=provider,
                event_bus=self.event_bus,
                foundry_manager=foundry_manager,
                context_manager=context_manager,
                vector_context_service=vector_context_service,
                display_callback=display_callback
            )
            command_handler = CommandHandler(
                foundry_manager=foundry_manager,
                display_callback=display_callback
            )
            ExecutorService(
                event_bus=self.event_bus,
                context_manager=context_manager,
                foundry_manager=foundry_manager,
                vector_context_service=vector_context_service,
                display_callback=display_callback
            )

            self.event_bus.subscribe(UserPromptEntered, llm_operator.handle)
            self.event_bus.subscribe(UserCommandEntered, command_handler.handle)

            logger.info("Backend services initialized and ready.")
            # Use the callback to ensure thread-safety
            display_callback("System online. All services ready.", "system_message")

        except Exception as e:
            logger.error(f"Failed to initialize backend services: {e}", exc_info=True)
            error_msg = format_as_box("FATAL ERROR", f"Could not initialize backend: {e}")
            display_callback(error_msg, "avm_error")