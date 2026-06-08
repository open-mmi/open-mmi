from typing import Any, Dict, Optional
from canbusd.event_bus import publish

def dispatch(event: str, action: Optional[Dict[str, Any]], extra_args=None):
    publish(event, extra_args)

    if not action:
        return

    module_name = action.get("module")
    func_name = action.get("func")
    args = action.get("args", [])

    if extra_args:
        args = args + extra_args

    mod = __import__(f"actions.{module_name}", fromlist=[func_name])
    fn = getattr(mod, func_name)
    fn(*args)