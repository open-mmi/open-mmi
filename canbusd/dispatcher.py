"""CAN event publication and bounded action execution."""

import logging
import os
import queue
import threading
from typing import Any, Dict, Optional

from canbusd.event_bus import publish

logger = logging.getLogger("canbusd.dispatcher")

DEFAULT_ACTION_QUEUE_SIZE = 64
DEFAULT_ACTION_SHUTDOWN_TIMEOUT = 6.0
_STOP = object()


def _action_name(action: Optional[Dict[str, Any]]) -> Optional[str]:
    if not action:
        return None

    module_name = action.get("module")
    func_name = action.get("func")

    if not module_name or not func_name:
        return None

    return f"actions.{module_name}.{func_name}"


def _publish_event(event: str, extra_args=None) -> None:
    """Publish an event immediately, independently of action execution."""

    logger.info(
        "event=%s action_pending=true extra_args=%s",
        event,
        extra_args,
    )
    publish(event, extra_args)


def _execute_action(event: str, action: Optional[Dict[str, Any]], extra_args=None) -> None:
    """Execute one configured action with exception isolation."""

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


def dispatch(event: str, action: Optional[Dict[str, Any]], extra_args=None):
    """Synchronously publish and execute one event.

    This compatibility function remains useful to callers and unit tests. The
    production CAN receive loop uses :class:`ActionQueue` so subprocess-backed
    actions cannot delay frame decoding.
    """

    logger.info(
        "event=%s action=%s extra_args=%s",
        event,
        _action_name(action),
        extra_args,
    )
    publish(event, extra_args)
    _execute_action(event, action, extra_args)


def _queue_size_from_env() -> int:
    try:
        value = int(os.getenv("OPEN_MMI_ACTION_QUEUE_SIZE", str(DEFAULT_ACTION_QUEUE_SIZE)))
    except (TypeError, ValueError):
        value = DEFAULT_ACTION_QUEUE_SIZE
    return max(1, min(value, 1024))


class ActionQueue:
    """Single-worker bounded queue for ordered, non-blocking actions.

    Event publication remains synchronous so observers see every decoded edge.
    Only the configured action is moved off the CAN receive thread. The queue is
    deliberately bounded: overload is logged and the newest action is dropped
    rather than allowing unbounded memory growth.
    """

    def __init__(self, maxsize: Optional[int] = None) -> None:
        self.maxsize = _queue_size_from_env() if maxsize is None else max(1, int(maxsize))
        self._queue: "queue.Queue[Any]" = queue.Queue(maxsize=self.maxsize)
        self._closed = False
        self._thread = threading.Thread(
            target=self._run,
            name="open-mmi-actions",
            daemon=True,
        )
        self._thread.start()

    def dispatch(self, event: str, action: Optional[Dict[str, Any]], extra_args=None) -> bool:
        """Publish immediately and enqueue the bound action without blocking."""

        _publish_event(event, extra_args)

        if not action:
            logger.warning("No binding configured for event=%s", event)
            return False
        if not _action_name(action):
            logger.error("Invalid binding for event=%s: %s", event, action)
            return False
        if self._closed:
            logger.error("Action queue is closed; dropping event=%s", event)
            return False

        item = (event, dict(action), list(extra_args) if extra_args else None)
        try:
            self._queue.put_nowait(item)
            return True
        except queue.Full:
            logger.error(
                "Action queue full (%d); dropping event=%s action=%s",
                self.maxsize,
                event,
                _action_name(action),
            )
            return False

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is _STOP:
                    return
                event, action, extra_args = item
                _execute_action(event, action, extra_args)
            finally:
                self._queue.task_done()

    def close(
        self,
        *,
        timeout: float = DEFAULT_ACTION_SHUTDOWN_TIMEOUT,
    ) -> None:
        """Stop the worker after queued actions, bounded by ``timeout``."""

        if self._closed:
            return
        self._closed = True
        try:
            self._queue.put(_STOP, timeout=max(0.0, float(timeout)))
        except queue.Full:
            logger.warning("Action queue did not accept shutdown marker before timeout")
            return
        self._thread.join(timeout=max(0.0, float(timeout)))
        if self._thread.is_alive():
            logger.warning("Action worker did not stop before timeout")
