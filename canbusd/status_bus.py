import threading
from typing import Callable, Dict, List, Any

_subscribers: List[Callable[[Dict[str, Any]], None]] = []
_lock = threading.Lock()

_state: Dict[str, Any] = {}


def subscribe(fn: Callable[[Dict[str, Any]], None]) -> None:
    with _lock:
        _subscribers.append(fn)


def publish(update: Dict[str, Any]) -> None:
    """Merge + broadcast state updates"""
    global _state

    with _lock:
        _state.update(update)
        snapshot = dict(_state)

    for fn in _subscribers:
        fn(snapshot)
