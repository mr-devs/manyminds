"""A small publish/subscribe channel between the core and whatever is watching it."""

import logging
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class JobUpdated:
    """A job's status or progress changed. The change is already saved."""

    check_id: str
    thread_id: str
    job_id: str


Listener = Callable[[JobUpdated], None]


class EventBus:
    def __init__(self) -> None:
        self._listeners: list[Listener] = []

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        """Register a listener and return a function that removes it again."""
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    def publish(self, event: JobUpdated) -> None:
        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception:
                logger.exception("An event listener failed")
