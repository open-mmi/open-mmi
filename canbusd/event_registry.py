"""Canonical Open MMI vehicle-event registry shared by runtime and setup.

Vehicle profiles translate vehicle-specific signals into these event identifiers.
Bindings translate the same identifiers into application behavior.  Neither side
may invent a private synonym for an existing universal intent.
"""

from __future__ import annotations

import copy
import json
import re
import stat
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence


SCHEMA_VERSION = 1
REGISTRY_ID = "open-mmi.vehicle-events"
MAX_REGISTRY_BYTES = 256 * 1024
DEFAULT_REGISTRY_PATH = Path(__file__).with_name("data") / "vehicle-events.v1.json"
EVENT_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*(?:[.:][a-z][a-z0-9_]*)*$")
CATEGORIES = {"display", "media", "navigation", "vehicle"}
DELIVERY_MODES = {"edge", "repeatable", "state_transition", "value"}
EVENT_STATUSES = {"stable", "deprecated"}


class VehicleEventRegistryError(ValueError):
    """Raised when the bundled event registry or an event lookup is invalid."""


def _object(
    value: Any,
    *,
    path: str,
    required: set[str],
    optional: Optional[set[str]] = None,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise VehicleEventRegistryError(f"{path} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise VehicleEventRegistryError(f"{path} contains an invalid field name")
    allowed = required | (optional or set())
    unknown = sorted(set(value) - allowed)
    missing = sorted(required - set(value))
    if unknown:
        raise VehicleEventRegistryError(
            f"{path} contains unsupported fields: {', '.join(unknown)}"
        )
    if missing:
        raise VehicleEventRegistryError(
            f"{path} is missing required fields: {', '.join(missing)}"
        )
    return value




def _named_mapping(value: Any, *, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise VehicleEventRegistryError(f"{path} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise VehicleEventRegistryError(f"{path} contains an invalid field name")
    return value


def _bounded_text(value: Any, *, path: str, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > maximum
        or any(ord(character) < 32 for character in value)
    ):
        raise VehicleEventRegistryError(f"{path} must be bounded text")
    return value


def _payload(value: Any, *, path: str) -> dict[str, Any]:
    payload = _object(
        value,
        path=path,
        required={"type"},
        optional={"minimum", "maximum", "unit"},
    )
    payload_type = payload["type"]
    if payload_type == "none":
        if set(payload) != {"type"}:
            raise VehicleEventRegistryError(
                f"{path} none payload must not declare bounds or units"
            )
        return {"type": "none"}
    if payload_type != "integer":
        raise VehicleEventRegistryError(f"{path}.type is unsupported")
    if set(payload) != {"type", "minimum", "maximum", "unit"}:
        raise VehicleEventRegistryError(
            f"{path} integer payload requires minimum, maximum and unit"
        )
    minimum = payload["minimum"]
    maximum = payload["maximum"]
    if (
        isinstance(minimum, bool)
        or isinstance(maximum, bool)
        or not isinstance(minimum, int)
        or not isinstance(maximum, int)
        or minimum > maximum
    ):
        raise VehicleEventRegistryError(f"{path} integer bounds are invalid")
    return {
        "type": "integer",
        "minimum": minimum,
        "maximum": maximum,
        "unit": _bounded_text(payload["unit"], path=f"{path}.unit", maximum=32),
    }


def normalize_registry(value: Any) -> dict[str, Any]:
    registry = _object(
        value,
        path="registry",
        required={"schema_version", "registry_id", "events", "aliases"},
    )
    if registry["schema_version"] != SCHEMA_VERSION or isinstance(
        registry["schema_version"], bool
    ):
        raise VehicleEventRegistryError("registry.schema_version is unsupported")
    if registry["registry_id"] != REGISTRY_ID:
        raise VehicleEventRegistryError("registry.registry_id is unsupported")

    raw_events = _named_mapping(
        registry["events"],
        path="registry.events",
    )
    if not raw_events:
        raise VehicleEventRegistryError("registry.events must not be empty")

    events: dict[str, dict[str, Any]] = {}
    for name in sorted(raw_events):
        if not EVENT_NAME_RE.fullmatch(name):
            raise VehicleEventRegistryError(f"registry.events.{name} has an invalid name")
        entry = _object(
            raw_events[name],
            path=f"registry.events.{name}",
            required={
                "title",
                "category",
                "description",
                "payload",
                "delivery",
                "status",
            },
        )
        category = entry["category"]
        delivery = entry["delivery"]
        status = entry["status"]
        if category not in CATEGORIES:
            raise VehicleEventRegistryError(
                f"registry.events.{name}.category is unsupported"
            )
        if delivery not in DELIVERY_MODES:
            raise VehicleEventRegistryError(
                f"registry.events.{name}.delivery is unsupported"
            )
        if status not in EVENT_STATUSES:
            raise VehicleEventRegistryError(
                f"registry.events.{name}.status is unsupported"
            )
        events[name] = {
            "title": _bounded_text(
                entry["title"], path=f"registry.events.{name}.title", maximum=80
            ),
            "category": category,
            "description": _bounded_text(
                entry["description"],
                path=f"registry.events.{name}.description",
                maximum=512,
            ),
            "payload": _payload(
                entry["payload"], path=f"registry.events.{name}.payload"
            ),
            "delivery": delivery,
            "status": status,
        }

    raw_aliases = _named_mapping(
        registry["aliases"],
        path="registry.aliases",
    )
    aliases: dict[str, dict[str, str]] = {}
    for alias in sorted(raw_aliases):
        if not EVENT_NAME_RE.fullmatch(alias):
            raise VehicleEventRegistryError(f"registry.aliases.{alias} has an invalid name")
        if alias in events:
            raise VehicleEventRegistryError(
                f"registry.aliases.{alias} conflicts with a canonical event"
            )
        entry = _object(
            raw_aliases[alias],
            path=f"registry.aliases.{alias}",
            required={"event", "description", "status"},
        )
        canonical = entry["event"]
        if canonical not in events:
            raise VehicleEventRegistryError(
                f"registry.aliases.{alias}.event is not canonical"
            )
        if entry["status"] != "deprecated":
            raise VehicleEventRegistryError(
                f"registry.aliases.{alias}.status must be deprecated"
            )
        aliases[alias] = {
            "event": canonical,
            "description": _bounded_text(
                entry["description"],
                path=f"registry.aliases.{alias}.description",
                maximum=512,
            ),
            "status": "deprecated",
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "registry_id": REGISTRY_ID,
        "events": events,
        "aliases": aliases,
    }


def _unique_json_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise VehicleEventRegistryError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _reject_json_constant(value: str) -> None:
    raise VehicleEventRegistryError(f"non-finite JSON number: {value}")


def load_registry(path: Path = DEFAULT_REGISTRY_PATH) -> dict[str, Any]:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise VehicleEventRegistryError(
            "vehicle event registry cannot be inspected"
        ) from exc
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_REGISTRY_BYTES:
        raise VehicleEventRegistryError(
            "vehicle event registry must be a bounded regular file"
        )
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise VehicleEventRegistryError(
            "vehicle event registry cannot be read"
        ) from exc
    if len(content) > MAX_REGISTRY_BYTES:
        raise VehicleEventRegistryError("vehicle event registry exceeds the size limit")
    try:
        document = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VehicleEventRegistryError(
            "vehicle event registry is not valid UTF-8 JSON"
        ) from exc
    return normalize_registry(document)


@lru_cache(maxsize=1)
def _default_registry() -> dict[str, Any]:
    return load_registry(DEFAULT_REGISTRY_PATH)


def registry_payload() -> dict[str, Any]:
    """Return a defensive copy of the canonical bundled registry."""

    return copy.deepcopy(_default_registry())


def _event_status(
    name: Any,
    registry: Mapping[str, Any],
) -> tuple[str, Optional[str]]:
    if not isinstance(name, str) or not EVENT_NAME_RE.fullmatch(name):
        return "invalid", None
    if name in registry["events"]:
        return "canonical", name
    alias = registry["aliases"].get(name)
    if alias:
        return "alias", alias["event"]
    return "unknown", None


def event_status(
    name: Any,
    registry: Optional[Mapping[str, Any]] = None,
) -> tuple[str, Optional[str]]:
    """Classify an event name as canonical, deprecated alias, or unknown."""

    selected = (
        normalize_registry(registry)
        if registry is not None
        else _default_registry()
    )
    return _event_status(name, selected)


def require_event(
    name: Any,
    *,
    carries_payload: Optional[bool] = None,
    registry: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Return a canonical definition or raise a precise conformance error."""

    selected = (
        normalize_registry(registry)
        if registry is not None
        else _default_registry()
    )
    status, canonical = _event_status(name, selected)
    if status == "invalid":
        raise VehicleEventRegistryError("event name is invalid")
    if status == "alias" and canonical is not None:
        raise VehicleEventRegistryError(
            f"event alias {name!r} is deprecated; use {canonical!r}"
        )
    if status == "unknown" or canonical is None:
        raise VehicleEventRegistryError(f"event is not registered: {name}")
    definition = selected["events"][canonical]
    if carries_payload is not None:
        expects_payload = definition["payload"]["type"] != "none"
        if carries_payload and not expects_payload:
            raise VehicleEventRegistryError(
                f"event {canonical!r} does not accept a payload"
            )
        if expects_payload and not carries_payload:
            raise VehicleEventRegistryError(
                f"event {canonical!r} requires a payload"
            )
    return copy.deepcopy(definition)


def event_definition(name: str) -> dict[str, Any]:
    selected = _default_registry()
    status, canonical = _event_status(name, selected)
    if status == "invalid":
        raise VehicleEventRegistryError("event name is invalid")
    if status == "unknown" or canonical is None:
        raise VehicleEventRegistryError(f"event is not registered: {name}")
    return {
        "event": canonical,
        "requested_event": name,
        "requested_status": status,
        **copy.deepcopy(selected["events"][canonical]),
    }
