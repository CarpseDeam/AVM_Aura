# gui/main_window.py
import logging
import threading
import os
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
    QButtonGroup, QFrame, QScrollArea
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon

from .controller import GUIController
from event_bus import EventBus
from services import (
    LLMOperator, CommandHandler, ExecutorService, ConfigManager,
    ContextManager, VectorContextService, format_as_box, ProjectManager,
    MissionLogService, PromptEngine, InstructionFactory, MissionManager
)
from foundry import FoundryManager
from providers import GeminiProvider, OllamaProvider
from events import UserPromptEntered, UserCommandEntered

logger = logging.getLogger(__name__)


class AuraMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Aura - Command Deck")
        self.setGeometry(100, 100, 1200, 800)

        icon_path = os.path.join(os.path.dirname(__file__), '..', 'assets', 'Ava_icon.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        else:
            logger.warning(f"Window icon not found at {icon_path}")

        self.event_bus = EventBus()
        # Controller is now initialized later, after the UI is built
        self.controller = None

        self._setup_ui()
        # Now we can initialize the controller
        self.controller = GUIController(self, self.event_bus, self.chat_layout, self.scroll_area)

        self.controller.register_ui_elements(self.command_input)
        self._start_backend_setup()

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Left Column: Chat and Controls ---
        left_column_widget = QWidget()
        left_column_layout = QVBoxLayout(left_column_widget)
        left_column_layout.setContentsMargins(0, 0, 0, 0)  # No margins for the column itself
        left_column_layout.setSpacing(0)

        # --- NEW: Scrollable Chat Area ---
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setObjectName("ScrollArea")
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        chat_container = QWidget()
        self.chat_layout = QVBoxLayout(chat_container)
        self.chat_layout.setContentsMargins(10, 10, 10, 10)
        self.chat_layout.setSpacing(10)
        self.chat_layout.addStretch(1)  # Pushes content to the top

        self.scroll_area.setWidget(chat_container)
        left_column_layout.addWidget(self.scroll_area)

        # --- Bottom Control Strip ---
        control_strip = QFrame()
        control_strip.setObjectName("ControlStrip")
        control_strip.setFixedHeight(100)
        # ... rest of the control strip UI is the same ...
        strip_layout = QVBoxLayout(control_strip)
        strip_layout.setContentsMargins(10, 5, 10, 10)
        strip_layout.setSpacing(5)
        mode_toggle_layout = QHBoxLayout()
        self.plan_button = QPushButton("Plan")
        self.plan_button.setObjectName("ModeButton")
        self.plan_button.setCheckable(True)
        self.plan_button.setChecked(True)
        self.build_button = QPushButton("Build")
        self.build_button.setObjectName("ModeButton")
        self.build_button.setCheckable(True)
        self.mode_toggle_group = QButtonGroup(self)
        self.mode_toggle_group.setExclusive(True)
        self.mode_toggle_group.addButton(self.plan_button)
        self.mode_toggle_group.addButton(self.build_button)
        mode_toggle_layout.addWidget(self.plan_button)
        mode_toggle_layout.addWidget(self.build_button)
        mode_toggle_layout.addStretch(1)
        strip_layout.addLayout(mode_toggle_layout)
        input_area_layout = QHBoxLayout()
        self.command_input = QTextEdit()
        self.command_input.setObjectName("CommandInput")
        self.command_input.setPlaceholderText("Describe what you want to build...")
        input_area_layout.addWidget(self.command_input)
        self.send_button = QPushButton("Send")
        self.send_button.setObjectName("SendButton")
        self.send_button.setFixedSize(QSize(80, 50))
        self.send_button.clicked.connect(lambda: self.controller.submit_input())
        input_area_layout.addWidget(self.send_button)
        strip_layout.addLayout(input_area_layout)
        left_column_layout.addWidget(control_strip)

        # --- Right Column: Tool Bar (no changes) ---
        right_column_widget = QWidget()
        right_column_widget.setObjectName("ToolBar")
        right_column_widget.setFixedWidth(160)
        right_column_layout = QVBoxLayout(right_column_widget)
        right_column_layout.setContentsMargins(10, 10, 10, 10)
        right_column_layout.setSpacing(10)
        right_column_layout.addStretch(1)
        node_viewer_btn = QPushButton("Node Viewer")
        node_viewer_btn.setObjectName("ToolButton")
        node_viewer_btn.clicked.connect(lambda: self.controller.toggle_node_viewer())
        right_column_layout.addWidget(node_viewer_btn)
        code_viewer_btn = QPushButton("Code Viewer")
        code_viewer_btn.setObjectName("ToolButton")
        code_viewer_btn.clicked.connect(lambda: self.controller.toggle_code_viewer())
        right_column_layout.addWidget(code_viewer_btn)
        mission_log_btn = QPushButton("Mission Log")
        mission_log_btn.setObjectName("ToolButton")
        mission_log_btn.clicked.connect(lambda: self.controller.toggle_mission_log())
        right_column_layout.addWidget(mission_log_btn)
        right_column_layout.addStretch(1)

        main_layout.addWidget(left_column_widget, 1)
        main_layout.addWidget(right_column_widget)

    def is_build_mode(self) -> bool:
        return self.build_button.isChecked()

    def _start_backend_setup(self):
        self.controller.post_welcome_message()
        threading.Thread(target=self._setup_backend_services, daemon=True).start()

    def _setup_backend_services(self):
        try:
            # Backend setup remains largely the same
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
            prompt_engine = PromptEngine(vector_context_service=vector_context_service, context_manager=context_manager)
            instruction_factory = InstructionFactory(foundry_manager=foundry_manager, display_callback=display_callback)
            MissionManager(event_bus=self.event_bus, mission_log_service=mission_log_service,
                           display_callback=display_callback)
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
            llm_operator = LLMOperator(provider=provider, event_bus=self.event_bus, foundry_manager=foundry_manager,
                                       prompt_engine=prompt_engine, instruction_factory=instruction_factory,
                                       display_callback=display_callback)

            # The output log is no longer passed here, as the controller manages its own widgets
            command_handler = CommandHandler(foundry_manager=foundry_manager, event_bus=self.event_bus,
                                             project_manager=project_manager, display_callback=display_callback,
                                             output_log_text_fetcher=lambda: self.controller.get_full_chat_text())

            ExecutorService(event_bus=self.event_bus, context_manager=context_manager, foundry_manager=foundry_manager,
                            vector_context_service=vector_context_service, project_manager=project_manager,
                            mission_log_service=mission_log_service, display_callback=display_callback)
            self.event_bus.subscribe(UserPromptEntered, llm_operator.handle)
            self.event_bus.subscribe(UserCommandEntered, command_handler.handle)
            logger.info("Backend services initialized and ready.")
            display_callback("System online. All services ready.", "system_message")
        except Exception as e:
            logger.error(f"Failed to initialize backend services: {e}", exc_info=True)
            error_msg = format_as_box("FATAL ERROR", f"Could not initialize backend: {e}")
            display_callback(error_msg, "avm_error")