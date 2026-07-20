"""Privileged vehicle configuration coordination.

The coordinator owns a fixed local Unix-socket boundary, persistent public
transaction state, independent preview validation, and the fixed apply action.
The browser UI remains disabled until its review/progress workflow is connected.
A separate root-only, one-shot vcan round-trip command remains available for
qualification of the apply and restoration engine.
"""

from __future__ import annotations

import argparse
import fcntl
import grp
import json
import os
import pwd
import re
import signal
import socket
import socketserver
import stat
import sys
import tempfile
import uuid
from contextlib import AbstractContextManager, ExitStack
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Protocol, Sequence

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
DEFAULT_COORDINATOR_ENV = Path("/etc/open-mmi/vehicle-config-coordinator.env")
DEFAULT_QUALIFICATION_GATE = Path(
    "/etc/open-mmi/enable-vcan-vehicle-configuration-qualification"
)
QUALIFICATION_GATE_CONTENT = b"OPEN_MMI_ALLOW_VCAN_CONFIGURATION_APPLY=1\n"
MAX_REQUEST_BYTES = 4096
MAX_RESPONSE_BYTES = 256 * 1024
DEFAULT_APPLY_TIMEOUT = 60.0
MAX_QUALIFICATION_PREVIEW_BYTES = 256 * 1024
MAX_CONFIGURED_PATH_LENGTH = 4096
MAX_ERROR_LENGTH = 512
ACTIVE_STATES = {"validating", "applying", "reloading", "verifying", "restoring"}
TERMINAL_STATES = {"idle", "complete", "failed"}
ALLOWED_STATES = ACTIVE_STATES | TERMINAL_STATES
_TRANSACTION_RE = re.compile(r"^configuration-[0-9a-f]{32}$")
_STAGE_RE = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
_VCAN_INTERFACE_RE = re.compile(r"^vcan[0-9]{1,3}$")
_ABSENT_CAN_INTERFACE_RE = re.compile(r"^can[0-9]{1,3}$")
_DROPIN_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}\.conf$")
_COORDINATOR_ENV_KEYS = {
    "OPEN_MMI_INSTALL_DIR",
    "OPEN_MMI_CONFIG_DIR",
    "OPEN_MMI_RUNTIME_DROPIN",
    "OPEN_MMI_STATUS_PATH",
}
_MANAGED_RUNTIME_KEYS = {
    "OPEN_MMI_VEHICLE",
    "OPEN_MMI_BINDINGS",
    "OPEN_MMI_VEHICLE_CONFIG",
    "OPEN_MMI_BINDINGS_FILE",
    "OPEN_MMI_CAN_BUS",
    "OPEN_MMI_CAN_INTERFACE",
}


class CoordinatorError(RuntimeError):
    """A fail-closed coordinator boundary error."""


class CoordinatorUnavailableError(CoordinatorError):
    """The fixed local coordinator boundary could not be reached."""


class CoordinatorConflictError(CoordinatorError):
    """A stale preview or active lifecycle transaction blocked apply."""

    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


class CoordinatorApplyError(CoordinatorError):
    """An apply failed after the coordinator created transaction state."""

    def __init__(self, message: str, code: str, state: Mapping[str, Any]):
        super().__init__(message)
        self.code = code
        self.state = dict(state)


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
            raise CoordinatorConflictError(self.busy_error, "busy") from exc
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


def _restoration_required(state: Mapping[str, Any]) -> bool:
    return bool(
        state.get("state") == "failed"
        and state.get("stage") == "restore-unverified"
        and state.get("restoration_attempted") is True
        and state.get("restoration_verified") is False
    )


