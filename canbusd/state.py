import threading
from typing import Callable, Dict, Any

_state: Dict[str, Any] = {}
_subs: list[Callable[[Dict[str, Any]], None]] = []
_lock = threading.Lock()

def update(key: str, value: Any):
    with _lock:
        _state[key] = value
        snapshot = dict(_state)

    for fn in _subs:
        fn(snapshot)

def get(key: str, default=None):
    with _lock:
        return _state.get(key, default)

def subscribe(fn: Callable[[Dict[str, Any]], None]):
    with _lock:
        _subs.append(fn)
