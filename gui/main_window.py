# gui/main_window.py
import logging
import threading
import os
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton
)
from PySide6.QtCore import Qt, QSize

from .controller import GUIController
from event_bus import EventBus
from services import (
    LLMOperator, CommandHandler, ExecutorService, ConfigManager,
    ContextManager, VectorContextService, format_as_box
)
from foundry import FoundryManager
from providers import GeminiProvider, OllamaProvider
from events import UserPromptEntered, UserCommandEntered

logger = logging.getLogger(__name__)


class AuraMainWindow(QMainWindow):
    """
    The main Command Deck for Aura. It provides the central chat/CLI interface
    and a tabbed sidebar to launch specialized viewer windows.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Aura - Command Deck")
        self.setGeometry(100, 100, 1100, 800)

        self.event_bus = EventBus()
        self._setup_ui()
        self.controller = GUIController(self, self.event_bus)
        self._start_backend_setup()

    def _setup_ui(self):
        """Builds the main user interface."""
        # Main layout is horizontal: [Chat Area | Tab Bar]
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Left Side: The main Chat/CLI Interface ---
        chat_widget = QWidget()
        chat_layout = QVBoxLayout(chat_widget)
        chat_layout.setContentsMargins(10, 10, 10, 10)
        chat_layout.setSpacing(5)

        self.output_log = QTextEdit()
        self.output_log.setReadOnly(True)
        self.output_log.setObjectName("OutputLog")
        chat_layout.addWidget(self.output_log, 1)  # Stretch factor

        # --- NEW: Multi-line input area ---
        input_area_layout = QHBoxLayout()
        self.command_input = QTextEdit()
        self.command_input.setObjectName("CommandInput")
        self.command_input.setPlaceholderText("Describe the new application you want to build...")
        self.command_input.setFixedHeight(80)  # Set a fixed height for the input box
        input_area_layout.addWidget(self.command_input, 1)

        self.send_button = QPushButton("Build")
        self.send_button.setObjectName("SendButton")
        self.send_button.setFixedSize(QSize(100, 80))  # Match height of input box
        self.send_button.clicked.connect(lambda: self.controller.submit_input())
        input_area_layout.addWidget(self.send_button)

        chat_layout.addLayout(input_area_layout)

        # --- Right Side: The "Cutout" Tab Bar ---
        self.tab_bar = QWidget()
        self.tab_bar.setObjectName("SideBar")
        self.tab_bar.setFixedWidth(120)  # A slim, fixed-width bar
        tab_bar_layout = QVBoxLayout(self.tab_bar)
        tab_bar_layout.setContentsMargins(0, 20, 0, 0)  # Start tabs lower
        tab_bar_layout.setSpacing(5)
        tab_bar_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Create custom tab buttons
        node_viewer_tab = QPushButton("Node Viewer")
        node_viewer_tab.setObjectName("SideTabButton")
        node_viewer_tab.clicked.connect(lambda: self.controller.toggle_node_viewer())
        tab_bar_layout.addWidget(node_viewer_tab)

        code_viewer_tab = QPushButton("Code Viewer")
        code_viewer_tab.setObjectName("SideTabButton")
        code_viewer_tab.clicked.connect(lambda: self.controller.toggle_code_viewer())
        tab_bar_layout.addWidget(code_viewer_tab)

        # Add main widgets to the horizontal layout
        main_layout.addWidget(chat_widget, 1)
        main_layout.addWidget(self.tab_bar)

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
            provider = None
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
            llm_operator = LLMOperator(console=None, provider=provider, event_bus=self.event_bus,
                                       foundry_manager=foundry_manager, context_manager=context_manager,
                                       vector_context_service=vector_context_service, display_callback=display_callback)
            command_handler = CommandHandler(foundry_manager=foundry_manager, display_callback=display_callback)
            ExecutorService(event_bus=self.event_bus, context_manager=context_manager, foundry_manager=foundry_manager,
                            vector_context_service=vector_context_service, display_callback=display_callback)
            self.event_bus.subscribe(UserPromptEntered, llm_operator.handle)
            self.event_bus.subscribe(UserCommandEntered, command_handler.handle)
            logger.info("Backend services initialized and ready.")
            display_callback("System online. All services ready.", "system_message")
        except Exception as e:
            logger.error(f"Failed to initialize backend services: {e}", exc_info=True)
            error_msg = format_as_box("FATAL ERROR", f"Could not initialize backend: {e}")
            display_callback(error_msg, "avm_error")