def _public_response(
    state: Mapping[str, Any],
    configuration_lock: Path = DEFAULT_LOCK,
    lifecycle_lock: Path = DEFAULT_LIFECYCLE_LOCK,
    update_lock: Path = DEFAULT_UPDATE_LOCK,
    *,
    apply_enabled: bool = False,
) -> Dict[str, Any]:
    effective_apply_enabled = apply_enabled and not _restoration_required(state)
    return {
        "ok": True,
        "api_version": API_VERSION,
        "read_only": not effective_apply_enabled,
        "preview_enabled": True,
        "apply_enabled": effective_apply_enabled,
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


class ApplyOperations(Protocol):
    """Fixed coordinator-owned system operations for one apply transaction."""

    def snapshot(self, transaction_id: str) -> object: ...
    def install(self, target: Mapping[str, Any]) -> None: ...
    def reload(self, target: Mapping[str, Any]) -> None: ...
    def restart(self) -> None: ...
    def loaded_runtime(self) -> Mapping[str, Any]: ...
    def restore(self, snapshot: object) -> None: ...
    def restoration_verified(self, snapshot: object, loaded: Mapping[str, Any]) -> bool: ...


class RecoverableApplyOperations(ApplyOperations, Protocol):
    """Apply operations able to reopen a durable rollback snapshot."""

    def load_snapshot(self, transaction_id: str) -> object: ...


class QualificationApplyOperations(RecoverableApplyOperations, Protocol):
    """Apply operations used by the one-shot vcan qualification command."""

    def discard_snapshot(self, snapshot: object) -> None: ...


ApplyOperationsFactory = Callable[[Mapping[str, Any]], ApplyOperations]
PreSnapshotValidator = Callable[[Mapping[str, Any]], None]


def _request_for_target(target: Mapping[str, Any]) -> Dict[str, Any]:
    """Drop reviewed revisions and rebuild the fixed preview request schema."""

    normalized = vehicle_configuration.normalize_selection(target)
    active_bus = normalized["runtime"]["active_bus"]
    return {
        "vehicle": {
            "source": normalized["vehicle"]["source"],
            "id": normalized["vehicle"]["id"],
        },
        "bindings": {
            "source": normalized["bindings"]["source"],
            "id": normalized["bindings"]["id"],
        },
        "runtime": {
            "active_bus": active_bus,
            "buses": {
                active_bus: {
                    "interface": normalized["runtime"]["buses"][active_bus][
                        "interface"
                    ]
                }
            },
        },
    }


def _normalize_apply_payload(
    payload: object,
) -> tuple[Dict[str, Any], Dict[str, Any], str]:
    """Validate the exact reviewed apply body accepted by HTTP and the socket."""

    if not isinstance(payload, Mapping) or set(payload) != {
        "target",
        "expected_configuration_revision",
        "target_configuration_revision",
        "confirm",
    }:
        raise CoordinatorError("Invalid vehicle configuration apply schema")
    if payload.get("confirm") is not True:
        raise CoordinatorError(
            "Vehicle configuration apply requires explicit confirmation"
        )
    expected_revision = payload.get("expected_configuration_revision")
    target_revision = payload.get("target_configuration_revision")
    if (
        not isinstance(expected_revision, str)
        or not vehicle_configuration.REVISION_RE.fullmatch(expected_revision)
    ):
        raise CoordinatorError("Expected configuration revision is invalid")
    try:
        target = vehicle_configuration.normalize_selection(payload.get("target"))
    except vehicle_configuration.VehicleConfigurationError as exc:
        raise CoordinatorError("Reviewed vehicle configuration target is invalid") from exc
    if (
        not isinstance(target_revision, str)
        or not vehicle_configuration.REVISION_RE.fullmatch(target_revision)
        or target_revision != vehicle_configuration.selection_revision(target)
    ):
        raise CoordinatorError("Reviewed target configuration revision is invalid")
    return _request_for_target(target), target, expected_revision


def _state_update(path: Path, payload: Dict[str, Any], **changes: Any) -> Dict[str, Any]:
    payload.update(changes)
    payload["updated_at"] = _timestamp()
    return write_state(payload, path)


def _sanitized_failure(stage: str, exc: BaseException) -> str:
    """Return a bounded public error without leaking operation output."""

    if isinstance(exc, CoordinatorError):
        raw = str(exc) or "Vehicle configuration transaction failed"
    else:
        raw = f"Vehicle configuration operation failed during {stage}"
    sanitized = " ".join(raw.split())
    return sanitized[:MAX_ERROR_LENGTH] or "Vehicle configuration transaction failed"


def _best_effort_state_update(
    path: Path,
    payload: Dict[str, Any],
    **changes: Any,
) -> Dict[str, Any]:
    """Never allow public-state persistence to block restoration."""

    updated = dict(payload)
    updated.update(changes)
    updated["updated_at"] = _timestamp()
    try:
        return write_state(updated, path)
    except Exception:
        return updated


def _loaded_matches_target(loaded: Mapping[str, Any], target: Mapping[str, Any]) -> bool:
    try:
        return (
            loaded.get("state") == "ready"
            and loaded.get("errors") == []
            and loaded["vehicle"] == target["vehicle"]
            and loaded["bindings"] == target["bindings"]
            and loaded["active_bus"] == target["runtime"]["active_bus"]
            and loaded["interface"]
            == target["runtime"]["buses"][target["runtime"]["active_bus"]]["interface"]
        )
    except (KeyError, TypeError):
        return False


def run_apply_transaction(
    request: Mapping[str, Any],
    *,
    reviewed_target: Mapping[str, Any],
    expected_configuration_revision: str,
    confirm: bool,
    operations: Optional[ApplyOperations] = None,
    operations_factory: Optional[ApplyOperationsFactory] = None,
    pre_snapshot_validator: Optional[PreSnapshotValidator] = None,
    state_path: Path = DEFAULT_STATE_FILE,
    roots: Optional[vehicle_setup.CatalogueRoots] = None,
    dropin_path: Optional[Path] = None,
    status_path: Optional[Path] = None,
    sys_class_net: Path = Path("/sys/class/net"),
    configuration_lock: Path = DEFAULT_LOCK,
    lifecycle_lock: Path = DEFAULT_LIFECYCLE_LOCK,
    update_lock: Path = DEFAULT_UPDATE_LOCK,
    qualification_restore_on_success: bool = False,
) -> Dict[str, Any]:
    """Execute one fail-closed apply transaction.

    Apply is bound both to the active configuration revision and to the exact
    normalized target (including profile and bindings content revisions) that
    the user reviewed. System mutation is supplied only by coordinator-owned
    operations selected after stale-review checks while all transaction locks
    are held.
    """

    if confirm is not True:
        raise CoordinatorError("Vehicle configuration apply requires explicit confirmation")
    if (
        not isinstance(expected_configuration_revision, str)
        or not vehicle_configuration.REVISION_RE.fullmatch(expected_configuration_revision)
    ):
        raise CoordinatorError("Expected configuration revision is invalid")
    try:
        expected_target = vehicle_configuration.normalize_selection(reviewed_target)
    except vehicle_configuration.VehicleConfigurationError as exc:
        raise CoordinatorError("Reviewed vehicle configuration target is invalid") from exc
    if (operations is None) == (operations_factory is None):
        raise CoordinatorError("Vehicle configuration apply operations are unavailable")

    with ConfigurationTransactionLocks(configuration_lock, lifecycle_lock, update_lock):
        preview = coordinator_preview(
            request,
            roots=roots,
            dropin_path=dropin_path,
            status_path=status_path,
            sys_class_net=sys_class_net,
            configuration_lock=configuration_lock,
            lifecycle_lock=lifecycle_lock,
            update_lock=update_lock,
        )
        if preview["expected_configuration_revision"] != expected_configuration_revision:
            raise CoordinatorConflictError(
                "Vehicle configuration preview is stale",
                "stale-preview",
            )
        target = vehicle_configuration.normalize_selection(preview["target"])
        if target != expected_target:
            raise CoordinatorConflictError(
                "Vehicle configuration target changed after review",
                "stale-preview",
            )
        if preview.get("target_configuration_revision") != vehicle_configuration.selection_revision(target):
            raise CoordinatorConflictError(
                "Vehicle configuration preview target is inconsistent",
                "stale-preview",
            )
        if pre_snapshot_validator is not None:
            pre_snapshot_validator(target)
        if operations is not None:
            selected_operations = operations
        else:
            assert operations_factory is not None
            selected_operations = operations_factory(target)

        transaction_id = f"configuration-{uuid.uuid4().hex}"
        state = initial_state()
        state.update(
            {
                "state": "validating",
                "stage": "validated",
                "transaction_id": transaction_id,
                "started_at": _timestamp(),
                "target": {
                    "vehicle": target["vehicle"],
                    "bindings": target["bindings"],
                    "active_bus": target["runtime"]["active_bus"],
                    "interface": target["runtime"]["buses"][target["runtime"]["active_bus"]]["interface"],
                },
                "expected_configuration_revision": expected_configuration_revision,
            }
        )
        state = write_state(state, state_path)
        snapshot: object = None
        mutation_started = False
        stage = "snapshot"
        try:
            snapshot = selected_operations.snapshot(transaction_id)
            state = _state_update(state_path, state, state="applying", stage="installing")
            mutation_started = True
            stage = "installing"
            selected_operations.install(target)
            state = _state_update(state_path, state, state="reloading", stage="reloading")
            stage = "reloading"
            selected_operations.reload(target)
            stage = "restarting"
            selected_operations.restart()
            state = _state_update(state_path, state, state="verifying", stage="verifying")
            stage = "verifying"
            loaded = selected_operations.loaded_runtime()
            if not _loaded_matches_target(loaded, target):
                raise CoordinatorError("Applied vehicle configuration could not be verified")
            if qualification_restore_on_success:
                stage = "qualification-restoring"
                state = _state_update(
                    state_path,
                    state,
                    state="restoring",
                    stage=stage,
                    restoration_attempted=True,
                )
                selected_operations.restore(snapshot)
                selected_operations.restart()
                restored_loaded = selected_operations.loaded_runtime()
                if not selected_operations.restoration_verified(snapshot, restored_loaded):
                    raise CoordinatorError(
                        "Vehicle configuration qualification restoration could not be verified"
                    )
                completed = _state_update(
                    state_path,
                    state,
                    state="complete",
                    stage="qualification-restored",
                    completed_at=_timestamp(),
                    error="",
                    restoration_attempted=True,
                    restoration_verified=True,
                )
                # Persist the terminal state before deleting the only durable
                # snapshot. A process interruption may leave an extra snapshot,
                # but can never leave an active state with no recovery material.
                discard = getattr(selected_operations, "discard_snapshot", None)
                if callable(discard):
                    try:
                        discard(snapshot)
                    except Exception:
                        pass
                return completed
            now = _timestamp()
            return _state_update(
                state_path,
                state,
                state="complete",
                stage="complete",
                completed_at=now,
                error="",
                restoration_attempted=False,
                restoration_verified=False,
            )
        except BaseException as exc:
            error = _sanitized_failure(stage, exc)
            if mutation_started:
                state = _best_effort_state_update(
                    state_path,
                    state,
                    state="restoring",
                    stage="restoring",
                    restoration_attempted=True,
                    error=error,
                )
                restoration_verified = False
                try:
                    selected_operations.restore(snapshot)
                    selected_operations.restart()
                    restored_loaded = selected_operations.loaded_runtime()
                    restoration_verified = selected_operations.restoration_verified(
                        snapshot,
                        restored_loaded,
                    )
                except BaseException:
                    restoration_verified = False
                terminal_state = _best_effort_state_update(
                    state_path,
                    state,
                    state="failed",
                    stage="restored" if restoration_verified else "restore-unverified",
                    completed_at=_timestamp(),
                    restoration_attempted=True,
                    restoration_verified=restoration_verified,
                    error=error,
                )
            else:
                terminal_state = _best_effort_state_update(
                    state_path,
                    state,
                    state="failed",
                    stage="failed",
                    completed_at=_timestamp(),
                    error=error,
                )
            raise CoordinatorApplyError(
                error,
                _apply_failure_code(terminal_state),
                terminal_state,
            ) from exc


def recover_interrupted_transaction(
    operations: RecoverableApplyOperations,
    *,
    state_path: Path = DEFAULT_STATE_FILE,
    configuration_lock: Path = DEFAULT_LOCK,
    lifecycle_lock: Path = DEFAULT_LIFECYCLE_LOCK,
    update_lock: Path = DEFAULT_UPDATE_LOCK,
) -> Dict[str, Any]:
    """Restore a durable snapshot after a coordinator process interruption.

    Transactions interrupted before the snapshot completed are failed without
    restoration.  Once mutation may have started, recovery is conservative:
    reopen the root-owned snapshot, restore all generated files, reload/restart
    the daemon, and report whether the previous loaded runtime was verified.
    """

    state = read_state(state_path) if state_path.exists() else initial_state()
    recoverable_failed_restoration = bool(
        state.get("state") == "failed"
        and state.get("stage") == "restore-unverified"
        and state.get("restoration_attempted") is True
        and state.get("restoration_verified") is False
    )
    if state["state"] not in ACTIVE_STATES and not recoverable_failed_restoration:
        return state
    transaction_id = state.get("transaction_id")
    if not isinstance(transaction_id, str) or not _TRANSACTION_RE.fullmatch(transaction_id):
        raise CoordinatorError("Interrupted transaction identifier is invalid")
    error = (
        str(state.get("error") or "Vehicle configuration restoration requires recovery")
        if recoverable_failed_restoration
        else "Coordinator restarted during an active transaction"
    )
    if state["state"] == "validating":
        return _best_effort_state_update(
            state_path,
            state,
            state="failed",
            stage="recovery",
            completed_at=_timestamp(),
            error=error,
            recovered=True,
        )

    with ConfigurationTransactionLocks(configuration_lock, lifecycle_lock, update_lock):
        state = _best_effort_state_update(
            state_path,
            state,
            state="restoring",
            stage="restoring",
            restoration_attempted=True,
            error=error,
            recovered=True,
        )
        verified = False
        try:
            snapshot = operations.load_snapshot(transaction_id)
            operations.restore(snapshot)
            operations.restart()
            loaded = operations.loaded_runtime()
            verified = operations.restoration_verified(snapshot, loaded)
        except Exception:
            verified = False
        return _best_effort_state_update(
            state_path,
            state,
            state="failed",
            stage="restored" if verified else "restore-unverified",
            completed_at=_timestamp(),
            restoration_attempted=True,
            restoration_verified=verified,
            error=error,
            recovered=True,
        )


def _resolved_preview_context(
    roots: Optional[vehicle_setup.CatalogueRoots],
    dropin_path: Optional[Path],
    status_path: Optional[Path],
) -> tuple[vehicle_setup.CatalogueRoots, Path, Path]:
    if roots is None or dropin_path is None or status_path is None:
        configured_roots, configured_dropin, configured_status = _preview_context()
        roots = roots or configured_roots
        dropin_path = dropin_path or configured_dropin
        status_path = status_path or configured_status
    return roots, dropin_path, status_path


def validate_apply_interface(
    interface: str,
    *,
    sys_class_net: Path = Path("/sys/class/net"),
) -> None:
    """Require a physical SocketCAN target or an absent conventional ``canN``.

    The public apply protocol must not bypass the root-only vcan qualification
    gate. Present interfaces must be kernel SocketCAN devices. An absent target
    is accepted only with the conservative ``canN`` naming contract so a future
    non-CAN device cannot accidentally match the generated udev rule.
    """

    if not isinstance(interface, str) or not vehicle_configuration.INTERFACE_RE.fullmatch(
        interface
    ):
        raise CoordinatorError("Vehicle configuration interface is invalid")
    if _VCAN_INTERFACE_RE.fullmatch(interface):
        raise CoordinatorError("vcan targets require root-only qualification")
    type_path = sys_class_net / interface / "type"
    try:
        interface_type = type_path.read_text(encoding="ascii").strip()
    except FileNotFoundError:
        if not _ABSENT_CAN_INTERFACE_RE.fullmatch(interface):
            raise CoordinatorError(
                "Absent vehicle interfaces must use the conventional canN name"
            )
        return
    except (OSError, UnicodeError) as exc:
        raise CoordinatorError("Selected interface type cannot be inspected") from exc
    if interface_type != "280":
        raise CoordinatorError("Selected interface is not a SocketCAN device")


def production_apply_operations(_target: Mapping[str, Any]) -> ApplyOperations:
    """Construct the concrete fixed operation layer for one reviewed target."""

    return root_apply_operations(suppress_can_provisioning=False)


def _apply_failure_code(state: Optional[Mapping[str, Any]]) -> str:
    if isinstance(state, Mapping):
        if state.get("stage") == "restored" and state.get("restoration_verified") is True:
            return "apply-failed-restored"
        if state.get("stage") == "restore-unverified":
            return "apply-failed-restore-unverified"
    return "apply-failed"


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
    apply_operations_factory: Optional[ApplyOperationsFactory] = None,
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
                apply_enabled=apply_operations_factory is not None,
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
        if action == "apply":
            if apply_operations_factory is None:
                return {"ok": False, "error": "Coordinator action is not enabled"}
            if _restoration_required(read_state(state_path)):
                raise CoordinatorConflictError(
                    "Previous vehicle configuration restoration requires recovery",
                    "restoration-required",
                )
            if set(payload) != {"api_version", "action", "apply"}:
                return {"ok": False, "error": "Invalid coordinator request schema"}
            request, target, expected_revision = _normalize_apply_payload(
                payload.get("apply")
            )
            roots, dropin_path, status_path = _resolved_preview_context(
                preview_roots,
                preview_dropin_path,
                preview_status_path,
            )

            def validate_target(reviewed: Mapping[str, Any]) -> None:
                active_bus = reviewed["runtime"]["active_bus"]
                interface = reviewed["runtime"]["buses"][active_bus]["interface"]
                validate_no_conflicting_runtime_dropins(dropin_path)
                validate_apply_interface(
                    interface,
                    sys_class_net=preview_sys_class_net,
                )

            state = run_apply_transaction(
                request,
                reviewed_target=target,
                expected_configuration_revision=expected_revision,
                confirm=True,
                operations_factory=apply_operations_factory,
                pre_snapshot_validator=validate_target,
                state_path=state_path,
                roots=roots,
                dropin_path=dropin_path,
                status_path=status_path,
                sys_class_net=preview_sys_class_net,
                configuration_lock=configuration_lock,
                lifecycle_lock=lifecycle_lock,
                update_lock=update_lock,
            )
            return {
                "ok": True,
                "api_version": API_VERSION,
                "action": "apply",
                "state": state,
            }
        return {"ok": False, "error": "Coordinator action is not enabled"}
    except CoordinatorConflictError as exc:
        return {"ok": False, "code": exc.code, "error": str(exc)}
    except CoordinatorApplyError as exc:
        return {
            "ok": False,
            "code": exc.code,
            "error": str(exc),
            "state": exc.state,
        }
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
            response = response_for_request(
                payload,
                self.server.state_path,  # type: ignore[attr-defined]
                self.server.configuration_lock,  # type: ignore[attr-defined]
                self.server.lifecycle_lock,  # type: ignore[attr-defined]
                self.server.update_lock,  # type: ignore[attr-defined]
                preview_roots=self.server.preview_roots,  # type: ignore[attr-defined]
                preview_dropin_path=self.server.preview_dropin_path,  # type: ignore[attr-defined]
                preview_status_path=self.server.preview_status_path,  # type: ignore[attr-defined]
                preview_sys_class_net=self.server.preview_sys_class_net,  # type: ignore[attr-defined]
                apply_operations_factory=self.server.apply_operations_factory,  # type: ignore[attr-defined]
            )
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

    def __init__(
        self,
        socket_path: Path,
        state_path: Path,
        *,
        configuration_lock: Path = DEFAULT_LOCK,
        lifecycle_lock: Path = DEFAULT_LIFECYCLE_LOCK,
        update_lock: Path = DEFAULT_UPDATE_LOCK,
        preview_roots: Optional[vehicle_setup.CatalogueRoots] = None,
        preview_dropin_path: Optional[Path] = None,
        preview_status_path: Optional[Path] = None,
        preview_sys_class_net: Path = Path("/sys/class/net"),
        apply_operations_factory: Optional[ApplyOperationsFactory] = None,
    ):
        self.socket_path = socket_path
        self.state_path = state_path
        self.configuration_lock = configuration_lock
        self.lifecycle_lock = lifecycle_lock
        self.update_lock = update_lock
        self.preview_roots = preview_roots
        self.preview_dropin_path = preview_dropin_path
        self.preview_status_path = preview_status_path
        self.preview_sys_class_net = preview_sys_class_net
        self.apply_operations_factory = apply_operations_factory
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
        raise CoordinatorUnavailableError(
            "Vehicle configuration coordinator is unavailable"
        ) from exc
    if not isinstance(decoded, dict):
        raise CoordinatorError("Coordinator returned an invalid response")
    if decoded.get("ok") is not True:
        message = decoded.get("error")
        if not _bounded_text(message, MAX_ERROR_LENGTH, allow_empty=False):
            raise CoordinatorError("Coordinator returned an invalid error response")
        code = decoded.get("code")
        if code in {"busy", "stale-preview"}:
            raise CoordinatorConflictError(message, code)
        state = decoded.get("state")
        if state is not None:
            validated_state = _validate_state(state)
            if code not in {
                "apply-failed",
                "apply-failed-restored",
                "apply-failed-restore-unverified",
            }:
                raise CoordinatorError("Coordinator returned an invalid apply error")
            raise CoordinatorApplyError(message, code, validated_state)
        if code is not None:
            raise CoordinatorError("Coordinator returned an invalid error code")
        raise CoordinatorError(message)
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


def client_apply(
    apply: Mapping[str, Any],
    socket_path: Path = DEFAULT_SOCKET,
    *,
    timeout: float = DEFAULT_APPLY_TIMEOUT,
) -> Dict[str, Any]:
    """Submit one exact reviewed target to the fixed coordinator action."""

    _request, target, expected_revision = _normalize_apply_payload(apply)
    canonical_apply = {
        "target": target,
        "expected_configuration_revision": expected_revision,
        "target_configuration_revision": vehicle_configuration.selection_revision(
            target
        ),
        "confirm": True,
    }
    response = _client_request(
        {
            "api_version": API_VERSION,
            "action": "apply",
            "apply": canonical_apply,
        },
        socket_path,
        timeout,
    )
    if (
        response.get("api_version") != API_VERSION
        or response.get("action") != "apply"
        or set(response) != {"ok", "api_version", "action", "state"}
    ):
        raise CoordinatorError("Coordinator returned an invalid apply wrapper")
    state = _validate_state(response.get("state"))
    active_bus = target["runtime"]["active_bus"]
    expected_state_target = {
        "vehicle": target["vehicle"],
        "bindings": target["bindings"],
        "active_bus": active_bus,
        "interface": target["runtime"]["buses"][active_bus]["interface"],
    }
    if (
        state.get("state") != "complete"
        or state.get("stage") != "complete"
        or state.get("target") != expected_state_target
        or state.get("expected_configuration_revision") != expected_revision
        or state.get("restoration_attempted") is not False
        or state.get("restoration_verified") is not False
    ):
        raise CoordinatorError("Coordinator returned an invalid apply result")
    return {
        "ok": True,
        "api_version": API_VERSION,
        "action": "apply",
        "state": state,
    }


def _read_no_follow_file(
    path: Path,
    maximum_bytes: int,
    *,
    exact_mode: Optional[int] = None,
) -> bytes:
    """Read a trusted fixed file without following a final-component symlink."""

    expected_uid = 0 if path in {DEFAULT_COORDINATOR_ENV, DEFAULT_QUALIFICATION_GATE} else os.geteuid()
    expected_gid = 0 if path in {DEFAULT_COORDINATOR_ENV, DEFAULT_QUALIFICATION_GATE} else os.getegid()
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise CoordinatorError(f"Required coordinator file is unavailable: {path.name}") from exc
    try:
        metadata = os.fstat(descriptor)
        mode = stat.S_IMODE(metadata.st_mode)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != expected_uid
            or metadata.st_gid != expected_gid
            or metadata.st_nlink != 1
            or (exact_mode is not None and mode != exact_mode)
            or (exact_mode is None and mode & 0o022)
            or metadata.st_size > maximum_bytes
        ):
            raise CoordinatorError(f"Required coordinator file is untrusted: {path.name}")
        chunks = []
        remaining = maximum_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(remaining, 65536))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        if len(content) > maximum_bytes:
            raise CoordinatorError(f"Required coordinator file is too large: {path.name}")
        return content
    finally:
        os.close(descriptor)


