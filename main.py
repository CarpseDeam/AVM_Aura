# main.py
import logging
from gui.main_window import AuraMainWindow

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler("aura_gui.log"), logging.StreamHandler()],
    )
    logger = logging.getLogger(__name__)
    logger.info("Starting Aura GUI application...")

    app = AuraMainWindow()
    app.mainloop()

    logger.info("Aura GUI application closed.")