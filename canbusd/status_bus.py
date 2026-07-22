import copy
import json
import logging
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("canbusd.status_bus")


def _default_status_path() -> Path:
    runtime_dir = os.getenv("XDG_RUNTIME_DIR")
    if runtime_dir:
        return Path(runtime_dir) / "open-mmi" / "status.json"

    return Path("/tmp/open-mmi-status.json")


STATUS_PATH = Path(os.getenv("OPEN_MMI_STATUS_PATH", str(_default_status_path())))


def _deep_merge(dst: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in src.items():
        if isinstance(value, dict) and isinstance(dst.get(key), dict):
            _deep_merge(dst[key], value)
        else:
            dst[key] = copy.deepcopy(value)
    return dst


class StatusBus:
    """Thread-safe decoded-state publisher with an atomic JSON snapshot.

    Publication is serialised so concurrent updates cannot write snapshots out
    of order. Persistence and subscriber failures are logged and isolated from
    the CAN receive loop; the in-memory state remains available to later
    publishers and subscribers.
    """

    def __init__(
        self,
        path: Path,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.path = Path(path)
        self._clock = clock
        self._subscribers: List[Callable[[Dict[str, Any]], None]] = []
        self._state: Dict[str, Any] = {}
        self._runtime: Optional[Dict[str, Any]] = None
        self._lock = threading.RLock()
        self._publish_lock = threading.Lock()

    def subscribe(self, fn: Callable[[Dict[str, Any]], None]) -> None:
        with self._lock:
            self._subscribers.append(fn)

    def unsubscribe(self, fn: Callable[[Dict[str, Any]], None]) -> bool:
        with self._lock:
            try:
                self._subscribers.remove(fn)
            except ValueError:
                return False
            return True

    def reset(self, persist: bool = False, notify: bool = False) -> None:
        """Clear state at an explicit daemon/profile lifecycle boundary.

        By default this only resets memory. ``persist=True`` atomically replaces
        the previous snapshot with an empty state, preventing fields from an old
        profile/runtime being presented as current. ``notify=True`` also sends
        that empty state to in-process subscribers.
        """

        with self._publish_lock:
            with self._lock:
                self._state.clear()
                subscribers = list(self._subscribers) if notify else []
                runtime = copy.deepcopy(self._runtime)

            if persist:
                try:
                    self._write_status_file({}, runtime)
                except Exception:
                    logger.exception("Failed to persist cleared status snapshot to %s", self.path)

            for fn in subscribers:
                try:
                    fn({})
                except Exception:
                    logger.exception(
                        "Status subscriber failed during reset fn=%s",
                        getattr(fn, "__name__", repr(fn)),
                    )

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._state)

    def runtime_snapshot(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(self._runtime)

    def publish(self, update: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(update, dict):
            raise TypeError("status update must be a dictionary")

        with self._publish_lock:
            with self._lock:
                _deep_merge(self._state, update)
                snapshot = copy.deepcopy(self._state)
                runtime = copy.deepcopy(self._runtime)
                subscribers = list(self._subscribers)

            try:
                self._write_status_file(snapshot, runtime)
            except Exception:
                logger.exception("Failed to persist status snapshot to %s", self.path)

            for fn in subscribers:
                try:
                    fn(copy.deepcopy(snapshot))
                except Exception:
                    logger.exception(
                        "Status subscriber failed fn=%s",
                        getattr(fn, "__name__", repr(fn)),
                    )

            return snapshot

    def publish_runtime(self, runtime: Dict[str, Any]) -> Dict[str, Any]:
        """Persist daemon-loaded configuration evidence outside decoded state.

        Runtime evidence is wrapper metadata rather than a decoded status path, so
        vehicle profiles cannot overwrite it through a status rule. Publishing it
        does not notify decoded-state subscribers.
        """

        if not isinstance(runtime, dict):
            raise TypeError("runtime update must be a dictionary")

        with self._publish_lock:
            with self._lock:
                self._runtime = copy.deepcopy(runtime)
                snapshot = copy.deepcopy(self._state)
                persisted_runtime = copy.deepcopy(self._runtime)

            try:
                self._write_status_file(snapshot, persisted_runtime)
            except Exception:
                logger.exception("Failed to persist runtime evidence to %s", self.path)

            return copy.deepcopy(persisted_runtime)

    def _write_status_file(
        self,
        snapshot: Dict[str, Any],
        runtime: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "updated_at": self._clock(),
            "state": snapshot,
        }
        if runtime is not None:
            payload["runtime"] = runtime
        tmp_path: Optional[Path] = None

        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=str(self.path.parent),
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
                tmp_path = Path(handle.name)

            os.replace(str(tmp_path), str(self.path))
            tmp_path = None
            self._fsync_parent_directory()
        finally:
            if tmp_path is not None:
                try:
                    tmp_path.unlink()
                except FileNotFoundError:
                    pass

    def _fsync_parent_directory(self) -> None:
        flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            flags |= os.O_DIRECTORY

        try:
            directory_fd = os.open(str(self.path.parent), flags)
        except OSError:
            # Some platforms/filesystems do not permit directory fsync. The
            # atomic replace is still valid; durability is best effort there.
            return

        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)


_default_bus = StatusBus(STATUS_PATH)


def _sync_default_path() -> None:
    # Preserve the long-standing ability for tests/embedders to replace the
    # module-level STATUS_PATH after import.
    _default_bus.path = Path(STATUS_PATH)


def _write_status_file(snapshot: Dict[str, Any]) -> None:
    _sync_default_path()
    _default_bus._write_status_file(
        copy.deepcopy(snapshot),
        _default_bus.runtime_snapshot(),
    )


def subscribe(fn: Callable[[Dict[str, Any]], None]) -> None:
    _default_bus.subscribe(fn)


def unsubscribe(fn: Callable[[Dict[str, Any]], None]) -> bool:
    return _default_bus.unsubscribe(fn)


def reset(persist: bool = False, notify: bool = False) -> None:
    _sync_default_path()
    _default_bus.reset(persist=persist, notify=notify)


def publish(update: Dict[str, Any]) -> Dict[str, Any]:
    _sync_default_path()
    return _default_bus.publish(update)


def publish_runtime(runtime: Dict[str, Any]) -> Dict[str, Any]:
    _sync_default_path()
    return _default_bus.publish_runtime(runtime)


def snapshot() -> Dict[str, Any]:
    return _default_bus.snapshot()


def runtime_snapshot() -> Optional[Dict[str, Any]]:
    return _default_bus.runtime_snapshot()
