# main.py
import sys
import logging
import os #<-- NEW: Import the 'os' module

project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)
from PySide6.QtWidgets import QApplication
from gui.main_window import AuraMainWindow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("aura_pyside.log", encoding='utf-8'),
        logging.StreamHandler()
    ],
)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("Starting Aura PySide6 GUI application...")

    app = QApplication(sys.argv)

    # Load the stylesheet
    try:
        with open("gui/style.qss", "r") as f:
            app.setStyleSheet(f.read())
        logger.info("Stylesheet 'gui/style.qss' loaded successfully.")
    except FileNotFoundError:
        logger.warning("Stylesheet 'gui/style.qss' not found. Using default styles.")

    window = AuraMainWindow()
    window.show()

    logger.info("Aura GUI is running.")
    sys.exit(app.exec())