def load_coordinator_environment(path: Path = DEFAULT_COORDINATOR_ENV) -> Dict[str, str]:
    """Load the root-owned fixed-path environment for direct root commands."""

    try:
        text = _read_no_follow_file(path, 16 * 1024).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CoordinatorError("Coordinator environment is not valid UTF-8") from exc
    values: Dict[str, str] = {}
    for line in text.splitlines():
        if not line or "=" not in line:
            raise CoordinatorError("Coordinator environment schema is invalid")
        key, encoded = line.split("=", 1)
        if key not in _COORDINATOR_ENV_KEYS or key in values:
            raise CoordinatorError("Coordinator environment schema is invalid")
        try:
            value = json.loads(encoded)
        except json.JSONDecodeError as exc:
            raise CoordinatorError("Coordinator environment schema is invalid") from exc
        if not isinstance(value, str):
            raise CoordinatorError("Coordinator environment schema is invalid")
        candidate = Path(value)
        if (
            not value
            or not candidate.is_absolute()
            or ".." in candidate.parts
            or any(ord(character) < 32 for character in value)
            or len(value) > MAX_CONFIGURED_PATH_LENGTH
        ):
            raise CoordinatorError("Coordinator environment path is invalid")
        values[key] = value
    if set(values) != _COORDINATOR_ENV_KEYS:
        raise CoordinatorError("Coordinator environment schema is invalid")
    os.environ.update(values)
    return values


