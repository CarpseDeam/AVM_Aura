from event_bus import EventBus
from core.app_state import AppState
from core.interaction_mode import InteractionMode


class AppStateService:
    """
    A centralized service to manage the application's global state.
    """
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self._app_state: AppState = AppState.BOOTSTRAP
        self._interaction_mode: InteractionMode = InteractionMode.BUILD
        print("[AppStateService] Initialized.")

    def get_app_state(self) -> AppState:
        return self._app_state

    def get_interaction_mode(self) -> InteractionMode:
        return self._interaction_mode

    def set_app_state(self, new_state: AppState, project_name: str | None = None):
        if self._app_state != new_state:
            self._app_state = new_state
            self.log("info", f"Application state changed to: {new_state.name}")
            self.event_bus.emit("app_state_changed", new_state, project_name)

    def set_interaction_mode(self, new_mode: InteractionMode):
        if self._interaction_mode != new_mode:
            self._interaction_mode = new_mode
            self.log("info", f"Interaction mode changed to: {new_mode.name}")
            self.event_bus.emit("interaction_mode_changed", new_mode)

    def log(self, level: str, message: str):
        self.event_bus.emit("log_message_received", "AppStateService", level, message)