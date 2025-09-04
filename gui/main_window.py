# gui/main_window.py
import logging
import os
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFrame, QScrollArea, QLabel, QSizePolicy, QPushButton
)
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QIcon, QResizeEvent, QCloseEvent, QFont, QMoveEvent

from event_bus import EventBus
from .command_input_widget import CommandInputWidget
from .controller import GUIController
from .utils import get_aura_banner
from .widgets.thinking_scanner_widget import ThinkingScannerWidget
from .widgets.message_renderer_widget import MessageRendererWidget
from events import ProcessingStarted, ProcessingFinished

logger = logging.getLogger(__name__)


class AuraMainWindow(QMainWindow):
    def __init__(self, event_bus: EventBus, project_root: Path):
        super().__init__()
        self.setWindowTitle("Aura - Command Deck")
        self.setGeometry(100, 100, 950, 800)
        self.event_bus = event_bus

        icon_path = project_root / "assets" / "Ava_icon.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        else:
            logger.warning(f"Window icon not found at {icon_path}")

        self._setup_ui()
        self.controller = GUIController(self, self.event_bus, self.message_renderer)
        self.controller.register_ui_elements(
            command_input=self.command_input,
            autocomplete_popup=self.autocomplete_popup
        )
        self.controller.post_welcome_message()
        self._apply_stylesheet()
        self._setup_scanner_signals()

    def closeEvent(self, event: QCloseEvent):
        """
        Overrides the default close event to trigger a graceful shutdown.
        """
        logger.info("Main window close event triggered. Initiating application shutdown.")
        self.event_bus.emit("application_shutdown")
        event.accept()

    def _handle_geometry_change(self):
        """Handles both moving and resizing of the window."""
        if hasattr(self, 'controller') and self.controller:
            self.controller.reposition_autocomplete_popup()
        self.event_bus.emit("main_window_geometry_changed")

    def moveEvent(self, event: QMoveEvent):
        """Emits an event when the main window is moved."""
        super().moveEvent(event)
        self._handle_geometry_change()

    def resizeEvent(self, event: QResizeEvent):
        """Emits an event when the main window is resized."""
        super().resizeEvent(event)
        self._handle_geometry_change()

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        left_column_widget = QWidget()
        left_column_layout = QVBoxLayout(left_column_widget)
        left_column_layout.setContentsMargins(0, 0, 0, 0)
        left_column_layout.setSpacing(0)

        # Add persistent identity banner
        banner_text = f"<pre>{get_aura_banner()}</pre>"
        self.identity_banner = QLabel(banner_text)
        self.identity_banner.setTextFormat(Qt.TextFormat.RichText)
        self.identity_banner.setObjectName("IdentityBanner")
        self.identity_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Add with stretch factor 0 to prevent it from being collapsed
        left_column_layout.addWidget(self.identity_banner, 0)

        # Add thinking scanner widget (hidden by default)
        self.thinking_scanner = ThinkingScannerWidget()
        self.thinking_scanner.hide()
        # Add with stretch factor 0
        left_column_layout.addWidget(self.thinking_scanner, 0)

        # Add the new MessageRendererWidget
        self.message_renderer = MessageRendererWidget()
        # Add with stretch factor 1 to make it take up the remaining space
        left_column_layout.addWidget(self.message_renderer, 1)

        self.control_strip = QFrame()
        self.control_strip.setObjectName("ControlStrip")
        self.control_strip.setFixedHeight(120)
        strip_layout = QVBoxLayout(self.control_strip)
        strip_layout.setContentsMargins(10, 10, 10, 10)
        strip_layout.setSpacing(5)

        input_area_layout = QHBoxLayout()
        self.command_input = CommandInputWidget()
        self.command_input.setObjectName("CommandInput")
        self.command_input.setPlaceholderText("Describe what you want to build...")
        input_area_layout.addWidget(self.command_input)

        self.send_button = QPushButton("Send")
        self.send_button.setObjectName("SendButton")
        self.send_button.setFixedSize(QSize(80, 50))
        self.send_button.clicked.connect(lambda: self.controller.submit_input())
        self.command_input.send_message_requested.connect(lambda: self.controller.submit_input())
        input_area_layout.addWidget(self.send_button)

        strip_layout.addLayout(input_area_layout, 1)
        # Add with stretch factor 0
        left_column_layout.addWidget(self.control_strip, 0)

        right_column_widget = QWidget()
        right_column_widget.setObjectName("ToolBar")
        right_column_widget.setFixedWidth(160)
        right_column_layout = QVBoxLayout(right_column_widget)
        right_column_layout.setContentsMargins(10, 10, 10, 10)
        right_column_layout.setSpacing(10)

        project_button = QPushButton("New Project")
        project_button.setObjectName("ToolButton")
        project_button.clicked.connect(lambda: self.controller.handle_new_project_request())
        right_column_layout.addWidget(project_button)

        load_project_button = QPushButton("Load Project")
        load_project_button.setObjectName("ToolButton")
        load_project_button.clicked.connect(lambda: self.controller.handle_load_project_request())
        right_column_layout.addWidget(load_project_button)

        mission_log_btn = QPushButton("Agent TODO")
        mission_log_btn.setObjectName("ToolButton")
        mission_log_btn.clicked.connect(lambda: self.controller.toggle_mission_log())
        right_column_layout.addWidget(mission_log_btn)

        right_column_layout.addStretch(1)

        model_config_button = QPushButton("Configure Models")
        model_config_button.setObjectName("ToolButton")
        model_config_button.clicked.connect(lambda: self.event_bus.emit("configure_models_requested"))
        right_column_layout.addWidget(model_config_button)

        node_viewer_btn = QPushButton("Node Viewer")
        node_viewer_btn.setObjectName("ToolButton")
        node_viewer_btn.clicked.connect(lambda: self.controller.toggle_node_viewer())
        right_column_layout.addWidget(node_viewer_btn)

        code_viewer_btn = QPushButton("Code Viewer")
        code_viewer_btn.setObjectName("ToolButton")
        code_viewer_btn.clicked.connect(lambda: self.controller.toggle_code_viewer())
        right_column_layout.addWidget(code_viewer_btn)

        main_layout.addWidget(left_column_widget, 1)
        main_layout.addWidget(right_column_widget)

        self.autocomplete_popup = QLabel(self.command_input)
        self.autocomplete_popup.setObjectName("AutoCompletePopup")
        self.autocomplete_popup.setFrameShape(QFrame.Shape.Box)
        self.autocomplete_popup.setWordWrap(True)
        self.autocomplete_popup.hide()

    def get_controller(self) -> GUIController:
        return self.controller

    def _setup_scanner_signals(self):
        """Connect processing signals to scanner widget visibility"""
        self.event_bus.subscribe("processing_started", self._show_scanner)
        self.event_bus.subscribe("processing_finished", self._hide_scanner)

    def _show_scanner(self):
        """Show the thinking scanner when processing starts"""
        self.thinking_scanner.show()

    def _hide_scanner(self):
        """Hide the thinking scanner when processing finishes"""
        self.thinking_scanner.hide()

    def _apply_stylesheet(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #000000;
                color: #d4d4d4;
                font-family: "SF Mono", "JetBrains Mono", "Consolas", monospace;
                font-size: 15px;
                font-weight: 500;
            }
            #IdentityBanner {
                background-color: #000000;
                color: #FFB74D; /* Amber */
                font-family: "Courier New", monospace;
                font-size: 10px;
                font-weight: bold;
                line-height: 1.0;
                padding: 10px 0;
                border-bottom: 1px solid #333333;
            }
            #ScrollArea {
                background-color: #000000;
                border: none;
            }
            #ControlStrip {
                background-color: #0A0A0A;
                border-top: 1px solid #333333;
            }
            #CommandInput {
                background-color: #2a2a2a;
                border: 1px solid #444444;
                border-radius: 4px;
                padding: 5px;
                font-size: 15px;
            }
            QTextEdit::placeholderText { color: #777777; }
            #SendButton {
                background-color: #FFB74D;
                color: #000000;
                font-weight: bold;
                border-radius: 4px;
            }
            #SendButton:hover { background-color: #FFA726; }
            #ToolBar {
                background-color: #0A0A0A;
                border-left: 1px solid #333333;
            }
            #ToolButton {
                background-color: #2a2a2a;
                color: #cccccc;
                border: 1px solid #444444;
                border-radius: 8px;
                padding: 12px;
                font-weight: bold;
            }
            #ToolButton:hover {
                background-color: #3a3a3a;
                color: #FFB74D;
                border-color: #FFB74D;
            }
            #SystemMessage {
                color: #888888;
                font-style: italic;
                padding: 5px 10px;
            }
            #WelcomeBanner {
                color: #FFB74D;
                font-family: "Courier New", monospace;
                font-size: 12px;
                line-height: 1.0;
                padding-bottom: 10px;
            }
            #AutoCompletePopup {
                background-color: #2a2a2a;
                border: 1px solid #444444;
                color: #d4d4d4;
                padding: 5px;
            }
        """)