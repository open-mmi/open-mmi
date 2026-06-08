from typing import Any, Dict, Optional
from canbusd.event_bus import publish
from canbusd.canbusd import _call_action

def dispatch(event: str, action: Optional[Dict[str, Any]], extra_args=None) -> None:
    publish(event, extra_args)

    if action:
        _call_action(action)