def _service_account_from_runtime_dropin(dropin_path: Path) -> pwd.struct_passwd:
    """Resolve the fixed desktop service account from its owned drop-in directory."""

    try:
        directory = dropin_path.parent
        metadata = directory.lstat()
    except OSError as exc:
        raise CoordinatorError("Vehicle service account cannot be resolved") from exc
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_mode & 0o022
        or metadata.st_uid == 0
    ):
        raise CoordinatorError("Vehicle service account directory is untrusted")
    try:
        account = pwd.getpwuid(metadata.st_uid)
    except KeyError as exc:
        raise CoordinatorError("Vehicle service account cannot be resolved") from exc
    home = Path(account.pw_dir)
    try:
        dropin_path.relative_to(home)
    except ValueError as exc:
        raise CoordinatorError("Vehicle runtime drop-in is outside the service home") from exc
    return account


def root_apply_operations(*, suppress_can_provisioning: bool = False) -> QualificationApplyOperations:
    """Construct the fixed concrete operation layer from the trusted environment."""

    from ui import vehicle_config_apply

    roots, dropin_path, status_path = _preview_context()
    account = _service_account_from_runtime_dropin(dropin_path)
    return vehicle_config_apply.RootApplyOperations(
        roots=roots,
        paths=vehicle_config_apply.ApplyPaths(
            descriptor=vehicle_config_apply.DEFAULT_DESCRIPTOR_PATH,
            runtime_dropin=dropin_path,
            udev_rules=vehicle_config_apply.DEFAULT_UDEV_RULE_PATH,
            runtime_status=status_path,
            rollback_root=vehicle_config_apply.DEFAULT_ROLLBACK_ROOT,
        ),
        service_user=account.pw_name,
        service_uid=account.pw_uid,
        service_gid=account.pw_gid,
        service_home=Path(account.pw_dir),
        suppress_can_provisioning=suppress_can_provisioning,
    )


