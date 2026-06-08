import logging
from collections import defaultdict
from typing import Any, Callable

logger = logging.getLogger("canbusd.event_bus")

_subscribers = defaultdict(list)


def subscribe(event: str, fn: Callable[[Any], None]):
    logger.debug("subscribe event=%s fn=%s", event, getattr(fn, "__name__", repr(fn)))
    _subscribers[event].append(fn)


def publish(event: str, payload: Any = None):
    subscribers = list(_subscribers.get(event, []))

    logger.debug(
        "publish event=%s payload=%s subscribers=%d",
        event,
        payload,
        len(subscribers),
    )

    for fn in subscribers:
        try:
            fn(payload)
        except Exception:
            logger.exception(
                "Subscriber failed for event=%s fn=%s",
                event,
                getattr(fn, "__name__", repr(fn)),
            )
