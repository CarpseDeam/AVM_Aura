# gui/mission_log_window.py
import logging
import os
from typing import List, Dict, Any

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QLineEdit, QPushButton,
    QScrollArea, QFrame
)
from PySide6.QtCore import Qt, QSize, Slot
from PySide6.QtGui import QIcon

from event_bus import EventBus
from events import MissionLogUpdated, DirectToolInvocationRequest, MissionDispatchRequest
from .task_widget import TaskWidget

logger = logging.getLogger(__name__)


class MissionLogWindow(QMainWindow):
    """
    A pop-out window to display and manage the project's Mission Log.
    """

    def __init__(self, event_bus: EventBus):
        super().__init__()
        self.event_bus = event_bus
        self.setWindowTitle("Aura - Mission Log")
        self.setGeometry(200, 200, 400, 600)
        self.setMinimumSize(350, 400)

        icon_path = os.path.join(os.path.dirname(__file__), '..', 'assets', 'Ava_icon.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self._init_ui()
        self.event_bus.subscribe(MissionLogUpdated, self.update_tasks)

    def _init_ui(self):
        """Builds the user interface."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        central_widget.setObjectName("MissionLog")
        central_widget.setStyleSheet("""
            #MissionLog { background-color: #0d0d0d; }
            QLineEdit {
                background-color: #2a2a2a;
                border: 1px solid #444444;
                border-radius: 4px;
                padding: 8px;
                color: #FFB74D;
                font-size: 14px;
            }
            #DispatchButton {
                background-color: #FFB74D;
                color: #0d0d0d;
                font-weight: bold;
                border-radius: 4px;
                padding: 10px;
                font-size: 15px;
                margin-top: 5px;
            }
            #DispatchButton:hover {
                background-color: #FFA726;
            }
        """)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: none; }")

        self.task_list_container = QWidget()
        self.task_list_layout = QVBoxLayout(self.task_list_container)
        self.task_list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.task_list_layout.setSpacing(5)
        scroll_area.setWidget(self.task_list_container)

        main_layout.addWidget(scroll_area, 1)

        # --- Input and Dispatch Controls ---
        bottom_frame = QFrame()
        bottom_layout = QVBoxLayout(bottom_frame)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(5)

        self.add_task_input = QLineEdit()
        self.add_task_input.setPlaceholderText("Add a new task...")
        self.add_task_input.returnPressed.connect(self._on_add_task)
        bottom_layout.addWidget(self.add_task_input)

        self.dispatch_button = QPushButton("Dispatch Aura")
        self.dispatch_button.setObjectName("DispatchButton")
        self.dispatch_button.clicked.connect(self._on_dispatch)
        bottom_layout.addWidget(self.dispatch_button)

        main_layout.addWidget(bottom_frame)

    @Slot(MissionLogUpdated)
    def update_tasks(self, event: MissionLogUpdated):
        """Clears and redraws the list of tasks from the event data."""
        while self.task_list_layout.count():
            item = self.task_list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        # Add new widgets for the updated task list
        for task_data in event.tasks:
            task_widget = TaskWidget(
                task_id=task_data['id'],
                description=task_data['description'],
                is_done=task_data['done']
            )
            task_widget.task_state_changed.connect(self._on_task_state_changed)
            self.task_list_layout.addWidget(task_widget)

    def _on_add_task(self):
        """Handles when the user presses Enter in the input field."""
        description = self.add_task_input.text().strip()
        if description:
            self.event_bus.publish(DirectToolInvocationRequest(
                tool_id='add_task_to_mission_log',
                params={'description': description}
            ))
            self.add_task_input.clear()

    def _on_dispatch(self):
        """Handles when the user clicks the 'Dispatch Aura' button."""
        logger.info("Dispatch Aura button clicked. Publishing MissionDispatchRequest.")
        self.event_bus.publish(MissionDispatchRequest())

    def _on_task_state_changed(self, task_id: int, is_done: bool):
        """Handles when a task's checkbox is toggled."""
        if is_done:
            self.event_bus.publish(DirectToolInvocationRequest(
                tool_id='mark_task_as_done',
                params={'task_id': task_id}
            ))
        else:
            logger.warning(f"Task {task_id} unchecked. No action is currently configured for this.")

    def show_window(self):
        """Shows the mission log window, bringing it to the front."""
        if not self.isVisible():
            self.show()
        self.activateWindow()
        self.raise_()