def run_can_provision() -> str:
    """Consume one root-owned request and provision the host CAN interface."""

    from ui import vehicle_config_apply

    roots, dropin_path, _status_path = _preview_context()
    account = _service_account_from_runtime_dropin(dropin_path)
    return vehicle_config_apply.provision_from_request(
        roots,
        service_uid=account.pw_uid,
    )


def _qualification_request(preview: object) -> tuple[Dict[str, Any], Dict[str, Any], str]:
    """Extract only the reviewed allowlisted target from a preview response."""

    if not isinstance(preview, dict) or (
        preview.get("api_version") != API_VERSION
        or preview.get("read_only") is not True
        or preview.get("apply_available") is not False
        or preview.get("state") != "ready"
    ):
        raise CoordinatorError("Qualification preview is invalid")
    try:
        target = vehicle_configuration.normalize_selection(preview.get("target"))
    except vehicle_configuration.VehicleConfigurationError as exc:
        raise CoordinatorError("Qualification preview target is invalid") from exc
    expected_revision = preview.get("expected_configuration_revision")
    target_revision = preview.get("target_configuration_revision")
    if (
        not isinstance(expected_revision, str)
        or not vehicle_configuration.REVISION_RE.fullmatch(expected_revision)
        or not isinstance(target_revision, str)
        or target_revision != vehicle_configuration.selection_revision(target)
    ):
        raise CoordinatorError("Qualification preview revisions are invalid")
    metadata = preview.get("coordinator")
    locks = metadata.get("locks") if isinstance(metadata, dict) else None
    if (
        not isinstance(metadata, dict)
        or metadata.get("previewed") is not True
        or metadata.get("read_only") is not True
        or metadata.get("apply_blocked") is not False
        or not isinstance(locks, dict)
        or set(locks) != {"configuration_active", "lifecycle_active", "update_active"}
        or any(value is not False for value in locks.values())
    ):
        raise CoordinatorError("Qualification preview is blocked")
    active_bus = target["runtime"]["active_bus"]
    interface = target["runtime"]["buses"][active_bus]["interface"]
    if not _VCAN_INTERFACE_RE.fullmatch(interface):
        raise CoordinatorError("Qualification target must use a vcan interface")
    request = {
        "vehicle": {
            "source": target["vehicle"]["source"],
            "id": target["vehicle"]["id"],
        },
        "bindings": {
            "source": target["bindings"]["source"],
            "id": target["bindings"]["id"],
        },
        "runtime": {
            "active_bus": active_bus,
            "buses": {active_bus: {"interface": interface}},
        },
    }
    return request, target, expected_revision


