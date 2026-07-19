"""Read-only vehicle setup discovery, validation and runtime status.

The browser, CLI and the later privileged configuration coordinator share this
module.  Every catalogue lookup resolves a source class and identifier beneath a
fixed root; callers never supply a filesystem path.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shlex
import stat
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from canbusd.can_runtime import resolve_can_runtime


API_VERSION = 1
DEFAULT_BUS = "comfort"
DEFAULT_INTERFACE = "can0"
MAX_PROFILE_BYTES = 1024 * 1024
MAX_BINDINGS_BYTES = 256 * 1024
MAX_CAN_ID = 0x1FFFFFFF
MAX_EVENT_LENGTH = 128
MAX_STATUS_PATH_LENGTH = 192

IDENTIFIER_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
PYTHON_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
INTERFACE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,14}$")
STATUS_TYPES = {
    "raw",
    "percent",
    "scaled",
    "bool",
    "enum",
    "bitfield",
    "signed_magnitude",
    "steering_angle",
    "u16le",
    "u24le",
    "u32le",
    "uint_le",
}
PROVISIONING_MODES = {"manual", "udev"}
RUNTIME_ENVIRONMENT_KEYS = {
    "OPEN_MMI_VEHICLE",
    "OPEN_MMI_BINDINGS",
    "OPEN_MMI_VEHICLE_CONFIG",
    "OPEN_MMI_BINDINGS_FILE",
    "OPEN_MMI_CAN_BUS",
    "OPEN_MMI_CAN_INTERFACE",
}


class VehicleSetupError(RuntimeError):
    """A fail-closed vehicle setup inspection error."""


@dataclass(frozen=True)
class CatalogueRoots:
    """Trusted roots for maintained and user-owned catalogue content."""

    maintained: Path
    custom: Path
    development_mode: bool = False


def default_roots(environment: Optional[Mapping[str, str]] = None) -> CatalogueRoots:
    env = dict(os.environ if environment is None else environment)
    development_root = str(
        env.get("OPEN_MMI_VEHICLE_SETUP_DEVELOPMENT_ROOT") or ""
    ).strip()
    installed_root = str(env.get("OPEN_MMI_INSTALL_DIR") or "/opt/open-mmi")
    config_root = str(
        env.get("OPEN_MMI_CONFIG_DIR")
        or Path(env.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "open-mmi"
    )
    return CatalogueRoots(
        maintained=Path(development_root or installed_root).expanduser(),
        custom=Path(config_root).expanduser(),
        development_mode=bool(development_root),
    )


def _issue(level: str, code: str, path: str, message: str) -> dict[str, str]:
    return {"level": level, "code": code, "path": path, "message": message}


def _validation(issues: Iterable[Mapping[str, str]]) -> dict[str, Any]:
    ordered = [dict(issue) for issue in issues]
    errors = [issue for issue in ordered if issue["level"] == "error"]
    warnings = [issue for issue in ordered if issue["level"] == "warning"]
    return {"valid": not errors, "errors": errors, "warnings": warnings}


def validate_identifier(value: Any, *, path: str = "id") -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    if not isinstance(value, str) or not IDENTIFIER_RE.fullmatch(value):
        issues.append(
            _issue(
                "error",
                "invalid-identifier",
                path,
                "must match ^[a-z0-9][a-z0-9_-]{0,63}$",
            )
        )
    return _validation(issues)


def _catalogue_path(
    roots: CatalogueRoots,
    kind: str,
    source: str,
    identifier: str,
) -> tuple[Path, Path]:
    identifier_validation = validate_identifier(identifier)
    if not identifier_validation["valid"]:
        raise VehicleSetupError("Invalid catalogue identifier")
    if source == "maintained":
        root = roots.maintained
    elif source == "custom":
        root = roots.custom
    else:
        raise VehicleSetupError("Catalogue source must be maintained or custom")

    if kind == "profile":
        return root, root / "vehicles" / identifier / "config.json"
    if kind == "bindings":
        return root, root / "bindings" / f"{identifier}.json"
    raise VehicleSetupError("Catalogue kind must be profile or bindings")


def _reject_symlink_components(root: Path, target: Path) -> None:
    try:
        relative = target.relative_to(root)
    except ValueError as exc:
        raise VehicleSetupError("Catalogue path escapes its fixed root") from exc

    current = root
    components = [root, *(root / Path(*relative.parts[:index]) for index in range(1, len(relative.parts) + 1))]
    for current in components:
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise VehicleSetupError("Catalogue path cannot be inspected") from exc
        if stat.S_ISLNK(mode):
            raise VehicleSetupError("Symlinked catalogue paths are not trusted")


def resolve_catalogue_path(
    roots: CatalogueRoots,
    kind: str,
    source: str,
    identifier: str,
) -> Path:
    """Resolve one identity beneath a fixed root without following symlinks."""

    root, target = _catalogue_path(roots, kind, source, identifier)
    _reject_symlink_components(root, target)
    return target


def _parse_int(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("boolean is not an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        return int(text, 16) if text.lower().startswith("0x") else int(text)
    raise ValueError("value is not an integer")


def _bounded_text(value: Any, *, maximum: int) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= maximum
        and not any(ord(character) < 32 for character in value)
    )


def _validate_can_id(
    value: Any,
    path: str,
    issues: list[dict[str, str]],
) -> None:
    try:
        parsed = _parse_int(value)
    except (TypeError, ValueError):
        parsed = -1
    if not 0 <= parsed <= MAX_CAN_ID:
        issues.append(
            _issue("error", "invalid-can-id", path, "must be a CAN identifier from 0 to 0x1FFFFFFF")
        )


def _validate_byte(
    value: Any,
    path: str,
    issues: list[dict[str, str]],
) -> None:
    try:
        parsed = _parse_int(value)
    except (TypeError, ValueError):
        parsed = -1
    if not 0 <= parsed <= 7:
        issues.append(_issue("error", "invalid-byte-index", path, "must be an integer from 0 to 7"))


def _validate_bus_reference(
    value: Any,
    path: str,
    declared: set[str],
    issues: list[dict[str, str]],
) -> None:
    values: Sequence[Any]
    if isinstance(value, list):
        values = value
    else:
        values = [value]
    if not values or any(not isinstance(item, str) for item in values):
        issues.append(_issue("error", "invalid-bus-reference", path, "must name one bus or a list of buses"))
        return
    for item in values:
        if item not in declared:
            issues.append(_issue("error", "undeclared-bus", path, f"references undeclared bus {item!r}"))


def _validate_profile_item(
    item: Any,
    path: str,
    kind: str,
    default_bus: str,
    declared_buses: set[str],
    issues: list[dict[str, str]],
) -> None:
    if not isinstance(item, Mapping):
        issues.append(_issue("error", "invalid-rule", path, "must be an object"))
        return
    if "id" not in item:
        issues.append(_issue("error", "missing-can-id", f"{path}.id", "is required"))
    else:
        _validate_can_id(item["id"], f"{path}.id", issues)

    if "bus" in item:
        _validate_bus_reference(item["bus"], f"{path}.bus", declared_buses, issues)
    elif default_bus not in declared_buses:
        issues.append(_issue("error", "undeclared-default-bus", f"{path}.bus", "implicit default bus is not declared"))

    if kind == "rule":
        _validate_byte(item.get("byte", 0), f"{path}.byte", issues)
        if not _bounded_text(item.get("event"), maximum=MAX_EVENT_LENGTH):
            issues.append(_issue("error", "invalid-event", f"{path}.event", "must be a non-empty bounded string"))
        value = item.get("value")
        if not (isinstance(value, str) and value.lower() == "any"):
            try:
                parsed = _parse_int(value)
            except (TypeError, ValueError):
                parsed = -1
            if not 0 <= parsed <= 255:
                issues.append(_issue("error", "invalid-rule-value", f"{path}.value", "must be 0..255 or 'any'"))
        return

    if kind == "presence":
        try:
            timeout = _parse_int(item.get("timeout_ms", 1000))
        except (TypeError, ValueError):
            timeout = 0
        if not 1 <= timeout <= 86_400_000:
            issues.append(_issue("error", "invalid-timeout", f"{path}.timeout_ms", "must be between 1 and 86400000"))
        for key in ("on_present", "on_absent"):
            if key in item and item[key] is not None and not _bounded_text(item[key], maximum=MAX_EVENT_LENGTH):
                issues.append(_issue("error", "invalid-event", f"{path}.{key}", "must be a bounded string"))
        status_path = item.get("status_path", "vehicle.present")
        if not _bounded_text(status_path, maximum=MAX_STATUS_PATH_LENGTH):
            issues.append(_issue("error", "invalid-status-path", f"{path}.status_path", "must be a bounded string"))
        return

    rule_type = item.get("type", "raw")
    if rule_type not in STATUS_TYPES:
        issues.append(_issue("error", "unsupported-status-type", f"{path}.type", "is not a supported status decoder"))
    if not _bounded_text(item.get("path"), maximum=MAX_STATUS_PATH_LENGTH):
        issues.append(_issue("error", "invalid-status-path", f"{path}.path", "must be a non-empty bounded string"))

    if "byte" in item:
        _validate_byte(item["byte"], f"{path}.byte", issues)
    if "start_byte" in item:
        _validate_byte(item["start_byte"], f"{path}.start_byte", issues)
    if "bytes" in item:
        if not isinstance(item["bytes"], list) or not item["bytes"]:
            issues.append(_issue("error", "invalid-byte-list", f"{path}.bytes", "must be a non-empty list"))
        else:
            for index, value in enumerate(item["bytes"]):
                _validate_byte(value, f"{path}.bytes[{index}]", issues)
    if rule_type == "bool" and "true" not in item:
        issues.append(_issue("error", "missing-true-value", f"{path}.true", "is required for bool rules"))
    elif rule_type == "bool":
        for key in ("true", "false", "mask"):
            if key not in item:
                continue
            try:
                parsed = _parse_int(item[key])
            except (TypeError, ValueError):
                parsed = -1
            if not 0 <= parsed <= 255:
                issues.append(_issue("error", "invalid-status-value", f"{path}.{key}", "must be between 0 and 255"))
    if rule_type == "enum":
        values = item.get("values")
        if not isinstance(values, Mapping) or not values:
            issues.append(_issue("error", "invalid-enum-values", f"{path}.values", "must be a non-empty object"))
        else:
            for key in values:
                try:
                    parsed = _parse_int(key)
                except (TypeError, ValueError):
                    parsed = -1
                if not 0 <= parsed <= 255:
                    issues.append(_issue("error", "invalid-enum-key", f"{path}.values.{key}", "must be between 0 and 255"))
    if rule_type == "bitfield":
        fields_present = False
        for key in ("fields", "equals"):
            values = item.get(key)
            if values is None:
                continue
            if not isinstance(values, Mapping):
                issues.append(_issue("error", "invalid-bitfield-values", f"{path}.{key}", "must be an object"))
                continue
            fields_present = fields_present or bool(values)
            for name, value in values.items():
                try:
                    parsed = _parse_int(value)
                except (TypeError, ValueError):
                    parsed = -1
                if not _bounded_text(name, maximum=64) or not 0 <= parsed <= 255:
                    issues.append(_issue("error", "invalid-bitfield-entry", f"{path}.{key}.{name}", "must have a bounded name and 0..255 value"))
        if not fields_present:
            issues.append(_issue("error", "empty-bitfield", path, "must declare fields or equals"))
    fixed_lengths = {"u16le": 2, "u24le": 3, "u32le": 4}
    if rule_type in fixed_lengths:
        try:
            start_byte = _parse_int(item.get("start_byte", item.get("byte", 0)))
        except (TypeError, ValueError):
            start_byte = -1
        if start_byte < 0 or start_byte + fixed_lengths[rule_type] > 8:
            issues.append(_issue("error", "status-width-exceeds-frame", path, "selected bytes exceed an eight-byte CAN frame"))
    if rule_type == "uint_le":
        try:
            length = _parse_int(item.get("length", 1))
        except (TypeError, ValueError):
            length = 0
        if not 1 <= length <= 8:
            issues.append(_issue("error", "invalid-integer-length", f"{path}.length", "must be between 1 and 8"))
        else:
            try:
                start_byte = _parse_int(item.get("start_byte", item.get("byte", 0)))
            except (TypeError, ValueError):
                start_byte = -1
            if start_byte < 0 or start_byte + length > 8:
                issues.append(_issue("error", "status-width-exceeds-frame", path, "selected bytes exceed an eight-byte CAN frame"))


def validate_profile(document: Any) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    if not isinstance(document, Mapping):
        return _validation([_issue("error", "invalid-document", "$", "profile must contain a JSON object")])

    default_bus = document.get("default_bus", DEFAULT_BUS)
    if not isinstance(default_bus, str) or not IDENTIFIER_RE.fullmatch(default_bus):
        issues.append(_issue("error", "invalid-default-bus", "default_bus", "must be a valid identifier"))
        default_bus = DEFAULT_BUS

    raw_buses = document.get("can_buses")
    if raw_buses is None:
        raw_buses = {default_bus: {}}
        issues.append(_issue("warning", "legacy-bus-fallback", "can_buses", "missing bus metadata uses the documented single-bus fallback"))
    elif not isinstance(raw_buses, Mapping):
        issues.append(_issue("error", "invalid-can-buses", "can_buses", "must be an object"))
        raw_buses = {}

    declared_buses: set[str] = set()
    for raw_name, metadata in raw_buses.items():
        path = f"can_buses.{raw_name}"
        if not isinstance(raw_name, str) or not IDENTIFIER_RE.fullmatch(raw_name):
            issues.append(_issue("error", "invalid-bus-name", path, "must be a valid identifier"))
            continue
        declared_buses.add(raw_name)
        if not isinstance(metadata, Mapping):
            issues.append(_issue("error", "invalid-bus-metadata", path, "must be an object"))
            continue
        interface = metadata.get("interface", metadata.get("tested_interface", DEFAULT_INTERFACE))
        if not isinstance(interface, str) or not INTERFACE_RE.fullmatch(interface):
            issues.append(_issue("error", "invalid-interface", f"{path}.interface", "must be a valid Linux interface name"))
        if "bitrate" in metadata:
            try:
                bitrate = _parse_int(metadata["bitrate"])
            except (TypeError, ValueError):
                bitrate = 0
            if not 1 <= bitrate <= 10_000_000:
                issues.append(_issue("error", "invalid-bitrate", f"{path}.bitrate", "must be between 1 and 10000000"))
        provisioning = metadata.get("provisioning", "manual")
        if provisioning not in PROVISIONING_MODES:
            issues.append(_issue("error", "invalid-provisioning", f"{path}.provisioning", "must be manual or udev"))
        if "bring_up" in metadata and not isinstance(metadata["bring_up"], bool):
            issues.append(_issue("error", "invalid-bring-up", f"{path}.bring_up", "must be boolean"))

    if default_bus not in declared_buses:
        issues.append(_issue("warning", "default-bus-fallback", "default_bus", "default bus is not declared and will use legacy fallback metadata"))
        declared_buses.add(default_bus)

    for key, kind in (("rules", "rule"), ("presence", "presence"), ("status", "status")):
        items = document.get(key, [])
        if not isinstance(items, list):
            issues.append(_issue("error", "invalid-rule-collection", key, "must be an array"))
            continue
        for index, item in enumerate(items):
            _validate_profile_item(item, f"{key}[{index}]", kind, default_bus, declared_buses, issues)

    return _validation(issues)


def validate_bindings(document: Any) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    if not isinstance(document, Mapping):
        return _validation([_issue("error", "invalid-document", "$", "bindings must contain a JSON object")])

    if document:
        issues.append(
            _issue(
                "warning",
                "legacy-action-schema",
                "$",
                "bindings use the runtime compatibility schema until the action registry is introduced",
            )
        )
    for event, action in document.items():
        path = f"bindings.{event}"
        if not _bounded_text(event, maximum=MAX_EVENT_LENGTH):
            issues.append(_issue("error", "invalid-event", path, "event name must be a bounded string"))
        if not isinstance(action, Mapping):
            issues.append(_issue("error", "invalid-binding", path, "must be an object"))
            continue
        unsupported = sorted(set(action) - {"module", "func", "args"})
        for key in unsupported:
            issues.append(_issue("error", "unsupported-binding-field", f"{path}.{key}", "is not supported"))
        for key in ("module", "func"):
            if not isinstance(action.get(key), str) or not PYTHON_IDENTIFIER_RE.fullmatch(action[key]):
                issues.append(_issue("error", f"invalid-{key}", f"{path}.{key}", "must be a Python identifier"))
        args = action.get("args", [])
        if not isinstance(args, list) or len(args) > 16:
            issues.append(_issue("error", "invalid-arguments", f"{path}.args", "must be an array of at most 16 values"))
        else:
            for index, value in enumerate(args):
                if (
                    isinstance(value, (list, dict))
                    or (isinstance(value, str) and len(value.encode("utf-8")) > 4096)
                    or (isinstance(value, float) and not math.isfinite(value))
                ):
                    issues.append(_issue("error", "invalid-argument", f"{path}.args[{index}]", "must be a bounded JSON scalar"))
    return _validation(issues)


def compatibility_report(profile: Any, bindings: Any) -> dict[str, Any]:
    emitted: list[str] = []
    if isinstance(profile, Mapping):
        for item in profile.get("rules", []) if isinstance(profile.get("rules", []), list) else []:
            if isinstance(item, Mapping) and isinstance(item.get("event"), str):
                emitted.append(item["event"])
        for item in profile.get("presence", []) if isinstance(profile.get("presence", []), list) else []:
            if not isinstance(item, Mapping):
                continue
            for key in ("on_present", "on_absent"):
                if isinstance(item.get(key), str):
                    emitted.append(item[key])
    bound = sorted(str(key) for key in bindings) if isinstance(bindings, Mapping) else []
    emitted_set = set(emitted)
    bound_set = set(bound)
    return {
        "emitted_and_bound": sorted(emitted_set & bound_set),
        "emitted_unbound": sorted(emitted_set - bound_set),
        "bound_unemitted": sorted(bound_set - emitted_set),
        "duplicate_emitted": sorted(key for key, count in Counter(emitted).items() if count > 1),
    }


def _unique_json_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def _read_document(path: Path, maximum_bytes: int) -> tuple[Any, str]:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError as exc:
        raise VehicleSetupError("Catalogue document is missing") from exc
    except OSError as exc:
        raise VehicleSetupError("Catalogue document cannot be inspected") from exc
    if not stat.S_ISREG(mode):
        raise VehicleSetupError("Catalogue document must be a regular file")
    try:
        size = path.stat().st_size
        if size > maximum_bytes:
            raise VehicleSetupError("Catalogue document exceeds the size limit")
        content = path.read_bytes()
    except OSError as exc:
        raise VehicleSetupError("Catalogue document cannot be read") from exc
    revision = "sha256:" + hashlib.sha256(content).hexdigest()
    try:
        return (
            json.loads(
                content.decode("utf-8"),
                object_pairs_hook=_unique_json_object,
                parse_constant=_reject_json_constant,
            ),
            revision,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise VehicleSetupError("Catalogue document is not valid UTF-8 JSON") from exc


def _display_name(identifier: str) -> str:
    words = re.split(r"[-_]", identifier)
    return " ".join(word.upper() if len(word) <= 2 and any(character.isdigit() for character in word) else word.capitalize() for word in words)


def _invalid_entry(source: str, identifier: str, message: str, code: str = "invalid-entry") -> dict[str, Any]:
    return {
        "source": source,
        "id": identifier,
        "display_name": _display_name(identifier),
        "valid": False,
        "revision": "",
        "validation": _validation([_issue("error", code, "$", message)]),
    }


def _profile_entry(roots: CatalogueRoots, source: str, identifier: str) -> dict[str, Any]:
    try:
        path = resolve_catalogue_path(roots, "profile", source, identifier)
        document, revision = _read_document(path, MAX_PROFILE_BYTES)
    except VehicleSetupError as exc:
        return _invalid_entry(source, identifier, str(exc))
    validation = validate_profile(document)
    buses: list[dict[str, Any]] = []
    if isinstance(document, Mapping):
        default_bus = document.get("default_bus", DEFAULT_BUS)
        raw_buses = document.get("can_buses")
        if not isinstance(raw_buses, Mapping):
            raw_buses = {default_bus: {}}
        for name in sorted(raw_buses):
            metadata = raw_buses[name]
            metadata = metadata if isinstance(metadata, Mapping) else {}
            bitrate = metadata.get("bitrate")
            try:
                bitrate = _parse_int(bitrate) if bitrate is not None else None
            except (TypeError, ValueError):
                bitrate = None
            buses.append(
                {
                    "name": str(name),
                    "interface": str(metadata.get("interface") or metadata.get("tested_interface") or DEFAULT_INTERFACE),
                    "bitrate": bitrate,
                    "provisioning": str(metadata.get("provisioning") or "manual"),
                }
            )
    else:
        default_bus = DEFAULT_BUS
    return {
        "source": source,
        "id": identifier,
        "display_name": _display_name(identifier),
        "valid": validation["valid"],
        "revision": revision,
        "default_bus": default_bus,
        "buses": buses,
        "event_count": len(document.get("rules", [])) if isinstance(document, Mapping) and isinstance(document.get("rules", []), list) else 0,
        "presence_rule_count": len(document.get("presence", [])) if isinstance(document, Mapping) and isinstance(document.get("presence", []), list) else 0,
        "status_rule_count": len(document.get("status", [])) if isinstance(document, Mapping) and isinstance(document.get("status", []), list) else 0,
        "validation": validation,
    }


def _bindings_entry(roots: CatalogueRoots, source: str, identifier: str) -> dict[str, Any]:
    try:
        path = resolve_catalogue_path(roots, "bindings", source, identifier)
        document, revision = _read_document(path, MAX_BINDINGS_BYTES)
    except VehicleSetupError as exc:
        return _invalid_entry(source, identifier, str(exc))
    validation = validate_bindings(document)
    return {
        "source": source,
        "id": identifier,
        "display_name": _display_name(identifier),
        "valid": validation["valid"],
        "revision": revision,
        "binding_count": len(document) if isinstance(document, Mapping) else 0,
        "validation": validation,
    }


def _discover_identifiers(root: Path, kind: str) -> tuple[list[str], list[dict[str, str]]]:
    directory = root / ("vehicles" if kind == "profile" else "bindings")
    if not directory.exists():
        return [], []
    if directory.is_symlink() or not directory.is_dir():
        return [], [_issue("error", "untrusted-catalogue-root", kind, "catalogue directory is not a trusted directory")]
    try:
        children = sorted(directory.iterdir(), key=lambda item: item.name)
    except OSError:
        return [], [_issue("error", "unreadable-catalogue", kind, "catalogue directory cannot be read")]
    if kind == "profile":
        identifiers = [
            child.name
            for child in children
            if child.name != "__pycache__"
            and not child.name.startswith(".")
            and (
                child.is_symlink()
                or (child.is_dir() and (child / "config.json").exists())
            )
        ]
    else:
        identifiers = [child.name[:-5] for child in children if child.name.endswith(".json")]
    return identifiers, []


def catalogue_payload(roots: Optional[CatalogueRoots] = None) -> dict[str, Any]:
    selected_roots = roots or default_roots()
    profiles: list[dict[str, Any]] = []
    bindings: list[dict[str, Any]] = []
    issues: list[dict[str, str]] = []
    for source, root in (("maintained", selected_roots.maintained), ("custom", selected_roots.custom)):
        profile_ids, profile_issues = _discover_identifiers(root, "profile")
        binding_ids, binding_issues = _discover_identifiers(root, "bindings")
        issues.extend(profile_issues)
        issues.extend(binding_issues)
        for identifier in profile_ids:
            if validate_identifier(identifier)["valid"]:
                profiles.append(_profile_entry(selected_roots, source, identifier))
            else:
                profiles.append(_invalid_entry(source, identifier, "Invalid catalogue identifier", "invalid-identifier"))
        for identifier in binding_ids:
            if validate_identifier(identifier)["valid"]:
                bindings.append(_bindings_entry(selected_roots, source, identifier))
            else:
                bindings.append(_invalid_entry(source, identifier, "Invalid catalogue identifier", "invalid-identifier"))
    key = lambda entry: (0 if entry["source"] == "maintained" else 1, entry["id"])
    profiles.sort(key=key)
    bindings.sort(key=key)
    return {
        "development_mode": selected_roots.development_mode,
        "profiles": profiles,
        "bindings": bindings,
        "issues": issues,
    }


def discover_interfaces(sys_class_net: Path = Path("/sys/class/net")) -> list[dict[str, Any]]:
    interfaces: list[dict[str, Any]] = []
    try:
        entries = sorted(sys_class_net.iterdir(), key=lambda item: item.name)
    except (FileNotFoundError, OSError):
        return interfaces
    for entry in entries:
        if not INTERFACE_RE.fullmatch(entry.name):
            continue
        try:
            if (entry / "type").read_text(encoding="utf-8").strip() != "280":
                continue
            operstate = (entry / "operstate").read_text(encoding="utf-8").strip()
            flags_path = entry / "flags"
            flags = int(flags_path.read_text(encoding="utf-8").strip(), 0) if flags_path.exists() else None
            bitrate_path = entry / "can" / "bitrate"
            bitrate = int(bitrate_path.read_text(encoding="utf-8").strip()) if bitrate_path.exists() else None
        except (OSError, ValueError):
            continue
        interfaces.append(
            {
                "name": entry.name,
                "kind": "socketcan",
                "present": True,
                "up": bool(flags & 1) if flags is not None else operstate == "up",
                "operstate": operstate,
                "configured_bitrate": bitrate,
                "last_frame_age_seconds": None,
            }
        )
    return interfaces


def _default_dropin_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / "canbusd.service.d" / "10-can-runtime.conf"


def read_runtime_environment(path: Optional[Path] = None) -> dict[str, str]:
    target = path or _default_dropin_path()
    if target.is_symlink():
        raise VehicleSetupError("Runtime drop-in may not be a symlink")
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise VehicleSetupError("Runtime drop-in cannot be read") from exc
    values: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("Environment="):
            continue
        try:
            entries = shlex.split(stripped[len("Environment=") :], posix=True)
        except ValueError:
            continue
        for entry in entries:
            if "=" not in entry:
                continue
            key, value = entry.split("=", 1)
            if key in RUNTIME_ENVIRONMENT_KEYS:
                values[key] = value
    return values


def _identity_from_environment(
    roots: CatalogueRoots,
    kind: str,
    identifier: str,
    explicit_path: str,
) -> dict[str, Any]:
    if explicit_path:
        candidate = Path(explicit_path).expanduser()
        for source in ("maintained", "custom"):
            try:
                expected = resolve_catalogue_path(roots, kind, source, identifier)
            except VehicleSetupError:
                continue
            if candidate == expected:
                return {"source": source, "id": identifier}
        return {"source": "external", "id": identifier}
    return {"source": "maintained", "id": identifier}


def _find_entry(entries: Iterable[Mapping[str, Any]], identity: Mapping[str, str]) -> Optional[dict[str, Any]]:
    return next(
        (
            dict(entry)
            for entry in entries
            if entry.get("source") == identity.get("source") and entry.get("id") == identity.get("id")
        ),
        None,
    )


def _load_identity_document(
    roots: CatalogueRoots,
    kind: str,
    identity: Mapping[str, str],
) -> Any:
    if identity.get("source") not in {"maintained", "custom"}:
        return {}
    try:
        path = resolve_catalogue_path(roots, kind, identity["source"], identity["id"])
        document, _revision = _read_document(path, MAX_PROFILE_BYTES if kind == "profile" else MAX_BINDINGS_BYTES)
        return document
    except (KeyError, VehicleSetupError):
        return {}


def status_payload(
    roots: Optional[CatalogueRoots] = None,
    *,
    environment: Optional[Mapping[str, str]] = None,
    dropin_path: Optional[Path] = None,
    sys_class_net: Path = Path("/sys/class/net"),
) -> dict[str, Any]:
    """Return the complete read-only setup status used by CLI and dashboard."""

    selected_roots = roots or default_roots(environment)
    if environment is None:
        runtime_environment = read_runtime_environment(dropin_path)
        for key in RUNTIME_ENVIRONMENT_KEYS:
            if key in os.environ:
                runtime_environment[key] = os.environ[key]
    else:
        runtime_environment = {key: str(value) for key, value in environment.items() if key in RUNTIME_ENVIRONMENT_KEYS}

    catalogue = catalogue_payload(selected_roots)
    vehicle_id = runtime_environment.get("OPEN_MMI_VEHICLE", "seat_1p")
    bindings_id = runtime_environment.get("OPEN_MMI_BINDINGS", "default")
    vehicle = _identity_from_environment(
        selected_roots,
        "profile",
        vehicle_id,
        runtime_environment.get("OPEN_MMI_VEHICLE_CONFIG", ""),
    )
    bindings = _identity_from_environment(
        selected_roots,
        "bindings",
        bindings_id,
        runtime_environment.get("OPEN_MMI_BINDINGS_FILE", ""),
    )
    profile_entry = _find_entry(catalogue["profiles"], vehicle)
    bindings_entry = _find_entry(catalogue["bindings"], bindings)
    profile_document = _load_identity_document(selected_roots, "profile", vehicle)
    bindings_document = _load_identity_document(selected_roots, "bindings", bindings)
    runtime = resolve_can_runtime(profile_document if isinstance(profile_document, Mapping) else {}, runtime_environment)
    active_errors: list[str] = []
    if vehicle["source"] == "external":
        active_errors.append("external-profile-path")
    elif profile_entry is None:
        active_errors.append("profile-not-found")
    elif not profile_entry.get("valid"):
        active_errors.append("profile-invalid")
    if bindings["source"] == "external":
        active_errors.append("external-bindings-path")
    elif bindings_entry is None:
        active_errors.append("bindings-not-found")
    elif not bindings_entry.get("valid"):
        active_errors.append("bindings-invalid")

    revisions = {
        "vehicle": str(profile_entry.get("revision") or "") if profile_entry else "",
        "bindings": str(bindings_entry.get("revision") or "") if bindings_entry else "",
    }
    revision_input = json.dumps(
        {**revisions, "active_bus": runtime.name, "interface": runtime.interface},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    configuration_revision = "sha256:" + hashlib.sha256(revision_input).hexdigest()
    interfaces = discover_interfaces(sys_class_net)
    interface_names = {entry["name"] for entry in interfaces}
    return {
        "api_version": API_VERSION,
        "read_only": True,
        "runtime_mode": "single",
        "catalogue": catalogue,
        "active": {
            "state": "ready" if not active_errors else "invalid",
            "errors": active_errors,
            "vehicle": {**vehicle, "revision": revisions["vehicle"]},
            "bindings": {**bindings, "revision": revisions["bindings"]},
            "active_bus": runtime.name,
            "interface": runtime.interface,
            "interface_present": runtime.interface in interface_names,
            "configuration_revision": configuration_revision,
            "loaded": None,
        },
        "compatibility": compatibility_report(profile_document, bindings_document),
        "interfaces": interfaces,
    }
