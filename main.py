# main.py
import logging
import sys
import os

project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from gui import AuraMainWindow


if __name__ == "__main__":

    # --- LOGGING ---
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler("aura_gui.log"), logging.StreamHandler()],
    )
    logger = logging.getLogger(__name__)
    logger.info("Starting Aura GUI application...")

    # --- APP LAUNCH ---
    app = AuraMainWindow()
    app.mainloop()

    logger.info("Aura GUI application closed.")