def validate_vcan_interface(
    interface: str,
    *,
    sys_class_net: Path = Path("/sys/class/net"),
) -> None:
    """Require an up kernel vcan device, not merely a caller-chosen name."""

    if not isinstance(interface, str) or not _VCAN_INTERFACE_RE.fullmatch(interface):
        raise CoordinatorError("Qualification target must use a vcan interface")
    entry = sys_class_net / interface
    virtual_root = sys_class_net.parent.parent / "devices" / "virtual" / "net"
    try:
        resolved = entry.resolve(strict=True)
        resolved_virtual_root = virtual_root.resolve(strict=True)
        interface_type = int((entry / "type").read_text(encoding="ascii").strip(), 10)
        flags = int((entry / "flags").read_text(encoding="ascii").strip(), 0)
    except (OSError, UnicodeError, ValueError) as exc:
        raise CoordinatorError("Qualification vcan interface is unavailable") from exc
    if (
        resolved.parent != resolved_virtual_root
        or resolved.name != interface
        or interface_type != 280
        or not flags & 0x1
    ):
        raise CoordinatorError("Qualification interface is not an up vcan device")


def validate_no_conflicting_runtime_dropins(managed_dropin: Path) -> None:
    """Reject additional drop-ins that can override the reviewed target."""

    directory = managed_dropin.parent
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        directory_fd = os.open(directory, flags)
    except OSError as exc:
        raise CoordinatorError("Runtime drop-in directory is unavailable") from exc
    try:
        metadata = os.fstat(directory_fd)
        if not stat.S_ISDIR(metadata.st_mode) or metadata.st_mode & 0o022:
            raise CoordinatorError("Runtime drop-in directory is untrusted")
        try:
            names = os.listdir(directory_fd)
        except OSError as exc:
            raise CoordinatorError("Runtime drop-in directory cannot be inspected") from exc
        for name in names:
            if name == managed_dropin.name or not name.endswith(".conf"):
                continue
            if not _DROPIN_NAME_RE.fullmatch(name):
                raise CoordinatorError("Additional runtime drop-in name is invalid")
            try:
                descriptor = os.open(
                    name,
                    os.O_RDONLY
                    | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=directory_fd,
                )
            except OSError as exc:
                raise CoordinatorError("Additional runtime drop-in is invalid") from exc
            try:
                item = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(item.st_mode)
                    or item.st_uid != metadata.st_uid
                    or item.st_gid != metadata.st_gid
                    or item.st_nlink != 1
                    or item.st_mode & 0o022
                    or item.st_size > 64 * 1024
                ):
                    raise CoordinatorError("Additional runtime drop-in is untrusted")
                chunks = []
                remaining = 64 * 1024 + 1
                while remaining:
                    chunk = os.read(descriptor, min(remaining, 65536))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining -= len(chunk)
                content = b"".join(chunks)
                if len(content) > 64 * 1024:
                    raise CoordinatorError("Additional runtime drop-in is too large")
                try:
                    text = content.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise CoordinatorError("Additional runtime drop-in is invalid") from exc
            finally:
                os.close(descriptor)
            for line in text.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if (
                    (
                        stripped.startswith("Environment=")
                        or stripped.startswith("UnsetEnvironment=")
                    )
                    and any(key in stripped for key in _MANAGED_RUNTIME_KEYS)
                ):
                    raise CoordinatorError(
                        f"Conflicting canbusd runtime drop-in: {name}"
                    )
    finally:
        os.close(directory_fd)


