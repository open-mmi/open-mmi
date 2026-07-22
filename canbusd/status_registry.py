"""Canonical Open MMI persistent vehicle-status registry.

Vehicle profiles decode manufacturer-specific CAN data into these status paths.
The registry defines the shared human meaning, value type, unit, lifecycle and
search vocabulary for each path. It is a continuity checkpoint, not a
permission system: raw discovery may stay provisional, while maintained
profiles use canonical paths or explicit deprecated compatibility aliases.
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
REGISTRY_ID = "open-mmi.vehicle-statuses"
MAX_REGISTRY_BYTES = 1024 * 1024
DEFAULT_REGISTRY_PATH = Path(__file__).with_name("data") / "vehicle-statuses.v1.json"
STATUS_PATH_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
CATEGORIES = {
    "climate",
    "doors",
    "electrical",
    "engine",
    "fuel",
    "lighting",
    "parking",
    "steering",
    "vehicle",
}
VALUE_TYPES = {"boolean", "integer", "number", "enum", "string"}
STATUS_LIFECYCLES = {"stable", "experimental", "diagnostic", "deprecated"}
GENERIC_SEARCH_TERMS = {"signal", "status", "state", "value", "data", "can"}


class VehicleStatusRegistryError(ValueError):
    """Raised when the bundled status registry or a status lookup is invalid."""


def _object(
    value: Any,
    *,
    path: str,
    required: set[str],
    optional: Optional[set[str]] = None,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise VehicleStatusRegistryError(f"{path} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise VehicleStatusRegistryError(f"{path} contains an invalid field name")
    allowed = required | (optional or set())
    unknown = sorted(set(value) - allowed)
    missing = sorted(required - set(value))
    if unknown:
        raise VehicleStatusRegistryError(
            f"{path} contains unsupported fields: {', '.join(unknown)}"
        )
    if missing:
        raise VehicleStatusRegistryError(
            f"{path} is missing required fields: {', '.join(missing)}"
        )
    return value


def _named_mapping(value: Any, *, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise VehicleStatusRegistryError(f"{path} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise VehicleStatusRegistryError(f"{path} contains an invalid field name")
    return value


def _bounded_text(value: Any, *, path: str, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > maximum
        or any(ord(character) < 32 for character in value)
    ):
        raise VehicleStatusRegistryError(f"{path} must be bounded text")
    return value


def _number(value: Any, *, path: str) -> Any:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise VehicleStatusRegistryError(f"{path} must be numeric")
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        raise VehicleStatusRegistryError(f"{path} must be finite")
    return value


def _value_contract(value: Any, *, path: str) -> dict[str, Any]:
    contract = _object(
        value,
        path=path,
        required={"type", "nullable"},
        optional={"unit", "minimum", "maximum", "values"},
    )
    value_type = contract["type"]
    if value_type not in VALUE_TYPES:
        raise VehicleStatusRegistryError(f"{path}.type is unsupported")
    if not isinstance(contract["nullable"], bool):
        raise VehicleStatusRegistryError(f"{path}.nullable must be boolean")

    normalized: dict[str, Any] = {
        "type": value_type,
        "nullable": contract["nullable"],
    }
    if "unit" in contract:
        if value_type not in {"integer", "number"}:
            raise VehicleStatusRegistryError(
                f"{path}.unit is only valid for numeric values"
            )
        normalized["unit"] = _bounded_text(
            contract["unit"], path=f"{path}.unit", maximum=32
        )

    minimum = contract.get("minimum")
    maximum = contract.get("maximum")
    if minimum is not None:
        if value_type not in {"integer", "number"}:
            raise VehicleStatusRegistryError(
                f"{path}.minimum is only valid for numeric values"
            )
        normalized["minimum"] = _number(minimum, path=f"{path}.minimum")
    if maximum is not None:
        if value_type not in {"integer", "number"}:
            raise VehicleStatusRegistryError(
                f"{path}.maximum is only valid for numeric values"
            )
        normalized["maximum"] = _number(maximum, path=f"{path}.maximum")
    if (
        "minimum" in normalized
        and "maximum" in normalized
        and normalized["minimum"] > normalized["maximum"]
    ):
        raise VehicleStatusRegistryError(f"{path} numeric bounds are invalid")

    if value_type == "enum":
        raw_values = contract.get("values")
        if (
            not isinstance(raw_values, list)
            or not raw_values
            or any(not isinstance(item, str) or not item for item in raw_values)
            or len(set(raw_values)) != len(raw_values)
        ):
            raise VehicleStatusRegistryError(
                f"{path}.values must be a non-empty unique string array"
            )
        normalized["values"] = list(raw_values)
    elif "values" in contract:
        raise VehicleStatusRegistryError(
            f"{path}.values is only valid for enum values"
        )
    return normalized


def normalize_registry(value: Any) -> dict[str, Any]:
    registry = _object(
        value,
        path="registry",
        required={"schema_version", "registry_id", "statuses", "aliases"},
    )
    if registry["schema_version"] != SCHEMA_VERSION or isinstance(
        registry["schema_version"], bool
    ):
        raise VehicleStatusRegistryError("registry.schema_version is unsupported")
    if registry["registry_id"] != REGISTRY_ID:
        raise VehicleStatusRegistryError("registry.registry_id is unsupported")

    raw_statuses = _named_mapping(registry["statuses"], path="registry.statuses")
    if not raw_statuses:
        raise VehicleStatusRegistryError("registry.statuses must not be empty")
    statuses: dict[str, dict[str, Any]] = {}
    for path_name in sorted(raw_statuses):
        if not STATUS_PATH_RE.fullmatch(path_name):
            raise VehicleStatusRegistryError(
                f"registry.statuses.{path_name} has an invalid path"
            )
        entry = _object(
            raw_statuses[path_name],
            path=f"registry.statuses.{path_name}",
            required={"title", "category", "description", "value", "status"},
            optional={"search_terms"},
        )
        category = entry["category"]
        lifecycle = entry["status"]
        if category not in CATEGORIES:
            raise VehicleStatusRegistryError(
                f"registry.statuses.{path_name}.category is unsupported"
            )
        if lifecycle not in STATUS_LIFECYCLES:
            raise VehicleStatusRegistryError(
                f"registry.statuses.{path_name}.status is unsupported"
            )
        normalized = {
            "title": _bounded_text(
                entry["title"],
                path=f"registry.statuses.{path_name}.title",
                maximum=96,
            ),
            "category": category,
            "description": _bounded_text(
                entry["description"],
                path=f"registry.statuses.{path_name}.description",
                maximum=768,
            ),
            "value": _value_contract(
                entry["value"],
                path=f"registry.statuses.{path_name}.value",
            ),
            "status": lifecycle,
        }
        if "search_terms" in entry:
            terms = entry["search_terms"]
            if (
                not isinstance(terms, list)
                or any(
                    not isinstance(term, str)
                    or not term
                    or len(term.encode("utf-8")) > 256
                    for term in terms
                )
            ):
                raise VehicleStatusRegistryError(
                    f"registry.statuses.{path_name}.search_terms must be bounded text"
                )
            normalized["search_terms"] = list(terms)
        statuses[path_name] = normalized

    raw_aliases = _named_mapping(registry["aliases"], path="registry.aliases")
    aliases: dict[str, dict[str, str]] = {}
    for alias in sorted(raw_aliases):
        if not STATUS_PATH_RE.fullmatch(alias):
            raise VehicleStatusRegistryError(
                f"registry.aliases.{alias} has an invalid path"
            )
        if alias in statuses:
            raise VehicleStatusRegistryError(
                f"registry.aliases.{alias} conflicts with a canonical status"
            )
        entry = _object(
            raw_aliases[alias],
            path=f"registry.aliases.{alias}",
            required={"path", "description", "status"},
        )
        canonical = entry["path"]
        if canonical not in statuses:
            raise VehicleStatusRegistryError(
                f"registry.aliases.{alias}.path is not canonical"
            )
        if entry["status"] != "deprecated":
            raise VehicleStatusRegistryError(
                f"registry.aliases.{alias}.status must be deprecated"
            )
        aliases[alias] = {
            "path": canonical,
            "description": _bounded_text(
                entry["description"],
                path=f"registry.aliases.{alias}.description",
                maximum=768,
            ),
            "status": "deprecated",
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "registry_id": REGISTRY_ID,
        "statuses": statuses,
        "aliases": aliases,
    }


def _unique_json_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise VehicleStatusRegistryError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _reject_json_constant(value: str) -> None:
    raise VehicleStatusRegistryError(f"non-finite JSON number: {value}")


def load_registry(path: Path = DEFAULT_REGISTRY_PATH) -> dict[str, Any]:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise VehicleStatusRegistryError(
            "vehicle status registry cannot be inspected"
        ) from exc
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_REGISTRY_BYTES:
        raise VehicleStatusRegistryError(
            "vehicle status registry must be a bounded regular file"
        )
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise VehicleStatusRegistryError(
            "vehicle status registry cannot be read"
        ) from exc
    if len(content) > MAX_REGISTRY_BYTES:
        raise VehicleStatusRegistryError(
            "vehicle status registry exceeds the size limit"
        )
    try:
        document = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VehicleStatusRegistryError(
            "vehicle status registry is not valid UTF-8 JSON"
        ) from exc
    return normalize_registry(document)


@lru_cache(maxsize=1)
def _default_registry() -> dict[str, Any]:
    return load_registry(DEFAULT_REGISTRY_PATH)


def registry_payload() -> dict[str, Any]:
    return copy.deepcopy(_default_registry())


def _status_state(
    path: Any,
    registry: Mapping[str, Any],
) -> tuple[str, Optional[str]]:
    if not isinstance(path, str) or not STATUS_PATH_RE.fullmatch(path):
        return "invalid", None
    if path in registry["statuses"]:
        return "canonical", path
    alias = registry["aliases"].get(path)
    if alias:
        return "alias", alias["path"]
    return "unknown", None


def status_state(
    path: Any,
    registry: Optional[Mapping[str, Any]] = None,
) -> tuple[str, Optional[str]]:
    selected = (
        normalize_registry(registry)
        if registry is not None
        else _default_registry()
    )
    return _status_state(path, selected)


def status_definition(path: str) -> dict[str, Any]:
    selected = _default_registry()
    state, canonical = _status_state(path, selected)
    if state == "invalid":
        raise VehicleStatusRegistryError("status path is invalid")
    if state == "unknown" or canonical is None:
        raise VehicleStatusRegistryError(f"status path is not registered: {path}")
    return {
        "path": canonical,
        "requested_path": path,
        "requested_status": state,
        **copy.deepcopy(selected["statuses"][canonical]),
    }


def _types_compatible(expected: str, actual: Optional[str]) -> bool:
    if actual is None:
        return True
    if expected == actual:
        return True
    return expected == "number" and actual == "integer"


def require_status(
    path: Any,
    *,
    value_type: Optional[str] = None,
    allow_alias: bool = False,
    registry: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    selected = (
        normalize_registry(registry)
        if registry is not None
        else _default_registry()
    )
    state, canonical = _status_state(path, selected)
    if state == "invalid":
        raise VehicleStatusRegistryError("status path is invalid")
    if state == "alias" and canonical is not None and not allow_alias:
        raise VehicleStatusRegistryError(
            f"status alias {path!r} is deprecated; use {canonical!r}"
        )
    if state == "unknown" or canonical is None:
        raise VehicleStatusRegistryError(f"status path is not registered: {path}")
    definition = selected["statuses"][canonical]
    expected = definition["value"]["type"]
    if not _types_compatible(expected, value_type):
        raise VehicleStatusRegistryError(
            f"status {canonical!r} expects {expected}, not {value_type}"
        )
    return copy.deepcopy(definition)


def _search_tokens(query: Any) -> tuple[str, list[str]]:
    if not isinstance(query, str):
        raise VehicleStatusRegistryError("status search query must be text")
    normalized = query.strip().lower()
    if (
        not normalized
        or len(normalized.encode("utf-8")) > 256
        or any(ord(character) < 32 for character in normalized)
    ):
        raise VehicleStatusRegistryError(
            "status search query must be bounded text"
        )
    tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", normalized)
        if token not in GENERIC_SEARCH_TERMS
    ]
    if not tokens:
        tokens = re.findall(r"[a-z0-9]+", normalized)
    if not tokens:
        raise VehicleStatusRegistryError(
            "status search query has no searchable terms"
        )
    return normalized, tokens


def search_statuses(
    query: Any,
    *,
    limit: int = 20,
    registry: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    normalized_query, tokens = _search_tokens(query)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise VehicleStatusRegistryError(
            "status search limit must be between 1 and 100"
        )
    selected = (
        normalize_registry(registry)
        if registry is not None
        else _default_registry()
    )
    aliases_by_path: dict[str, list[str]] = {}
    for alias, definition in selected["aliases"].items():
        aliases_by_path.setdefault(definition["path"], []).append(alias)

    matches: list[tuple[int, str, dict[str, Any]]] = []
    for path_name, definition in selected["statuses"].items():
        aliases = sorted(aliases_by_path.get(path_name, []))
        fields = {
            "path": path_name.lower(),
            "title": definition["title"].lower(),
            "category": definition["category"].lower(),
            "description": definition["description"].lower(),
            "search_terms": " ".join(definition.get("search_terms", [])).lower(),
            "aliases": " ".join(aliases).lower(),
        }
        combined = " ".join(fields.values()).replace("_", " ").replace(".", " ")
        if not all(token in combined for token in tokens):
            continue
        matched_on = sorted(
            field
            for field, value in fields.items()
            if any(
                token in value.replace("_", " ").replace(".", " ")
                for token in tokens
            )
        )
        score = 0
        if normalized_query == path_name.lower():
            score += 100
        elif path_name.lower().startswith(normalized_query):
            score += 70
        for token in tokens:
            if token in path_name.lower().replace("_", " ").replace(".", " "):
                score += 20
            if token in definition["title"].lower():
                score += 12
            if token in definition["description"].lower():
                score += 6
            if token in fields["search_terms"]:
                score += 10
            if token == definition["category"].lower():
                score += 4
            if any(token in alias.lower() for alias in aliases):
                score += 8
        matches.append(
            (
                -score,
                path_name,
                {
                    "path": path_name,
                    "matched_on": matched_on,
                    "aliases": aliases,
                    **copy.deepcopy(definition),
                },
            )
        )

    ordered = [item for _, _, item in sorted(matches)[:limit]]
    return {
        "query": query.strip(),
        "count": len(ordered),
        "matches": ordered,
        "guidance": (
            "The registry is a continuity checkpoint, not a walled garden. "
            "Reuse a matching human-readable status path. If no result describes "
            "the confirmed persistent state, propose a new universal path in the "
            "same pull request as the vehicle mapping."
        ),
    }


def contribution_check(
    path: Any,
    *,
    registry: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    selected = (
        normalize_registry(registry)
        if registry is not None
        else _default_registry()
    )
    state, canonical = _status_state(path, selected)
    principles = [
        "The registry is a continuity checkpoint, not a walled garden.",
        "CAN IDs, bytes and masks are vehicle-specific; status paths express shared human meaning.",
        "Unregistered names are allowed in discovery notes, but maintained profiles use registered canonical paths.",
    ]
    if state == "canonical" and canonical is not None:
        return {
            "requested_path": path,
            "status": state,
            "decision": "reuse",
            "path": canonical,
            "definition": copy.deepcopy(selected["statuses"][canonical]),
            "message": (
                "Reuse this canonical status path and change only the "
                "vehicle-specific CAN decoder."
            ),
            "principles": principles,
        }
    if state == "alias" and canonical is not None:
        return {
            "requested_path": path,
            "status": state,
            "decision": "use_canonical",
            "path": canonical,
            "definition": copy.deepcopy(selected["statuses"][canonical]),
            "message": (
                f"Use canonical status path {canonical!r}; the requested path "
                "is a deprecated compatibility alias."
            ),
            "principles": principles,
        }
    if state == "invalid":
        search_query = str(path).replace("_", " ").replace(".", " ")
        try:
            candidates = search_statuses(search_query, registry=selected)["matches"]
        except VehicleStatusRegistryError:
            candidates = []
        return {
            "requested_path": path,
            "status": state,
            "decision": "rename_before_proposal",
            "candidates": candidates,
            "message": (
                "Choose a lowercase dot-separated human-readable path before "
                "proposing it. Reuse a candidate when its meaning matches; do not "
                "encode a manufacturer, CAN ID, byte offset or decoder implementation."
            ),
            "principles": principles,
        }

    search_query = str(path).replace("_", " ").replace(".", " ")
    candidates = search_statuses(search_query, registry=selected)["matches"]
    return {
        "requested_path": path,
        "status": "unknown",
        "decision": "reuse_or_propose",
        "candidates": candidates,
        "message": (
            "No canonical status has this path. Reuse a candidate when its meaning "
            "matches. If the confirmed persistent human concept is genuinely new, "
            "add a registry entry, documentation and tests in the same pull request "
            "as the vehicle mapping."
        ),
        "principles": principles,
    }


def _paths(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(path) for path in value if path not in (None, "")]
    return [str(value)]


def _output(
    path: str,
    value_type: str,
    role: str,
    *,
    enum_values: Optional[Sequence[str]] = None,
) -> dict[str, Any]:
    output: dict[str, Any] = {
        "path": path,
        "value_type": value_type,
        "role": role,
    }
    if enum_values is not None:
        output["enum_values"] = sorted(set(enum_values))
    return output


def rule_outputs(rule: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return every persistent status path emitted by one decoder rule."""

    kind = str(rule.get("type", "raw"))
    outputs: list[dict[str, Any]] = []
    primary_enum_values: Optional[list[str]] = None
    if kind == "bool":
        primary_type = "boolean"
    elif kind == "enum":
        primary_type = "enum"
        raw_values = rule.get("values")
        if isinstance(raw_values, Mapping):
            primary_enum_values = [str(value) for value in raw_values.values()]
        default = rule.get("default")
        if isinstance(default, str):
            primary_enum_values = [*(primary_enum_values or []), default]
    elif kind in {"raw"}:
        primary_type = "integer"
    elif kind in {
        "percent",
        "scaled",
        "signed_magnitude",
        "steering_angle",
        "u16le",
        "u24le",
        "u32le",
        "uint_le",
    }:
        primary_type = "number"
    elif kind == "bitfield":
        prefix = rule.get("path")
        if isinstance(prefix, str):
            for key in ("fields", "equals"):
                values = rule.get(key)
                if isinstance(values, Mapping):
                    for name in values:
                        outputs.append(
                            _output(f"{prefix}.{name}", "boolean", "derived")
                        )
            if rule.get("any"):
                outputs.append(
                    _output(f"{prefix}.{rule['any']}", "boolean", "derived")
                )
            if rule.get("raw"):
                raw_key = rule["raw"] if isinstance(rule["raw"], str) else "raw"
                outputs.append(
                    _output(f"{prefix}.{raw_key}", "integer", "raw")
                )
        return outputs
    else:
        return outputs

    for path_name in _paths(rule.get("path")):
        outputs.append(
            _output(
                path_name,
                primary_type,
                "primary",
                enum_values=primary_enum_values,
            )
        )
    for path_name in _paths(rule.get("aliases")):
        outputs.append(
            _output(
                path_name,
                primary_type,
                "alias",
                enum_values=primary_enum_values,
            )
        )
    for path_name in _paths(rule.get("raw_path")):
        outputs.append(_output(path_name, "integer", "raw"))
    for path_name in _paths(rule.get("raw_aliases")):
        outputs.append(_output(path_name, "integer", "alias"))
    for key in ("magnitude_raw_path",):
        for path_name in _paths(rule.get(key)):
            outputs.append(_output(path_name, "integer", "raw"))
    for path_name in _paths(rule.get("direction_path")):
        outputs.append(
            _output(
                path_name,
                "enum",
                "derived",
                enum_values=("left", "center", "right"),
            )
        )
    return outputs


