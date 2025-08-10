# gui/chat_widgets/tool_call_widget.py
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel
from PySide6.QtCore import Qt


class ToolCallWidget(QFrame):
    """A widget to display a dynamic ASCII art panel for tool executions."""

    def __init__(self, tool_name: str, params: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("ToolCallWidget")
        self.setFrameStyle(QFrame.Shape.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel()
        self.label.setObjectName("AsciiArtLabel")
        self.label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.label)

        self.tool_name = tool_name
        self.params = self._format_params(params)
        self.status = "[EXECUTING...]"

        self.redraw()
        self._apply_stylesheet()

    def _format_params(self, params: dict) -> dict:
        """Sanitizes and formats parameters for display."""
        formatted = {}
        param_priority = ['path', 'source_path', 'destination_path', 'command', 'dependency', 'description']

        for key in param_priority:
            if key in params:
                value = str(params[key])
                if key in ['path', 'source_path', 'destination_path']:
                    if len(value) > 25:
                        value = "..." + value[-22:]
                formatted[key.upper()] = value

        if 'content' in params and 'SIZE' not in formatted:
            formatted['SIZE'] = f"{len(params['content'])} Bytes"

        for key, value in params.items():
            if key.upper() in formatted or key == 'content':
                continue
            if len(formatted) >= 3:
                break
            formatted[key.upper()] = str(value)

        return formatted

    def redraw(self):
        """Generates and sets the ASCII art text."""
        width = 48
        title = f"[ EXECUTING TOOL: {self.tool_name} ]"

        lines = []
        top = f"┌─{title.center(width - 4, '─')}─┐"
        lines.append(top)

        param_lines = list(self.params.items())
        param_lines.append(("STATUS", self.status))

        for key, value in param_lines:
            key_str = f"  {key}....: "
            value_str = str(value)
            line_content = f"{key_str}{value_str}"
            lines.append(f"│ {line_content.ljust(width - 4)} │")

        while len(lines) < 5:
            lines.append(f"│ {' '.ljust(width - 4)} │")

        bottom = f"└{'─' * (width - 2)}┘"
        lines.append(bottom)

        full_art = "\n".join(lines)
        self.label.setText(f"<pre>{full_art}</pre>")

    def update_status(self, status: str, result: str):
        """Updates the status and redraws the widget."""
        if status.upper() == "SUCCESS":
            self.status = "[SUCCESS]"
            self.label.setStyleSheet("color: #4CAF50;")
        else:
            self.status = "[FAILURE]"
            self.label.setStyleSheet("color: #F44336;")

        if result and len(result) < 40 and '\n' not in result and 'success' not in result.lower():
            self.params["RESULT"] = result

        self.redraw()

    def _apply_stylesheet(self):
        self.setStyleSheet("""
            #ToolCallWidget {
                background-color: transparent;
                padding-left: 10px;
                padding-top: 10px;
                padding-bottom: 10px;
            }
            #AsciiArtLabel {
                color: #FFB74D; /* Amber for executing */
                font-family: "Courier New", monospace;
                font-size: 14px;
                line-height: 1.0;
            }
        """)