def consume_qualification_gate(path: Path = DEFAULT_QUALIFICATION_GATE) -> None:
    """Consume the one-shot root-owned qualification consent marker."""

    expected_uid = 0 if path == DEFAULT_QUALIFICATION_GATE else os.geteuid()
    expected_gid = 0 if path == DEFAULT_QUALIFICATION_GATE else os.getegid()
    try:
        parent = path.parent.lstat()
    except OSError as exc:
        raise CoordinatorError("Qualification gate directory is unavailable") from exc
    if (
        not stat.S_ISDIR(parent.st_mode)
        or parent.st_uid != expected_uid
        or parent.st_gid != expected_gid
        or parent.st_mode & 0o022
    ):
        raise CoordinatorError("Qualification gate directory is untrusted")
    content = _read_no_follow_file(
        path,
        len(QUALIFICATION_GATE_CONTENT),
        exact_mode=0o600,
    )
    if content != QUALIFICATION_GATE_CONTENT:
        raise CoordinatorError("Qualification gate content is invalid")
    try:
        path.unlink()
        descriptor = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise CoordinatorError("Qualification gate could not be consumed") from exc


def read_qualification_preview(stream: Any = None) -> Dict[str, Any]:
    """Read one bounded strict preview object from standard input."""

    source = stream if stream is not None else sys.stdin.buffer
    raw = source.read(MAX_QUALIFICATION_PREVIEW_BYTES + 1)
    if not raw or len(raw) > MAX_QUALIFICATION_PREVIEW_BYTES:
        raise CoordinatorError("Qualification preview size is invalid")
    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeError, json.JSONDecodeError, CoordinatorError) as exc:
        raise CoordinatorError("Qualification preview JSON is invalid") from exc
    if not isinstance(payload, dict):
        raise CoordinatorError("Qualification preview is invalid")
    return payload


