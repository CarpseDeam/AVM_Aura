# gui/main_window.py
import logging
import threading
import os
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
    QButtonGroup
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon

from .controller import GUIController
from event_bus import EventBus
from services import (
    LLMOperator, CommandHandler, ExecutorService, ConfigManager,
    ContextManager, VectorContextService, format_as_box, ProjectManager,
    MissionLogService
)
from foundry import FoundryManager
from providers import GeminiProvider, OllamaProvider
from events import UserPromptEntered, UserCommandEntered

logger = logging.getLogger(__name__)


class AuraMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Aura - Command Deck")
        self.setGeometry(100, 100, 1100, 800)

        icon_path = os.path.join(os.path.dirname(__file__), '..', 'assets', 'Ava_icon.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        else:
            logger.warning(f"Window icon not found at {icon_path}")

        self.event_bus = EventBus()
        self.controller = GUIController(self, self.event_bus)

        self._setup_ui()
        self.controller.register_ui_elements(self.output_log, self.command_input)

        self._start_backend_setup()

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Main content area (chat, toggles, input)
        chat_widget = QWidget()
        chat_layout = QVBoxLayout(chat_widget)
        chat_layout.setContentsMargins(10, 10, 10, 10)
        chat_layout.setSpacing(5)

        self.output_log = QTextEdit()
        self.output_log.setReadOnly(True)
        self.output_log.setObjectName("OutputLog")
        chat_layout.addWidget(self.output_log, 1)

        # Mode Toggle (Plan/Build)
        mode_toggle_widget = QWidget()
        mode_toggle_widget.setObjectName("ModeToggleWidget")
        mode_toggle_layout = QHBoxLayout(mode_toggle_widget)
        mode_toggle_layout.setContentsMargins(0, 5, 0, 5) # Add vertical spacing
        mode_toggle_layout.setSpacing(5)

        self.plan_button = QPushButton("Plan")
        self.plan_button.setObjectName("ModeButton")
        self.plan_button.setCheckable(True)
        self.plan_button.setChecked(True)  # Plan is the default mode

        self.build_button = QPushButton("Build")
        self.build_button.setObjectName("ModeButton")
        self.build_button.setCheckable(True)

        self.mode_toggle_group = QButtonGroup(self)
        self.mode_toggle_group.setExclusive(True)
        self.mode_toggle_group.addButton(self.plan_button)
        self.mode_toggle_group.addButton(self.build_button)

        mode_toggle_layout.addWidget(self.plan_button)
        mode_toggle_layout.addWidget(self.build_button)
        mode_toggle_layout.addStretch(1)  # Push buttons to the left
        chat_layout.addWidget(mode_toggle_widget)

        # Input Area
        input_area_layout = QHBoxLayout()
        self.command_input = QTextEdit()
        self.command_input.setObjectName("CommandInput")
        self.command_input.setPlaceholderText("Describe what you want to do...")
        self.command_input.setFixedHeight(80)
        input_area_layout.addWidget(self.command_input, 1)

        self.send_button = QPushButton("Send")
        self.send_button.setObjectName("SendButton")
        self.send_button.setFixedSize(QSize(80, 80))
        self.send_button.clicked.connect(self.controller.submit_input)
        input_area_layout.addWidget(self.send_button)
        chat_layout.addLayout(input_area_layout)

        # Right-side "Code Book" style Tool Tab Bar
        self.tool_tab_bar = QWidget()
        self.tool_tab_bar.setObjectName("ToolTabBar")
        self.tool_tab_bar.setFixedWidth(120)
        tool_tab_bar_layout = QVBoxLayout(self.tool_tab_bar)
        tool_tab_bar_layout.setContentsMargins(0, 20, 0, 0)
        tool_tab_bar_layout.setSpacing(5)
        tool_tab_bar_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        node_viewer_tab = QPushButton("Node Viewer")
        node_viewer_tab.setObjectName("ToolTabButton")
        node_viewer_tab.clicked.connect(self.controller.toggle_node_viewer)
        tool_tab_bar_layout.addWidget(node_viewer_tab)

        code_viewer_tab = QPushButton("Code Viewer")
        code_viewer_tab.setObjectName("ToolTabButton")
        code_viewer_tab.clicked.connect(self.controller.toggle_code_viewer)
        tool_tab_bar_layout.addWidget(code_viewer_tab)

        mission_log_tab = QPushButton("Mission Log")
        mission_log_tab.setObjectName("ToolTabButton")
        mission_log_tab.clicked.connect(self.controller.toggle_mission_log)
        tool_tab_bar_layout.addWidget(mission_log_tab)

        main_layout.addWidget(chat_widget, 1)
        main_layout.addWidget(self.tool_tab_bar)

    def is_build_mode(self) -> bool:
        """Checks if the Build mode toggle is active."""
        return self.build_button.isChecked()

    def _start_backend_setup(self):
        self.controller.post_welcome_message()
        threading.Thread(target=self._setup_backend_services, daemon=True).start()

    def _setup_backend_services(self):
        try:
            logger.info("Setting up backend services...")
            display_callback = self.controller.get_display_callback()
            config_manager = ConfigManager()
            foundry_manager = FoundryManager()
            context_manager = ContextManager()
            vector_context_service = VectorContextService()
            project_manager = ProjectManager()
            mission_log_service = MissionLogService(project_manager=project_manager, event_bus=self.event_bus)

            self.controller.set_project_manager(project_manager)
            self.controller.set_mission_log_service(mission_log_service)

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

            command_handler = CommandHandler(
                foundry_manager=foundry_manager, event_bus=self.event_bus,
                project_manager=project_manager, display_callback=display_callback
            )

            ExecutorService(event_bus=self.event_bus, context_manager=context_manager,
                            foundry_manager=foundry_manager, vector_context_service=vector_context_service,
                            project_manager=project_manager, mission_log_service=mission_log_service,
                            display_callback=display_callback)

            self.event_bus.subscribe(UserPromptEntered, llm_operator.handle)
            self.event_bus.subscribe(UserCommandEntered, command_handler.handle)

            logger.info("Backend services initialized and ready.")
            display_callback("System online. All services ready.", "system_message")
        except Exception as e:
            logger.error(f"Failed to initialize backend services: {e}", exc_info=True)
            error_msg = format_as_box("FATAL ERROR", f"Could not initialize backend: {e}")
            display_callback(error_msg, "avm_error")