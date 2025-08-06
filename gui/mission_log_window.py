# gui/mission_log_window.py
import logging
import os
from typing import List, Dict, Any

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QScrollArea, QFrame
)
from PySide6.QtCore import Qt, QSize, Slot, Signal
from PySide6.QtGui import QIcon, QFont

from event_bus import EventBus
from events import MissionLogUpdated, DirectToolInvocationRequest, MissionDispatchRequest
from .task_widget import TaskWidget

logger = logging.getLogger(__name__)


class MissionLogWindow(QMainWindow):
    """
    A pop-out window to display and manage the project's Mission Log.
    """
    # Signal to safely update the UI from another thread
    update_tasks_signal = Signal(list)

    def __init__(self, event_bus: EventBus):
        super().__init__()
        self.event_bus = event_bus
        self.setWindowTitle("Aura - Mission Log")
        self.setGeometry(200, 200, 400, 600)
        self.setMinimumSize(350, 400)

        icon_path = os.path.join(os.path.dirname(__file__), '..', 'assets', 'Ava_icon.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.task_widgets: Dict[int, TaskWidget] = {}
        self._init_ui()

        # Connect the signal to the slot that updates the UI
        self.update_tasks_signal.connect(self.handle_task_update)

        # Subscribe the event handler that will emit the signal
        self.event_bus.subscribe(MissionLogUpdated, self.on_mission_log_updated)

    def on_mission_log_updated(self, event: MissionLogUpdated):
        """Event handler that receives updates from any thread."""
        # Emit the signal to pass the data to the main UI thread safely
        self.update_tasks_signal.emit(event.tasks)

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
            #AddTaskButton {
                background-color: #2a2a2a; color: #FFB74D; font-weight: bold;
                border: 1px solid #444; border-radius: 4px; padding: 8px;
            }
            #AddTaskButton:hover { background-color: #3a3a3a; border-color: #FFB74D; }
            #DispatchButton {
                background-color: #FFB74D; color: #0d0d0d; font-weight: bold;
                border-radius: 4px; padding: 10px; font-size: 15px; margin-top: 5px;
            }
            #DispatchButton:hover { background-color: #FFA726; }
            #ToggleCompletedButton {
                background-color: transparent; border: 1px solid #333; color: #888;
                text-align: left; padding: 5px; margin-top: 10px; border-radius: 3px;
            }
            #SeparatorLine { color: #333; }
        """)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: none; }")
        scroll_content_widget = QWidget()
        scroll_area.setWidget(scroll_content_widget)
        self.scroll_content_layout = QVBoxLayout(scroll_content_widget)
        self.scroll_content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.pending_tasks_layout = QVBoxLayout()
        self.pending_tasks_layout.setSpacing(5)
        self.scroll_content_layout.addLayout(self.pending_tasks_layout)
        self.scroll_content_layout.addStretch(1)

        self.separator = QFrame()
        self.separator.setFrameShape(QFrame.Shape.HLine)
        self.separator.setFrameShadow(QFrame.Shadow.Sunken)
        self.separator.setObjectName("SeparatorLine")
        self.scroll_content_layout.addWidget(self.separator)

        self.toggle_completed_button = QPushButton("Completed (0)")
        self.toggle_completed_button.setObjectName("ToggleCompletedButton")
        self.toggle_completed_button.setCheckable(True)
        self.toggle_completed_button.clicked.connect(self._on_toggle_completed)
        font = self.toggle_completed_button.font();
        font.setBold(True);
        self.toggle_completed_button.setFont(font)
        self.scroll_content_layout.addWidget(self.toggle_completed_button)

        self.completed_tasks_container = QWidget()
        self.completed_tasks_layout = QVBoxLayout(self.completed_tasks_container)
        self.completed_tasks_layout.setContentsMargins(0, 0, 0, 0)
        self.completed_tasks_layout.setSpacing(5)
        self.scroll_content_layout.addWidget(self.completed_tasks_container)

        main_layout.addWidget(scroll_area, 1)

        bottom_frame = QFrame()
        bottom_layout = QVBoxLayout(bottom_frame)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(5)
        input_layout = QHBoxLayout()
        self.add_task_input = QLineEdit()
        self.add_task_input.setPlaceholderText("Add a new task...")
        self.add_task_input.returnPressed.connect(self._on_add_task)
        input_layout.addWidget(self.add_task_input)
        add_task_button = QPushButton("Add Task")
        add_task_button.setObjectName("AddTaskButton")
        add_task_button.clicked.connect(self._on_add_task)
        input_layout.addWidget(add_task_button)
        bottom_layout.addLayout(input_layout)
        self.dispatch_button = QPushButton("Dispatch Aura")
        self.dispatch_button.setObjectName("DispatchButton")
        self.dispatch_button.clicked.connect(self._on_dispatch)
        bottom_layout.addWidget(self.dispatch_button)
        main_layout.addWidget(bottom_frame)

        self.completed_tasks_container.hide()
        self.separator.hide()
        self.toggle_completed_button.hide()

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    @Slot(list)
    def handle_task_update(self, tasks: List[Dict[str, Any]]):
        """This slot is guaranteed to run on the main UI thread."""
        self._clear_layout(self.pending_tasks_layout)
        self._clear_layout(self.completed_tasks_layout)
        self.task_widgets.clear()

        completed_tasks = [task for task in tasks if task.get('done')]
        pending_tasks = [task for task in tasks if not task.get('done')]

        for task_data in pending_tasks:
            self._create_and_add_task_widget(task_data, self.pending_tasks_layout)

        for task_data in completed_tasks:
            self._create_and_add_task_widget(task_data, self.completed_tasks_layout)

        completed_count = len(completed_tasks)
        self.toggle_completed_button.setText(f"Completed ({completed_count}) ▼")
        self.toggle_completed_button.setVisible(completed_count > 0)
        self.separator.setVisible(completed_count > 0)

    def _create_and_add_task_widget(self, task_data, layout):
        task_widget = TaskWidget(
            task_id=task_data['id'],
            description=task_data['description'],
            is_done=task_data.get('done', False)
        )
        task_widget.task_state_changed.connect(self._on_task_state_changed)
        layout.addWidget(task_widget)
        self.task_widgets[task_data['id']] = task_widget

    def _on_add_task(self):
        description = self.add_task_input.text().strip()
        if description:
            self.event_bus.publish(DirectToolInvocationRequest(
                tool_id='add_task_to_mission_log',
                params={'description': description}
            ))
            self.add_task_input.clear()

    def _on_dispatch(self):
        logger.info("Dispatch Aura button clicked. Publishing MissionDispatchRequest.")
        self.event_bus.publish(MissionDispatchRequest())

    def _on_task_state_changed(self, task_id: int, is_done: bool):
        if is_done:
            self.event_bus.publish(DirectToolInvocationRequest(
                tool_id='mark_task_as_done',
                params={'task_id': task_id}
            ))
        else:
            logger.warning(f"Task {task_id} unchecked. No action is currently configured for this.")

    def _on_toggle_completed(self, checked):
        self.completed_tasks_container.setVisible(checked)
        arrow = "▲" if checked else "▼"
        count = self.completed_tasks_layout.count()
        self.toggle_completed_button.setText(f"Completed ({count}) {arrow}")

    def show_window(self):
        if not self.isVisible():
            self.show()
        self.activateWindow()
        self.raise_()