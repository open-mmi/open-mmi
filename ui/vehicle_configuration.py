"""Pure canonical vehicle-configuration schema helpers.

This module deliberately performs no system mutation.  The dashboard preview,
CLI, and later privileged coordinator share these exact normalized structures
so the browser never supplies paths, generated files, commands, or service
names.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import stat
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence


SCHEMA_VERSION = 1
MAX_DESCRIPTOR_BYTES = 64 * 1024
DEFAULT_DESCRIPTOR_PATH = Path("/etc/open-mmi/vehicle-configuration.json")

IDENTIFIER_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
INTERFACE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,14}$")
REVISION_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SOURCES = {"maintained", "custom"}


class VehicleConfigurationError(ValueError):
    """Raised when a canonical selection or descriptor fails closed."""


def _object(
    value: Any,
    *,
    path: str,
    required: set[str],
    optional: Optional[set[str]] = None,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise VehicleConfigurationError(f"{path} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise VehicleConfigurationError(f"{path} contains an invalid field name")
    allowed = required | (optional or set())
    unknown = sorted(set(value) - allowed)
    missing = sorted(required - set(value))
    if unknown:
        raise VehicleConfigurationError(
            f"{path} contains unsupported fields: {', '.join(unknown)}"
        )
    if missing:
        raise VehicleConfigurationError(
            f"{path} is missing required fields: {', '.join(missing)}"
        )
    return value


def _identity(value: Any, *, path: str) -> dict[str, str]:
    item = _object(
        value,
        path=path,
        required={"source", "id", "revision"},
    )
    source = item["source"]
    identifier = item["id"]
    revision = item["revision"]
    if not isinstance(source, str) or source not in SOURCES:
        raise VehicleConfigurationError(
            f"{path}.source must be maintained or custom"
        )
    if not isinstance(identifier, str) or not IDENTIFIER_RE.fullmatch(identifier):
        raise VehicleConfigurationError(f"{path}.id is invalid")
    if not isinstance(revision, str) or not REVISION_RE.fullmatch(revision):
        raise VehicleConfigurationError(f"{path}.revision is invalid")
    return {"source": source, "id": identifier, "revision": revision}


def normalize_selection(value: Any) -> dict[str, Any]:
    """Validate and normalize one single-input configuration selection."""

    selection = _object(
        value,
        path="configuration",
        required={"vehicle", "bindings", "runtime"},
    )
    runtime = _object(
        selection["runtime"],
        path="configuration.runtime",
        required={"mode", "active_bus", "buses"},
    )
    if runtime["mode"] != "single":
        raise VehicleConfigurationError(
            "configuration.runtime.mode must be single"
        )
    active_bus = runtime["active_bus"]
    if not isinstance(active_bus, str) or not IDENTIFIER_RE.fullmatch(active_bus):
        raise VehicleConfigurationError(
            "configuration.runtime.active_bus is invalid"
        )
    buses = _object(
        runtime["buses"],
        path="configuration.runtime.buses",
        required={active_bus},
    )
    if len(buses) != 1:
        raise VehicleConfigurationError(
            "configuration.runtime.buses must contain exactly the active bus"
        )
    assignment = _object(
        buses[active_bus],
        path=f"configuration.runtime.buses.{active_bus}",
        required={"interface"},
    )
    interface = assignment["interface"]
    if not isinstance(interface, str) or not INTERFACE_RE.fullmatch(interface):
        raise VehicleConfigurationError(
            f"configuration.runtime.buses.{active_bus}.interface is invalid"
        )
    return {
        "vehicle": _identity(selection["vehicle"], path="configuration.vehicle"),
        "bindings": _identity(
            selection["bindings"], path="configuration.bindings"
        ),
        "runtime": {
            "mode": "single",
            "active_bus": active_bus,
            "buses": {active_bus: {"interface": interface}},
        },
    }


def selection_revision(value: Any) -> str:
    normalized = normalize_selection(value)
    content = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(content).hexdigest()


def descriptor_for_selection(value: Any, *, applied_at: str) -> dict[str, Any]:
    normalized = normalize_selection(value)
    _validate_timestamp(applied_at)
    return {
        "schema_version": SCHEMA_VERSION,
        **normalized,
        "applied_at": applied_at,
    }


def _validate_timestamp(value: Any) -> None:
    if not isinstance(value, str) or not value:
        raise VehicleConfigurationError("configuration.applied_at is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise VehicleConfigurationError(
            "configuration.applied_at is invalid"
        ) from exc
    if parsed.tzinfo is None:
        raise VehicleConfigurationError(
            "configuration.applied_at must include a timezone"
        )


def validate_descriptor(value: Any) -> dict[str, Any]:
    descriptor = _object(
        value,
        path="configuration",
        required={
            "schema_version",
            "vehicle",
            "bindings",
            "runtime",
            "applied_at",
        },
    )
    if (
        isinstance(descriptor["schema_version"], bool)
        or descriptor["schema_version"] != SCHEMA_VERSION
    ):
        raise VehicleConfigurationError(
            "configuration.schema_version is unsupported"
        )
    _validate_timestamp(descriptor["applied_at"])
    normalized = normalize_selection(
        {
            "vehicle": descriptor["vehicle"],
            "bindings": descriptor["bindings"],
            "runtime": descriptor["runtime"],
        }
    )
    return {
        "schema_version": SCHEMA_VERSION,
        **normalized,
        "applied_at": descriptor["applied_at"],
    }


def _unique_json_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise VehicleConfigurationError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _reject_json_constant(value: str) -> None:
    raise VehicleConfigurationError(f"non-finite JSON number: {value}")


def load_descriptor(
    path: Path = DEFAULT_DESCRIPTOR_PATH,
    *,
    expected_uid: int = 0,
) -> Optional[dict[str, Any]]:
    """Read a root-owned descriptor without following a symlink.

    A missing descriptor is the expected migration state until the privileged
    coordinator first applies a canonical configuration.
    """

    flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor_fd = os.open(path, flags)
    except FileNotFoundError:
        return None
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise VehicleConfigurationError(
                "canonical configuration must be a regular file"
            ) from exc
        raise VehicleConfigurationError(
            "canonical configuration cannot be inspected"
        ) from exc
    try:
        metadata = os.fstat(descriptor_fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise VehicleConfigurationError(
                "canonical configuration must be a regular file"
            )
        if metadata.st_uid != expected_uid:
            raise VehicleConfigurationError(
                "canonical configuration has an untrusted owner"
            )
        if stat.S_IMODE(metadata.st_mode) & 0o022:
            raise VehicleConfigurationError(
                "canonical configuration must not be group or world writable"
            )
        if metadata.st_size > MAX_DESCRIPTOR_BYTES:
            raise VehicleConfigurationError(
                "canonical configuration exceeds the size limit"
            )
        with os.fdopen(descriptor_fd, "rb", closefd=True) as handle:
            descriptor_fd = -1
            content = handle.read(MAX_DESCRIPTOR_BYTES + 1)
        if len(content) > MAX_DESCRIPTOR_BYTES:
            raise VehicleConfigurationError(
                "canonical configuration exceeds the size limit"
            )
    except OSError as exc:
        raise VehicleConfigurationError(
            "canonical configuration cannot be read"
        ) from exc
    finally:
        if descriptor_fd >= 0:
            os.close(descriptor_fd)
    try:
        document = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VehicleConfigurationError(
            "canonical configuration is not valid UTF-8 JSON"
        ) from exc
    return validate_descriptor(document)
