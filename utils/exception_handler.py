# aura/utils/exception_handler.py
import sys
import traceback
from PySide6.QtWidgets import QMessageBox


def show_exception_dialog(exc_type, exc_value, exc_tb):
    """Creates and shows a detailed error message box."""
    tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))

    msg_box = QMessageBox()
    msg_box.setIcon(QMessageBox.Icon.Critical)
    msg_box.setText("An unexpected error occurred!")
    msg_box.setInformativeText(f"Please report this issue.\n\nError: {exc_value}")
    msg_box.setDetailedText(tb_str)
    msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
    msg_box.exec()


def setup_exception_hook():
    """
    Installs a global exception hook to catch and display unhandled exceptions
    in a user-friendly dialog.
    """
    sys.excepthook = show_exception_dialog