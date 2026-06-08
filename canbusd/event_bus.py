from collections import defaultdict
from typing import Callable, Any

_subscribers = defaultdict(list)

def subscribe(event: str, fn: Callable[[Any], None]) -> None:
    _subscribers[event].append(fn)

def publish(event: str, payload: Any = None) -> None:
    for fn in _subscribers.get(event, []):
        fn(payload)