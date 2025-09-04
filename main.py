"""
AURA - Autonomous Universal Reactive Agent
Main application entry point with improved conversation handling
"""
import sys
import logging
import asyncio
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QThread

from core.llm_client import LLMClient
from event_bus import EventBus

from core.managers import ProjectManager
from services import (
    MissionLogService,

    DevelopmentTeamService,
    CommandHandler
)
from foundry import FoundryManager
from services.agent_workflow_manager import AgentWorkflowManager

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

    def __init__(self):
        self.event_bus = EventBus()
        self.components = {}
        self.initialize_components()

    def initialize_components(self):
        """Initialize all application components in the correct order"""
        logger.info("Initializing AURA components...")

        # Core components
        self.components['llm_client'] = LLMClient()
        self.components['project_manager'] = ProjectManager(self.event_bus)
        self.components['foundry_manager'] = FoundryManager(
            self.event_bus,
            self.components['project_manager']
        )

        # Service layer
        self.components['mission_log_service'] = MissionLogService(self.event_bus)

        # Initialize workflow manager
        self.components['workflow_manager'] = AgentWorkflowManager(
            event_bus=self.event_bus,
            llm_client=self.components['llm_client'],
            mission_log_service=self.components['mission_log_service'],
            project_manager=self.components['project_manager'],
            foundry_manager=self.components['foundry_manager']
        )

        # Initialize development team service with conversation manager
        self.components['dev_team_service'] = DevelopmentTeamService(
            event_bus=self.event_bus,
            llm_client=self.components['llm_client'],
            project_manager=self.components['project_manager'],
            mission_log_service=self.components['mission_log_service'],
            workflow_manager=self.components['workflow_manager']
        )

        logger.info("All components initialized successfully")

    def create_gui(self, app):
        """Create and configure the GUI"""
        logger.info("Creating GUI...")

        # Create main window
        main_window = MainWindow(self.event_bus)

        # Initialize command handler
        def get_conversation_history():
            """Helper to get conversation history from controller"""
            if hasattr(main_window, 'command_deck_controller'):
                return main_window.command_deck_controller.get_conversation_history()
            return []

        command_handler = CommandHandler(
            foundry_manager=self.components['foundry_manager'],
            event_bus=self.event_bus,
            project_manager=self.components['project_manager'],
            conversation_history_fetcher=get_conversation_history
        )

        # Create command deck controller
        controller = CommandDeckController(
            command_deck=main_window.command_deck,
            event_bus=self.event_bus,
            command_handler=command_handler
        )

        # Store reference for history fetching
        main_window.command_deck_controller = controller

        # Show welcome message
        controller.post_welcome_message()

        return main_window

    def setup_event_handlers(self):
        """Setup global event handlers"""

        def on_critical_error(error_msg):
            logger.critical(f"Critical error: {error_msg}")
            # Could show error dialog here

        def on_status_update(agent, status, icon):
            logger.debug(f"Status update - {agent}: {status}")

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
        app = AuraApplication()
        app.run()
    finally:
        # Cleanup
        async_thread.stop()
        logger.info("AURA shutdown complete")


if __name__ == "__main__":
    main()