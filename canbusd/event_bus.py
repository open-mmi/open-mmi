import logging
import threading
from collections import defaultdict
from typing import Any, Callable, DefaultDict, List, Optional

logger = logging.getLogger("canbusd.event_bus")


class EventBus:
    """Small thread-safe in-process publish/subscribe bus.

    Subscribers are copied while holding the lock and invoked after the lock is
    released. One failing subscriber is logged and isolated from the others.
    """

    def __init__(self) -> None:
        self._subscribers: DefaultDict[str, List[Callable[[Any], None]]] = defaultdict(list)
        self._lock = threading.RLock()

    def subscribe(self, event: str, fn: Callable[[Any], None]) -> None:
        logger.debug("subscribe event=%s fn=%s", event, getattr(fn, "__name__", repr(fn)))
        with self._lock:
            self._subscribers[event].append(fn)

    def unsubscribe(self, event: str, fn: Callable[[Any], None]) -> bool:
        with self._lock:
            subscribers = self._subscribers.get(event)
            if not subscribers:
                return False

            try:
                subscribers.remove(fn)
            except ValueError:
                return False

            if not subscribers:
                self._subscribers.pop(event, None)
            return True

    def clear(self, event: Optional[str] = None) -> None:
        """Remove subscribers, primarily for explicit runtime/test teardown."""

        with self._lock:
            if event is None:
                self._subscribers.clear()
            else:
                self._subscribers.pop(event, None)

    def publish(self, event: str, payload: Any = None) -> int:
        with self._lock:
            subscribers = list(self._subscribers.get(event, []))

        logger.debug(
            "publish event=%s payload=%s subscribers=%d",
            event,
            payload,
            len(subscribers),
        )

        delivered = 0
        for fn in subscribers:
            try:
                fn(payload)
                delivered += 1
            except Exception:
                logger.exception(
                    "Subscriber failed for event=%s fn=%s",
                    event,
                    getattr(fn, "__name__", repr(fn)),
                )

        return delivered


_default_bus = EventBus()


def subscribe(event: str, fn: Callable[[Any], None]) -> None:
    _default_bus.subscribe(event, fn)


def unsubscribe(event: str, fn: Callable[[Any], None]) -> bool:
    return _default_bus.unsubscribe(event, fn)


def clear(event: Optional[str] = None) -> None:
    _default_bus.clear(event)


def publish(event: str, payload: Any = None) -> int:
    return _default_bus.publish(event, payload)
