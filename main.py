"""
AURA - Autonomous Universal Reactive Agent
Main application entry point with improved conversation handling
"""
import sys
import logging
import asyncio
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThread

from event_bus import EventBus
from core.managers import ProjectManager, ServiceManager
from services import CommandHandler
from gui.main_window import AuraMainWindow

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AuraApplication:
    """
    Main application class that initializes and manages all AURA components
    """

    def __init__(self, async_thread: 'AsyncEventLoop'):
        self.async_thread = async_thread
        self.event_bus = EventBus()
        self.project_root = Path(__file__).resolve().parent
        self.service_manager = ServiceManager(self.event_bus, self.project_root)
        self.initialize_components()

    def initialize_components(self):
        """Initialize all application components in the correct order"""
        logger.info("Initializing AURA components...")

        # ProjectManager is created here and passed to the service manager
        project_manager = ProjectManager(self.event_bus, str(self.project_root))

        # ServiceManager handles the rest
        self.service_manager.initialize_core_components(
            project_root=self.project_root,
            project_manager=project_manager
        )
        self.service_manager.initialize_services()

        logger.info("All components initialized successfully")

    def create_gui(self, _app):
        """Create and configure the GUI"""
        logger.info("Creating GUI...")

        # Create main window
        main_window = AuraMainWindow(self.event_bus, self.project_root)

        # Get the controller created by the main window
        controller = main_window.get_controller()

        # Get managers and services from the ServiceManager
        project_manager = self.service_manager.get_project_manager()
        foundry_manager = self.service_manager.get_foundry_manager()
        mission_log_service = self.service_manager.mission_log_service

        # Initialize command handler
        def get_conversation_history():
            """Helper to get conversation history from controller"""
            return controller.get_conversation_history()

        command_handler = CommandHandler(
            foundry_manager=foundry_manager,
            event_bus=self.event_bus,
            project_manager=project_manager,
            conversation_history_fetcher=get_conversation_history
        )

        # Wire up the command handler to the GUI controller
        controller.wire_up_command_handler(command_handler)

        # Wire up other components to the controller
        controller.set_project_manager(project_manager)
        controller.set_mission_log_service(mission_log_service)

        # Subscribe the controller's method to show the mission log
        # This ensures the button in the GUI will work.
        self.event_bus.subscribe("show_mission_log_requested", controller.show_mission_log)

        return main_window

    def setup_event_handlers(self):
        """Setup global event handlers"""

        def on_critical_error(error_msg):
            logger.critical(f"Critical error: {error_msg}")

        def on_status_update(agent, status, icon):
            logger.debug(f"Status update - {agent}: {status} [{icon}]")

        self.event_bus.subscribe("critical_error", on_critical_error)
        self.event_bus.subscribe("agent_status_changed", on_status_update)

    def run(self):
        """Run the application"""
        try:
            # Create Qt application
            app = QApplication(sys.argv)
            app.setApplicationName("AURA")
            app.setOrganizationName("AURA")

            # Set application style
            app.setStyle("Fusion")

            # Setup event handlers
            self.setup_event_handlers()

            # Create and show GUI
            main_window = self.create_gui(app)
            main_window.show()

            # Emit event to show mission log after the main window is visible
            # to ensure it loads on startup.
            self.event_bus.emit("show_mission_log_requested")

            logger.info("Launching background services...")
            asyncio.run_coroutine_threadsafe(
                self.service_manager.launch_background_servers(),
                self.async_thread.loop
            )

            logger.info("AURA is ready!")

            # Run application
            sys.exit(app.exec())

        except Exception as e:
            logger.critical(f"Failed to start AURA: {e}", exc_info=True)
            sys.exit(1)


class AsyncEventLoop(QThread):
    """
    Runs an asyncio event loop in a separate thread for handling async operations
    """

    def __init__(self):
        super().__init__()
        self.loop = None

    def run(self):
        """Run the async event loop"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def stop(self):
        """Stop the event loop"""
        if self.loop:
            self.loop.call_soon_threadsafe(self.loop.stop)
        self.wait()


def main():
    """Main entry point"""
    logger.info("=" * 50)
    logger.info("AURA - Autonomous Universal Reactive Agent")
    logger.info("Starting up...")
    logger.info("=" * 50)

    # Start async event loop thread
    async_thread = AsyncEventLoop()
    async_thread.start()

    try:
        # Create and run application
        app = AuraApplication(async_thread)
        app.run()
    finally:
        # Cleanup
        async_thread.stop()
        logger.info("AURA shutdown complete")


if __name__ == "__main__":
    main()
