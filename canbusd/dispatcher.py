import logging
from typing import Any, Dict, Optional

from canbusd.event_bus import publish

logger = logging.getLogger("canbusd.dispatcher")


def _action_name(action: Optional[Dict[str, Any]]) -> Optional[str]:
    if not action:
        return None

    module_name = action.get("module")
    func_name = action.get("func")

    if not module_name or not func_name:
        return None

    return f"actions.{module_name}.{func_name}"


def dispatch(event: str, action: Optional[Dict[str, Any]], extra_args=None):
    """Publish a decoded CAN event and run its configured action, if present."""
    logger.info(
        "event=%s action=%s extra_args=%s",
        event,
        _action_name(action),
        extra_args,
    )

    publish(event, extra_args)

    if not action:
        logger.warning("No binding configured for event=%s", event)
        return

    module_name = action.get("module")
    func_name = action.get("func")
    args = list(action.get("args", []))

    if not module_name or not func_name:
        logger.error("Invalid binding for event=%s: %s", event, action)
        return

    if extra_args:
        args = args + list(extra_args)

    logger.debug("calling actions.%s.%s args=%s", module_name, func_name, args)

    try:
        mod = __import__(f"actions.{module_name}", fromlist=[func_name])
        fn = getattr(mod, func_name)
        fn(*args)
    except Exception:
        logger.exception("Action failed for event=%s action=%s", event, _action_name(action))
