"""Read-only foundation for privileged vehicle configuration coordination.

The coordinator owns a fixed local Unix-socket boundary and persistent public
transaction state.  This first slice intentionally enables only ``status``;
preview remains in the unprivileged planning layer and apply/restore are not
available until atomic activation and verified restoration are implemented.
"""

from __future__ import annotations

import argparse
import fcntl
import grp
import json
import os
import re
import socket
import socketserver
import stat
import tempfile
from contextlib import AbstractContextManager, ExitStack
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from ui import vehicle_configuration


API_VERSION = 1
STATE_SCHEMA_VERSION = 1
DEFAULT_STATE_FILE = Path("/var/lib/open-mmi/vehicle-configuration-state.json")
DEFAULT_SOCKET = Path("/run/open-mmi/vehicle-configuration-coordinator.sock")
DEFAULT_LOCK = Path("/run/open-mmi/vehicle-configuration.lock")
DEFAULT_LIFECYCLE_LOCK = Path("/run/open-mmi/lifecycle.lock")
DEFAULT_UPDATE_LOCK = Path("/run/open-mmi/update.lock")
DEFAULT_GROUP = "open-mmi-config"
MAX_REQUEST_BYTES = 4096
MAX_ERROR_LENGTH = 512
ACTIVE_STATES = {"validating", "applying", "reloading", "verifying", "restoring"}
TERMINAL_STATES = {"idle", "complete", "failed"}
ALLOWED_STATES = ACTIVE_STATES | TERMINAL_STATES
_TRANSACTION_RE = re.compile(r"^configuration-[0-9a-f]{32}$")
_STAGE_RE = re.compile(r"^[a-z][a-z0-9-]{0,31}$")


class CoordinatorError(RuntimeError):
    """A fail-closed coordinator boundary error."""


def _timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def initial_state() -> Dict[str, Any]:
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "state": "idle",
        "transaction_id": None,
        "started_at": None,
        "updated_at": _timestamp(),
        "completed_at": None,
        "stage": "idle",
        "target": None,
        "expected_configuration_revision": "",
        "restoration_attempted": False,
        "restoration_verified": False,
        "error": "",
        "recovered": False,
    }


def _bounded_text(value: object, maximum: int, *, allow_empty: bool = True) -> bool:
    return (
        isinstance(value, str)
        and (allow_empty or bool(value))
        and len(value) <= maximum
        and not any(ord(character) < 32 for character in value)
    )


def _validate_timestamp(value: object) -> bool:
    if value is None:
        return True
    if not _bounded_text(value, 64, allow_empty=False):
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _validate_target(value: object) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {
        "vehicle",
        "bindings",
        "active_bus",
        "interface",
    }:
        raise CoordinatorError("Coordinator target schema is invalid")

    normalized: Dict[str, Any] = {}
    for kind in ("vehicle", "bindings"):
        identity = value.get(kind)
        if not isinstance(identity, dict) or set(identity) != {"source", "id", "revision"}:
            raise CoordinatorError("Coordinator target identity is invalid")
        source = identity.get("source")
        identifier = identity.get("id")
        revision = identity.get("revision")
        if source not in vehicle_configuration.SOURCES:
            raise CoordinatorError("Coordinator target source is invalid")
        if not isinstance(identifier, str) or not vehicle_configuration.IDENTIFIER_RE.fullmatch(identifier):
            raise CoordinatorError("Coordinator target identifier is invalid")
        if not isinstance(revision, str) or not vehicle_configuration.REVISION_RE.fullmatch(revision):
            raise CoordinatorError("Coordinator target revision is invalid")
        normalized[kind] = {
            "source": source,
            "id": identifier,
            "revision": revision,
        }

    active_bus = value.get("active_bus")
    interface = value.get("interface")
    if not isinstance(active_bus, str) or not vehicle_configuration.IDENTIFIER_RE.fullmatch(active_bus):
        raise CoordinatorError("Coordinator target bus is invalid")
    if not isinstance(interface, str) or not vehicle_configuration.INTERFACE_RE.fullmatch(interface):
        raise CoordinatorError("Coordinator target interface is invalid")
    normalized["active_bus"] = active_bus
    normalized["interface"] = interface
    return normalized


