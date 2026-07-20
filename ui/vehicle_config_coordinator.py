"""Read-only privileged vehicle configuration coordination.

The coordinator owns a fixed local Unix-socket boundary, persistent public
transaction state, and independent non-mutating preview validation. Apply and
restore remain unavailable until atomic activation and verified restoration are
implemented.
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

from ui import vehicle_configuration, vehicle_setup


API_VERSION = 1
STATE_SCHEMA_VERSION = 1
DEFAULT_STATE_FILE = Path("/var/lib/open-mmi/vehicle-configuration-state.json")
DEFAULT_SOCKET = Path("/run/open-mmi/vehicle-configuration-coordinator.sock")
DEFAULT_LOCK = Path("/run/open-mmi/vehicle-configuration.lock")
DEFAULT_LIFECYCLE_LOCK = Path("/run/open-mmi/lifecycle.lock")
DEFAULT_UPDATE_LOCK = Path("/run/open-mmi/update.lock")
DEFAULT_GROUP = "open-mmi-config"
DEFAULT_INSTALL_ROOT = Path("/opt/open-mmi")
DEFAULT_CONFIG_ROOT = Path("/var/lib/open-mmi/custom-catalogue-unconfigured")
DEFAULT_RUNTIME_DROPIN = Path("/etc/open-mmi/canbusd-runtime-unconfigured.conf")
DEFAULT_RUNTIME_STATUS = Path("/run/open-mmi/canbusd-status-unconfigured.json")
MAX_REQUEST_BYTES = 4096
MAX_RESPONSE_BYTES = 256 * 1024
MAX_CONFIGURED_PATH_LENGTH = 4096
MAX_ERROR_LENGTH = 512
ACTIVE_STATES = {"validating", "applying", "reloading", "verifying", "restoring"}
TERMINAL_STATES = {"idle", "complete", "failed"}
ALLOWED_STATES = ACTIVE_STATES | TERMINAL_STATES
_TRANSACTION_RE = re.compile(r"^configuration-[0-9a-f]{32}$")
_STAGE_RE = re.compile(r"^[a-z][a-z0-9-]{0,31}$")


class CoordinatorError(RuntimeError):
    """A fail-closed coordinator boundary error."""


def _unique_json_object(pairs: Sequence[tuple[str, Any]]) -> Dict[str, Any]:
    value: Dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise CoordinatorError(f"Duplicate coordinator JSON field: {key}")
        value[key] = item
    return value


def _reject_json_constant(value: str) -> None:
    raise CoordinatorError(f"Invalid coordinator JSON number: {value}")


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


def _lock_status(
    configuration_lock: Path = DEFAULT_LOCK,
    lifecycle_lock: Path = DEFAULT_LIFECYCLE_LOCK,
    update_lock: Path = DEFAULT_UPDATE_LOCK,
) -> Dict[str, bool]:
    return {
        "configuration_active": _lock_active(configuration_lock),
        "lifecycle_active": _lock_active(lifecycle_lock),
        "update_active": _lock_active(update_lock),
    }


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
        "preview_enabled": True,
        "apply_enabled": False,
        "restore_enabled": False,
        "locks": _lock_status(configuration_lock, lifecycle_lock, update_lock),
        "state": dict(state),
    }


def _configured_path(name: str, default: Path) -> Path:
    raw = str(os.environ.get(name) or default)
    if (
        not _bounded_text(raw, MAX_CONFIGURED_PATH_LENGTH, allow_empty=False)
        or "\x00" in raw
    ):
        raise CoordinatorError(f"{name} is invalid")
    path = Path(raw)
    if not path.is_absolute() or ".." in path.parts:
        raise CoordinatorError(f"{name} must be an absolute fixed path")
    return path


def _preview_context() -> tuple[vehicle_setup.CatalogueRoots, Path, Path]:
    roots = vehicle_setup.CatalogueRoots(
        maintained=_configured_path("OPEN_MMI_INSTALL_DIR", DEFAULT_INSTALL_ROOT),
        custom=_configured_path("OPEN_MMI_CONFIG_DIR", DEFAULT_CONFIG_ROOT),
    )
    return (
        roots,
        _configured_path("OPEN_MMI_RUNTIME_DROPIN", DEFAULT_RUNTIME_DROPIN),
        _configured_path("OPEN_MMI_STATUS_PATH", DEFAULT_RUNTIME_STATUS),
    )


def coordinator_preview(
    request: Mapping[str, Any],
    *,
    roots: Optional[vehicle_setup.CatalogueRoots] = None,
    dropin_path: Optional[Path] = None,
    status_path: Optional[Path] = None,
    sys_class_net: Path = Path("/sys/class/net"),
    configuration_lock: Path = DEFAULT_LOCK,
    lifecycle_lock: Path = DEFAULT_LIFECYCLE_LOCK,
    update_lock: Path = DEFAULT_UPDATE_LOCK,
) -> Dict[str, Any]:
    """Independently rebuild a non-mutating preview inside the root boundary."""

    if roots is None or dropin_path is None or status_path is None:
        configured_roots, configured_dropin, configured_status = _preview_context()
        roots = roots or configured_roots
        dropin_path = dropin_path or configured_dropin
        status_path = status_path or configured_status

    runtime_environment = vehicle_setup.read_runtime_environment(dropin_path)
    current_status = vehicle_setup.status_payload(
        roots,
        environment=runtime_environment,
        sys_class_net=sys_class_net,
        status_path=status_path,
    )
    preview = vehicle_setup.preview_payload(
        request,
        roots,
        current_status=current_status,
        sys_class_net=sys_class_net,
    )
    locks = _lock_status(configuration_lock, lifecycle_lock, update_lock)
    preview["coordinator"] = {
        "previewed": True,
        "read_only": True,
        "locks": locks,
        "apply_blocked": any(locks.values()),
    }
    return preview


def response_for_request(
    payload: object,
    state_path: Path = DEFAULT_STATE_FILE,
    configuration_lock: Path = DEFAULT_LOCK,
    lifecycle_lock: Path = DEFAULT_LIFECYCLE_LOCK,
    update_lock: Path = DEFAULT_UPDATE_LOCK,
    *,
    preview_roots: Optional[vehicle_setup.CatalogueRoots] = None,
    preview_dropin_path: Optional[Path] = None,
    preview_status_path: Optional[Path] = None,
    preview_sys_class_net: Path = Path("/sys/class/net"),
) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {"ok": False, "error": "Invalid coordinator request schema"}
    if payload.get("api_version") != API_VERSION:
        return {"ok": False, "error": "Unsupported coordinator API version"}

    action = payload.get("action")
    try:
        if action == "status":
            if set(payload) != {"api_version", "action"}:
                return {"ok": False, "error": "Invalid coordinator request schema"}
            return _public_response(
                read_state(state_path),
                configuration_lock,
                lifecycle_lock,
                update_lock,
            )
        if action == "preview":
            if set(payload) != {"api_version", "action", "request"}:
                return {"ok": False, "error": "Invalid coordinator request schema"}
            request = payload.get("request")
            if not isinstance(request, Mapping):
                return {"ok": False, "error": "Invalid coordinator preview schema"}
            preview = coordinator_preview(
                request,
                roots=preview_roots,
                dropin_path=preview_dropin_path,
                status_path=preview_status_path,
                sys_class_net=preview_sys_class_net,
                configuration_lock=configuration_lock,
                lifecycle_lock=lifecycle_lock,
                update_lock=update_lock,
            )
            return {
                "ok": True,
                "api_version": API_VERSION,
                "action": "preview",
                "preview": preview,
            }
        return {"ok": False, "error": "Coordinator action is not enabled"}
    except (
        CoordinatorError,
        vehicle_configuration.VehicleConfigurationError,
        vehicle_setup.VehicleSetupError,
    ) as exc:
        return {"ok": False, "error": str(exc)}


class _Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        raw = self.rfile.readline(MAX_REQUEST_BYTES + 1)
        if not raw or len(raw) > MAX_REQUEST_BYTES:
            response = {"ok": False, "error": "Invalid coordinator request size"}
        else:
            try:
                payload: object = json.loads(
                    raw.decode("utf-8"),
                    object_pairs_hook=_unique_json_object,
                    parse_constant=_reject_json_constant,
                )
            except (UnicodeError, json.JSONDecodeError, CoordinatorError):
                payload = None
            response = response_for_request(payload, self.server.state_path)  # type: ignore[attr-defined]
        try:
            encoded = (json.dumps(response, sort_keys=True) + "\n").encode("utf-8")
            if len(encoded) > MAX_RESPONSE_BYTES:
                encoded = (
                    json.dumps(
                        {"ok": False, "error": "Coordinator response exceeds the size limit"},
                        sort_keys=True,
                    )
                    + "\n"
                ).encode("utf-8")
            self.wfile.write(encoded)
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
    request = json.dumps(dict(payload), separators=(",", ":")).encode("utf-8") + b"\n"
    if len(request) > MAX_REQUEST_BYTES:
        raise CoordinatorError("Coordinator request exceeds the size limit")
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(timeout)
            connection.connect(str(socket_path))
            connection.sendall(request)
            response = connection.makefile("rb").readline(MAX_RESPONSE_BYTES + 1)
        if not response or len(response) > MAX_RESPONSE_BYTES:
            raise CoordinatorError("Coordinator returned an invalid response size")
        decoded = json.loads(
            response.decode("utf-8"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except CoordinatorError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CoordinatorError("Vehicle configuration coordinator is unavailable") from exc
    if not isinstance(decoded, dict):
        raise CoordinatorError("Coordinator returned an invalid response")
    if decoded.get("ok") is not True:
        raise CoordinatorError(str(decoded.get("error") or "Coordinator request failed"))
    return decoded


def client_status(socket_path: Path = DEFAULT_SOCKET) -> Dict[str, Any]:
    return _client_request({"api_version": API_VERSION, "action": "status"}, socket_path)


def client_preview(
    request: Mapping[str, Any],
    socket_path: Path = DEFAULT_SOCKET,
) -> Dict[str, Any]:
    response = _client_request(
        {
            "api_version": API_VERSION,
            "action": "preview",
            "request": dict(request),
        },
        socket_path,
    )
    if (
        response.get("api_version") != API_VERSION
        or response.get("action") != "preview"
    ):
        raise CoordinatorError("Coordinator returned an invalid preview wrapper")
    preview = response.get("preview")
    if not isinstance(preview, dict) or (
        preview.get("api_version") != API_VERSION
        or preview.get("read_only") is not True
        or preview.get("apply_available") is not False
        or preview.get("state") != "ready"
    ):
        raise CoordinatorError("Coordinator returned an invalid preview")

    expected_revision = preview.get("expected_configuration_revision")
    target_revision = preview.get("target_configuration_revision")
    try:
        target = vehicle_configuration.normalize_selection(preview.get("target"))
    except vehicle_configuration.VehicleConfigurationError as exc:
        raise CoordinatorError("Coordinator returned an invalid preview target") from exc
    if (
        not isinstance(expected_revision, str)
        or not vehicle_configuration.REVISION_RE.fullmatch(expected_revision)
        or not isinstance(target_revision, str)
        or not vehicle_configuration.REVISION_RE.fullmatch(target_revision)
        or target_revision != vehicle_configuration.selection_revision(target)
    ):
        raise CoordinatorError("Coordinator returned invalid preview revisions")

    metadata = preview.get("coordinator")
    if not isinstance(metadata, dict) or set(metadata) != {
        "previewed",
        "read_only",
        "locks",
        "apply_blocked",
    }:
        raise CoordinatorError("Coordinator returned invalid preview metadata")
    locks = metadata.get("locks")
    if (
        metadata.get("previewed") is not True
        or metadata.get("read_only") is not True
        or not isinstance(locks, dict)
        or set(locks)
        != {"configuration_active", "lifecycle_active", "update_active"}
        or any(not isinstance(value, bool) for value in locks.values())
        or not isinstance(metadata.get("apply_blocked"), bool)
        or metadata["apply_blocked"] is not any(locks.values())
    ):
        raise CoordinatorError("Coordinator returned invalid preview metadata")
    return dict(preview)


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
