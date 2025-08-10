# gui/main_window.py
import logging
import os
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFrame, QScrollArea, QLabel, QSizePolicy, QPushButton
)
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QIcon, QResizeEvent, QCloseEvent

from .command_input_widget import CommandInputWidget
from .controller import GUIController
from event_bus import EventBus

logger = logging.getLogger(__name__)


class AuraMainWindow(QMainWindow):
    def __init__(self, event_bus: EventBus, project_root: Path):
        super().__init__()
        self.setWindowTitle("Aura - Command Deck")
        self.setGeometry(100, 100, 1200, 800)
        self.event_bus = event_bus

        icon_path = project_root / "assets" / "Ava_icon.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        else:
            logger.warning(f"Window icon not found at {icon_path}")

        self._setup_ui()
        self.controller = GUIController(self, self.event_bus, self.chat_layout, self.scroll_area)
        self.controller.register_ui_elements(
            command_input=self.command_input,
            autocomplete_popup=self.autocomplete_popup
        )
        self.controller.post_welcome_message()
        self._apply_stylesheet()

    def closeEvent(self, event: QCloseEvent):
        """
        Overrides the default close event to trigger a graceful shutdown.
        """
        logger.info("Main window close event triggered. Initiating application shutdown.")
        # This signal will be caught by main.py to start the full shutdown.
        self.event_bus.emit("application_shutdown")
        # We accept the event to allow the window to close. The app itself will wait.
        event.accept()

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

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setObjectName("ScrollArea")
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        chat_container = QWidget()
        self.chat_layout = QVBoxLayout(chat_container)
        self.chat_layout.setContentsMargins(10, 10, 10, 10)
        self.chat_layout.setSpacing(10)
        self.chat_layout.addStretch(1)

        self.scroll_area.setWidget(chat_container)
        left_column_layout.addWidget(self.scroll_area)

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
        left_column_layout.addWidget(self.control_strip)

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

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        if hasattr(self, 'controller') and self.controller:
            self.controller.reposition_autocomplete_popup()

    def get_controller(self) -> GUIController:
        return self.controller

    def _apply_stylesheet(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #1a1a1a;
                color: #d4d4d4;
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 14px;
            }
            #ScrollArea {
                background-color: #0d0d0d;
                border: none;
            }
            #ControlStrip {
                background-color: #1a1a1a;
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
                color: #0d0d0d;
                font-weight: bold;
                border-radius: 4px;
            }
            #SendButton:hover { background-color: #FFA726; }
            #ToolBar {
                background-color: #1c1c1c;
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