def _validate_state(payload: object) -> Dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != set(initial_state()):
        raise CoordinatorError("Coordinator state schema is invalid")
    if payload.get("schema_version") != STATE_SCHEMA_VERSION:
        raise CoordinatorError("Coordinator state schema is invalid")

    state = payload.get("state")
    if state not in ALLOWED_STATES:
        raise CoordinatorError("Coordinator transaction state is invalid")
    stage = payload.get("stage")
    if not isinstance(stage, str) or not _STAGE_RE.fullmatch(stage):
        raise CoordinatorError("Coordinator transaction stage is invalid")
    if not all(_validate_timestamp(payload.get(key)) for key in ("started_at", "updated_at", "completed_at")):
        raise CoordinatorError("Coordinator transaction timestamp is invalid")

    transaction_id = payload.get("transaction_id")
    if transaction_id is not None and (
        not isinstance(transaction_id, str) or not _TRANSACTION_RE.fullmatch(transaction_id)
    ):
        raise CoordinatorError("Coordinator transaction identifier is invalid")

    revision = payload.get("expected_configuration_revision")
    if not isinstance(revision, str) or (
        revision and not vehicle_configuration.REVISION_RE.fullmatch(revision)
    ):
        raise CoordinatorError("Coordinator configuration revision is invalid")

    for key in ("restoration_attempted", "restoration_verified", "recovered"):
        if not isinstance(payload.get(key), bool):
            raise CoordinatorError("Coordinator boolean state is invalid")
    if payload.get("restoration_verified") and not payload.get("restoration_attempted"):
        raise CoordinatorError("Coordinator restoration state is invalid")

    error = payload.get("error")
    if not _bounded_text(error, MAX_ERROR_LENGTH):
        raise CoordinatorError("Coordinator error state is invalid")

    validated = dict(payload)
    validated["target"] = _validate_target(payload.get("target"))
    return validated


def _trusted_regular_file(path: Path, *, require_root: bool = True) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    expected_uid = 0 if require_root else os.geteuid()
    return (
        stat.S_ISREG(metadata.st_mode)
        and metadata.st_uid == expected_uid
        and not metadata.st_mode & 0o022
    )


def read_state(path: Path = DEFAULT_STATE_FILE) -> Dict[str, Any]:
    if not path.exists():
        return initial_state()
    if path == DEFAULT_STATE_FILE and not _trusted_regular_file(path):
        raise CoordinatorError("Coordinator state file is untrusted")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CoordinatorError("Coordinator state file is invalid") from exc
    return _validate_state(payload)