def run_vcan_qualification(
    preview: Mapping[str, Any],
    *,
    operations: Optional[QualificationApplyOperations] = None,
    gate_path: Path = DEFAULT_QUALIFICATION_GATE,
    state_path: Path = DEFAULT_STATE_FILE,
    roots: Optional[vehicle_setup.CatalogueRoots] = None,
    dropin_path: Optional[Path] = None,
    status_path: Optional[Path] = None,
    sys_class_net: Path = Path("/sys/class/net"),
    configuration_lock: Path = DEFAULT_LOCK,
    lifecycle_lock: Path = DEFAULT_LIFECYCLE_LOCK,
    update_lock: Path = DEFAULT_UPDATE_LOCK,
) -> Dict[str, Any]:
    """Apply a reviewed vcan target and restore the previous setup under one lock."""

    request, target, expected_revision = _qualification_request(preview)
    active_bus = target["runtime"]["active_bus"]
    interface = target["runtime"]["buses"][active_bus]["interface"]
    validate_vcan_interface(interface, sys_class_net=sys_class_net)
    if dropin_path is None:
        _roots, dropin_path, _status = _preview_context()
    validate_no_conflicting_runtime_dropins(dropin_path)
    consume_qualification_gate(gate_path)
    selected_operations = operations or root_apply_operations(
        suppress_can_provisioning=True
    )
    return run_apply_transaction(
        request,
        reviewed_target=target,
        expected_configuration_revision=expected_revision,
        confirm=True,
        operations=selected_operations,
        state_path=state_path,
        roots=roots,
        dropin_path=dropin_path,
        status_path=status_path,
        sys_class_net=sys_class_net,
        configuration_lock=configuration_lock,
        lifecycle_lock=lifecycle_lock,
        update_lock=update_lock,
        qualification_restore_on_success=True,
    )


def _interrupted_vcan_qualification(state: Mapping[str, Any]) -> bool:
    target = state.get("target")
    return bool(
        state.get("state") in ACTIVE_STATES
        and isinstance(target, Mapping)
        and isinstance(target.get("interface"), str)
        and _VCAN_INTERFACE_RE.fullmatch(target["interface"])
    )


def _interrupt_qualification(_signum: int, _frame: object) -> None:
    raise KeyboardInterrupt()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Open MMI vehicle configuration coordinator")
    parser.add_argument(
        "command", choices=("serve", "status", "qualify-vcan", "provision-can")
    )
    args = parser.parse_args(argv)
    if args.command == "status":
        print(json.dumps(client_status(), indent=2, sort_keys=True))
        return 0
    if os.geteuid() != 0:
        raise SystemExit(
            f"open-mmi-vehicle-config-coordinator: {args.command} requires root"
        )
    try:
        load_coordinator_environment()
        if args.command == "provision-can":
            run_can_provision()
            return 0
        persisted = read_state(DEFAULT_STATE_FILE)
        if args.command == "qualify-vcan":
            operations = root_apply_operations(suppress_can_provisioning=True)
            previous_sigterm = signal.signal(
                signal.SIGTERM,
                _interrupt_qualification,
            )
            try:
                state = run_vcan_qualification(
                    read_qualification_preview(),
                    operations=operations,
                )
            finally:
                signal.signal(signal.SIGTERM, previous_sigterm)
            print(json.dumps(state, indent=2, sort_keys=True))
            return 0
        if persisted["state"] in ACTIVE_STATES or (
            persisted.get("state") == "failed"
            and persisted.get("stage") == "restore-unverified"
            and persisted.get("restoration_attempted") is True
            and persisted.get("restoration_verified") is False
        ):
            operations = root_apply_operations(
                suppress_can_provisioning=_interrupted_vcan_qualification(
                    persisted
                )
            )
            recover_interrupted_transaction(operations)
    except CoordinatorError as exc:
        print(f"open-mmi-vehicle-config-coordinator: {exc}", file=sys.stderr)
        return 1
    with CoordinatorServer(
        DEFAULT_SOCKET,
        DEFAULT_STATE_FILE,
        apply_operations_factory=production_apply_operations,
    ) as server:
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
