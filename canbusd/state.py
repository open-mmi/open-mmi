from typing import Any, Dict
from canbusd.event_bus import publish

_state: Dict[str, Any] = {}

def update(key: str, value: Any) -> None:
    _state[key] = value
    publish("state.changed", {"key": key, "value": value})

def get(key: str, default=None):
    return _state.get(key, default)
