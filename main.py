# main.py
"""
AURA - Autonomous Universal Reactive Agent
Main application entry point.
"""
import sys
import logging
import asyncio
from pathlib import Path
import qasync
from PySide6.QtWidgets import QApplication

from core.application import Application

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main_async():
    """Asynchronous main function to setup and run the Aura application."""
    app = QApplication(sys.argv)
    app.setApplicationName("AURA")
    app.setOrganizationName("AURA")
    app.setStyle("Fusion")

    # This is crucial for integrating Qt with asyncio
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    project_root = Path(__file__).resolve().parent
    aura_app = Application(project_root)

    try:
        await aura_app.initialize_async()
        if aura_app.is_fully_initialized():
            logger.info("AURA initialization complete. Showing main window.")
            aura_app.show()
        else:
            logger.critical("AURA failed to initialize fully. Aborting.")
            return  # Exit if initialization failed

        with loop:
            await loop.create_future()

    except Exception as e:
        logger.critical(f"A critical error occurred during application startup: {e}", exc_info=True)
    finally:
        logger.info("Shutting down Aura application...")
        await aura_app.shutdown()


def main():
    """Main synchronous entry point."""
    logger.info("=" * 50)
    logger.info("AURA - Autonomous Universal Reactive Agent")
    logger.info("Starting up...")
    logger.info("=" * 50)

    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("Application interrupted by user.")
    finally:
        logger.info("AURA shutdown complete.")


if __name__ == "__main__":
    main()