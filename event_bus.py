"""
Provide a central mechanism for decoupled communication between application components
via a publish-subscribe model.
"""
import logging
from collections import defaultdict
from typing import Callable, Type, List, Any

from events import Event

logger = logging.getLogger(__name__)

class EventBus:
    """A simple event bus for decoupled communication."""

    def __init__(self) -> None:
        """Initializes the listener registry."""
        self.listeners: defaultdict[Type[Event], List[Callable[[Event], Any]]] = defaultdict(list)

    def subscribe(self, event_type: Type[Event], handler: Callable[[Event], Any]) -> None:
        """
        Subscribe a handler to a specific event type.

        Args:
            event_type: The class of the event to listen for.
            handler: The callable function to execute when the event is published.
        """
        logger.debug(f"Subscribing handler '{handler.__name__}' to event '{event_type.__name__}'")
        self.listeners[event_type].append(handler)

    def publish(self, event: Event) -> None:
        """
        Publish an event, calling all subscribed handlers.

        Args:
            event: The event instance to publish.
        """
        event_type = type(event)
        logger.info(f"Publishing event: {event_type.__name__} with data: {event}")
        if event_type in self.listeners:
            for handler in self.listeners[event_type]:
                try:
                    logger.debug(f"Calling handler '{handler.__name__}' for event '{event_type.__name__}'")
                    handler(event)
                except Exception as e:
                    logger.error(
                        f"Error executing handler {handler.__name__} for event {event_type.__name__}: {e}",
                        exc_info=True
                    )