def write_state(payload: Mapping[str, Any], path: Path = DEFAULT_STATE_FILE) -> Dict[str, Any]:
    if os.geteuid() != 0 and path == DEFAULT_STATE_FILE:
        raise CoordinatorError("Writing production coordinator state requires root")
    validated = _validate_state(dict(payload))
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    temporary_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            json.dump(validated, temporary, indent=2, sort_keys=True)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.chmod(temporary_name, 0o644)
        os.replace(temporary_name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        if temporary_name:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
        raise CoordinatorError("Could not persist coordinator state") from exc
    return validated


def recover_interrupted_state(path: Path = DEFAULT_STATE_FILE) -> Dict[str, Any]:
    state = read_state(path) if path.exists() else initial_state()
    if state["state"] in ACTIVE_STATES:
        state.update(
            {
                "state": "failed",
                "stage": "recovery",
                "updated_at": _timestamp(),
                "completed_at": _timestamp(),
                "error": "Coordinator restarted during an active transaction",
                "recovered": True,
            }
        )
    return write_state(state, path)


class TransactionLock(AbstractContextManager["TransactionLock"]):
    """Acquire one trusted non-blocking advisory transaction lock."""

    def __init__(self, path: Path, busy_error: str):
        self.path = path
        self.busy_error = busy_error
        self.handle: Optional[Any] = None

    def __enter__(self) -> "TransactionLock":
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        self.handle = self.path.open("a+", encoding="utf-8")
        os.chmod(self.path, 0o644)
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.handle.close()
            self.handle = None
            raise CoordinatorError(self.busy_error) from exc
        return self

    def __exit__(self, *args: object) -> None:
        if self.handle is not None:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()
            self.handle = None


class ConfigurationTransactionLocks(AbstractContextManager["ConfigurationTransactionLocks"]):
    """Reserve lifecycle, update and vehicle-configuration boundaries."""

    def __init__(
        self,
        configuration_path: Path = DEFAULT_LOCK,
        lifecycle_path: Path = DEFAULT_LIFECYCLE_LOCK,
        update_path: Path = DEFAULT_UPDATE_LOCK,
    ):
        self.configuration_path = configuration_path
        self.lifecycle_path = lifecycle_path
        self.update_path = update_path
        self.stack: Optional[ExitStack] = None

    def __enter__(self) -> "ConfigurationTransactionLocks":
        stack = ExitStack()
        try:
            stack.enter_context(
                TransactionLock(
                    self.lifecycle_path,
                    "Another Open MMI lifecycle transaction is active",
                )
            )
            stack.enter_context(
                TransactionLock(
                    self.update_path,
                    "An Open MMI update transaction is active",
                )
            )
            stack.enter_context(
                TransactionLock(
                    self.configuration_path,
                    "Another vehicle configuration transaction is active",
                )
            )
        except Exception:
            stack.close()
            raise
        self.stack = stack
        return self

    def __exit__(self, *args: object) -> None:
        if self.stack is not None:
            self.stack.close()
            self.stack = None


def _lock_active(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise CoordinatorError("Coordinator lock state cannot be inspected") from exc
    production_locks = {DEFAULT_LOCK, DEFAULT_LIFECYCLE_LOCK, DEFAULT_UPDATE_LOCK}
    if not _trusted_regular_file(path, require_root=path in production_locks):
        raise CoordinatorError("Coordinator lock file is untrusted")
    try:
        with path.open("r", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except BlockingIOError:
        return True
    except OSError as exc:
        raise CoordinatorError("Coordinator lock state cannot be inspected") from exc
    return False


def _public_response(
    state: Mapping[str, Any],
    configuration_lock: Path = DEFAULT_LOCK,
    lifecycle_lock: Path = DEFAULT_LIFECYCLE_LOCK,
    update_lock: Path = DEFAULT_UPDATE_LOCK,
) -> Dict[str, Any]:
    return {
        "ok": True,
        "api_version": API_VERSION,
        "read_only": True,
        "preview_enabled": False,
        "apply_enabled": False,
        "restore_enabled": False,
        "locks": {
            "configuration_active": _lock_active(configuration_lock),
            "lifecycle_active": _lock_active(lifecycle_lock),
            "update_active": _lock_active(update_lock),
        },
        "state": dict(state),
    }


def response_for_request(
    payload: object,
    state_path: Path = DEFAULT_STATE_FILE,
    configuration_lock: Path = DEFAULT_LOCK,
    lifecycle_lock: Path = DEFAULT_LIFECYCLE_LOCK,
    update_lock: Path = DEFAULT_UPDATE_LOCK,
) -> Dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != {"api_version", "action"}:
        return {"ok": False, "error": "Invalid coordinator request schema"}
    if payload.get("api_version") != API_VERSION:
        return {"ok": False, "error": "Unsupported coordinator API version"}
    if payload.get("action") != "status":
        return {"ok": False, "error": "Coordinator action is not enabled"}
    try:
        return _public_response(
            read_state(state_path),
            configuration_lock,
            lifecycle_lock,
            update_lock,
        )
    except CoordinatorError as exc:
        return {"ok": False, "error": str(exc)}


class _Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        raw = self.rfile.readline(MAX_REQUEST_BYTES + 1)
        if not raw or len(raw) > MAX_REQUEST_BYTES:
            response = {"ok": False, "error": "Invalid coordinator request size"}
        else:
            try:
                payload: object = json.loads(raw.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError):
                payload = None
            response = response_for_request(payload, self.server.state_path)  # type: ignore[attr-defined]
        try:
            self.wfile.write((json.dumps(response, sort_keys=True) + "\n").encode("utf-8"))
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass


class CoordinatorServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    allow_reuse_address = False
    daemon_threads = True

    def __init__(self, socket_path: Path, state_path: Path):
        self.socket_path = socket_path
        self.state_path = state_path
        socket_path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        try:
            existing = socket_path.lstat()
        except FileNotFoundError:
            existing = None
        expected_uid = 0 if socket_path == DEFAULT_SOCKET else os.geteuid()
        if existing is not None:
            if not stat.S_ISSOCK(existing.st_mode) or existing.st_uid != expected_uid:
                raise CoordinatorError("Coordinator socket path is occupied by an untrusted object")
            socket_path.unlink()
        super().__init__(str(socket_path), _Handler)
        os.chmod(socket_path, 0o660)
        try:
            os.chown(socket_path, 0, grp.getgrnam(DEFAULT_GROUP).gr_gid)
        except KeyError as exc:
            self.server_close()
            raise CoordinatorError("Coordinator access group is unavailable") from exc

    def server_close(self) -> None:
        super().server_close()
        try:
            metadata = self.socket_path.lstat()
            expected_uid = 0 if self.socket_path == DEFAULT_SOCKET else os.geteuid()
            if stat.S_ISSOCK(metadata.st_mode) and metadata.st_uid == expected_uid:
                self.socket_path.unlink()
        except OSError:
            pass


def _client_request(
    payload: Mapping[str, Any],
    socket_path: Path = DEFAULT_SOCKET,
    timeout: float = 3.0,
) -> Dict[str, Any]:
    request = json.dumps(dict(payload)).encode("utf-8") + b"\n"
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(timeout)
            connection.connect(str(socket_path))
            connection.sendall(request)
            response = connection.makefile("rb").readline(MAX_REQUEST_BYTES + 1)
        decoded = json.loads(response.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CoordinatorError("Vehicle configuration coordinator is unavailable") from exc
    if not isinstance(decoded, dict):
        raise CoordinatorError("Coordinator returned an invalid response")
    if decoded.get("ok") is not True:
        raise CoordinatorError(str(decoded.get("error") or "Coordinator request failed"))
    return decoded


def client_status(socket_path: Path = DEFAULT_SOCKET) -> Dict[str, Any]:
    return _client_request({"api_version": API_VERSION, "action": "status"}, socket_path)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Open MMI vehicle configuration coordinator")
    parser.add_argument("command", choices=("serve", "status"))
    args = parser.parse_args(argv)
    if args.command == "status":
        print(json.dumps(client_status(), indent=2, sort_keys=True))
        return 0
    if os.geteuid() != 0:
        raise SystemExit("open-mmi-vehicle-config-coordinator: serve requires root")
    recover_interrupted_state()
    with CoordinatorServer(DEFAULT_SOCKET, DEFAULT_STATE_FILE) as server:
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