def profile_outputs(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    presence = document.get("presence", [])
    if isinstance(presence, list):
        for item in presence:
            if isinstance(item, Mapping):
                path_name = item.get("status_path", "vehicle.present")
                if isinstance(path_name, str):
                    outputs.append(_output(path_name, "boolean", "primary"))
    status_rules = document.get("status", [])
    if isinstance(status_rules, list):
        for item in status_rules:
            if isinstance(item, Mapping):
                outputs.extend(rule_outputs(item))
    return outputs


def require_output(
    output: Mapping[str, Any],
    *,
    registry: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Require one expanded decoder output to satisfy its canonical contract."""

    selected = (
        normalize_registry(registry)
        if registry is not None
        else _default_registry()
    )
    definition = require_status(
        output.get("path"),
        value_type=output.get("value_type"),
        allow_alias=output.get("role") == "alias",
        registry=selected,
    )
    enum_values = output.get("enum_values")
    if enum_values is not None:
        if not isinstance(enum_values, (list, tuple)) or any(
            not isinstance(value, str) for value in enum_values
        ):
            raise VehicleStatusRegistryError("status enum values are invalid")
        allowed = set(definition["value"].get("values", []))
        unsupported = sorted(set(enum_values) - allowed)
        if unsupported:
            raise VehicleStatusRegistryError(
                f"status {output.get('path')!r} emits unsupported enum values: "
                + ", ".join(repr(value) for value in unsupported)
            )
    return definition


def require_profile_statuses(
    document: Mapping[str, Any],
    *,
    registry: Optional[Mapping[str, Any]] = None,
) -> None:
    selected = (
        normalize_registry(registry)
        if registry is not None
        else _default_registry()
    )
    for output in profile_outputs(document):
        require_output(output, registry=selected)
