"""Canonical Open MMI action registry and binding resolution.

Bindings name stable human-readable actions.  The registry owns the private
Python implementation mapping so maintained configuration does not expose module
or function names.  Legacy module/func bindings remain accepted temporarily for
custom catalogue compatibility.
"""

from __future__ import annotations

import copy
import json
import math
import re
import stat
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence


SCHEMA_VERSION = 1
REGISTRY_ID = "open-mmi.vehicle-actions"
MAX_REGISTRY_BYTES = 256 * 1024
DEFAULT_REGISTRY_PATH = Path(__file__).with_name("data") / "vehicle-actions.v1.json"
ACTION_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
PYTHON_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
ARGUMENT_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
CATEGORIES = {"display", "media", "navigation", "vehicle"}
ACTION_STATUSES = {"stable", "deprecated"}
VALUE_TYPES = {"none", "boolean", "integer", "number", "string"}


class VehicleActionRegistryError(ValueError):
    """Raised for invalid registries, action lookups, or canonical bindings."""

    def __init__(self, message: str, *, code: str = "invalid-action") -> None:
        super().__init__(message)
        self.code = code


def _object(
    value: Any,
    *,
    path: str,
    required: set[str],
    optional: Optional[set[str]] = None,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise VehicleActionRegistryError(f"{path} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise VehicleActionRegistryError(f"{path} contains an invalid field name")
    allowed = required | (optional or set())
    unknown = sorted(set(value) - allowed)
    missing = sorted(required - set(value))
    if unknown:
        raise VehicleActionRegistryError(
            f"{path} contains unsupported fields: {', '.join(unknown)}"
        )
    if missing:
        raise VehicleActionRegistryError(
            f"{path} is missing required fields: {', '.join(missing)}"
        )
    return value


def _named_mapping(value: Any, *, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise VehicleActionRegistryError(f"{path} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise VehicleActionRegistryError(f"{path} contains an invalid field name")
    return value


def _bounded_text(value: Any, *, path: str, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > maximum
        or any(ord(character) < 32 for character in value)
    ):
        raise VehicleActionRegistryError(f"{path} must be bounded text")
    return value


def _number(value: Any, *, path: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise VehicleActionRegistryError(f"{path} must be numeric")
    if isinstance(value, float) and not math.isfinite(value):
        raise VehicleActionRegistryError(f"{path} must be finite")
    return value


def _value_contract(value: Any, *, path: str, allow_none: bool) -> dict[str, Any]:
    contract = _object(
        value,
        path=path,
        required={"type"},
        optional={"minimum", "maximum", "unit", "maximum_length", "pattern"},
    )
    value_type = contract["type"]
    if value_type not in VALUE_TYPES or (value_type == "none" and not allow_none):
        raise VehicleActionRegistryError(f"{path}.type is unsupported")
    if value_type == "none":
        if set(contract) != {"type"}:
            raise VehicleActionRegistryError(
                f"{path} none contract must not declare bounds, unit, length, or pattern"
            )
        return {"type": "none"}

    normalized: dict[str, Any] = {"type": value_type}
    if "minimum" in contract or "maximum" in contract:
        if value_type not in {"integer", "number"}:
            raise VehicleActionRegistryError(
                f"{path} bounds are only valid for integer or number values"
            )
        if "minimum" not in contract or "maximum" not in contract:
            raise VehicleActionRegistryError(f"{path} requires both minimum and maximum")
        minimum = _number(contract["minimum"], path=f"{path}.minimum")
        maximum = _number(contract["maximum"], path=f"{path}.maximum")
        if value_type == "integer" and (
            not isinstance(minimum, int) or not isinstance(maximum, int)
        ):
            raise VehicleActionRegistryError(f"{path} integer bounds must be integers")
        if minimum > maximum:
            raise VehicleActionRegistryError(f"{path} bounds are invalid")
        normalized["minimum"] = minimum
        normalized["maximum"] = maximum
    if "unit" in contract:
        if value_type not in {"integer", "number"}:
            raise VehicleActionRegistryError(
                f"{path}.unit is only valid for numeric values"
            )
        normalized["unit"] = _bounded_text(
            contract["unit"], path=f"{path}.unit", maximum=32
        )
    if "maximum_length" in contract:
        maximum_length = contract["maximum_length"]
        if (
            value_type != "string"
            or isinstance(maximum_length, bool)
            or not isinstance(maximum_length, int)
            or not 1 <= maximum_length <= 4096
        ):
            raise VehicleActionRegistryError(f"{path}.maximum_length is invalid")
        normalized["maximum_length"] = maximum_length
    if "pattern" in contract:
        if value_type != "string":
            raise VehicleActionRegistryError(
                f"{path}.pattern is only valid for string values"
            )
        pattern = _bounded_text(
            contract["pattern"], path=f"{path}.pattern", maximum=256
        )
        try:
            re.compile(pattern)
        except re.error as exc:
            raise VehicleActionRegistryError(f"{path}.pattern is invalid") from exc
        normalized["pattern"] = pattern
    return normalized


def _argument(value: Any, *, path: str) -> dict[str, Any]:
    entry = _object(
        value,
        path=path,
        required={"name", "type", "required"},
        optional={"minimum", "maximum", "unit", "maximum_length", "pattern", "default"},
    )
    name = entry["name"]
    if not isinstance(name, str) or not ARGUMENT_NAME_RE.fullmatch(name):
        raise VehicleActionRegistryError(f"{path}.name is invalid")
    if not isinstance(entry["required"], bool):
        raise VehicleActionRegistryError(f"{path}.required must be boolean")
    contract = _value_contract(
        {
            key: item
            for key, item in entry.items()
            if key not in {"name", "required", "default"}
        },
        path=path,
        allow_none=False,
    )
    normalized = {"name": name, "required": entry["required"], **contract}
    if "default" in entry:
        if entry["required"]:
            raise VehicleActionRegistryError(
                f"{path}.default is not valid for a required argument"
            )
        normalized["default"] = _validate_scalar(
            entry["default"], contract, path=f"{path}.default"
        )
    return normalized


def normalize_registry(value: Any) -> dict[str, Any]:
    registry = _object(
        value,
        path="registry",
        required={"schema_version", "registry_id", "actions", "aliases"},
    )
    if registry["schema_version"] != SCHEMA_VERSION or isinstance(
        registry["schema_version"], bool
    ):
        raise VehicleActionRegistryError("registry.schema_version is unsupported")
    if registry["registry_id"] != REGISTRY_ID:
        raise VehicleActionRegistryError("registry.registry_id is unsupported")

    raw_actions = _named_mapping(registry["actions"], path="registry.actions")
    if not raw_actions:
        raise VehicleActionRegistryError("registry.actions must not be empty")

    actions: dict[str, dict[str, Any]] = {}
    for name in sorted(raw_actions):
        if not ACTION_NAME_RE.fullmatch(name):
            raise VehicleActionRegistryError(f"registry.actions.{name} has an invalid name")
        entry = _object(
            raw_actions[name],
            path=f"registry.actions.{name}",
            required={
                "title",
                "category",
                "description",
                "implementation",
                "arguments",
                "event_payload",
                "requirements",
                "status",
            },
            optional={"search_terms"},
        )
        category = entry["category"]
        if category not in CATEGORIES:
            raise VehicleActionRegistryError(
                f"registry.actions.{name}.category is unsupported"
            )
        status = entry["status"]
        if status not in ACTION_STATUSES:
            raise VehicleActionRegistryError(
                f"registry.actions.{name}.status is unsupported"
            )
        implementation = _object(
            entry["implementation"],
            path=f"registry.actions.{name}.implementation",
            required={"module", "func"},
        )
        module = implementation["module"]
        func = implementation["func"]
        if not isinstance(module, str) or not PYTHON_IDENTIFIER_RE.fullmatch(module):
            raise VehicleActionRegistryError(
                f"registry.actions.{name}.implementation.module is invalid"
            )
        if not isinstance(func, str) or not PYTHON_IDENTIFIER_RE.fullmatch(func):
            raise VehicleActionRegistryError(
                f"registry.actions.{name}.implementation.func is invalid"
            )
        raw_arguments = entry["arguments"]
        if not isinstance(raw_arguments, list) or len(raw_arguments) > 8:
            raise VehicleActionRegistryError(
                f"registry.actions.{name}.arguments must be an array of at most 8 items"
            )
        arguments: list[dict[str, Any]] = []
        argument_names: set[str] = set()
        optional_seen = False
        for index, raw_argument in enumerate(raw_arguments):
            argument = _argument(
                raw_argument,
                path=f"registry.actions.{name}.arguments[{index}]",
            )
            if argument["name"] in argument_names:
                raise VehicleActionRegistryError(
                    f"registry.actions.{name}.arguments contains a duplicate name"
                )
            argument_names.add(argument["name"])
            if optional_seen and argument["required"]:
                raise VehicleActionRegistryError(
                    f"registry.actions.{name}.arguments cannot require an argument after an optional one"
                )
            optional_seen = optional_seen or not argument["required"]
            arguments.append(argument)

        requirements = entry["requirements"]
        if (
            not isinstance(requirements, list)
            or len(requirements) > 16
            or any(not isinstance(item, str) for item in requirements)
        ):
            raise VehicleActionRegistryError(
                f"registry.actions.{name}.requirements must be an array of text"
            )
        normalized_requirements = [
            _bounded_text(
                item,
                path=f"registry.actions.{name}.requirements[{index}]",
                maximum=80,
            )
            for index, item in enumerate(requirements)
        ]
        search_terms = entry.get("search_terms", [])
        if (
            not isinstance(search_terms, list)
            or len(search_terms) > 16
            or any(not isinstance(item, str) for item in search_terms)
        ):
            raise VehicleActionRegistryError(
                f"registry.actions.{name}.search_terms must be an array of text"
            )
        normalized_search_terms = [
            _bounded_text(
                item,
                path=f"registry.actions.{name}.search_terms[{index}]",
                maximum=160,
            )
            for index, item in enumerate(search_terms)
        ]

        actions[name] = {
            "title": _bounded_text(
                entry["title"], path=f"registry.actions.{name}.title", maximum=80
            ),
            "category": category,
            "description": _bounded_text(
                entry["description"],
                path=f"registry.actions.{name}.description",
                maximum=512,
            ),
            "implementation": {"module": module, "func": func},
            "arguments": arguments,
            "event_payload": _value_contract(
                entry["event_payload"],
                path=f"registry.actions.{name}.event_payload",
                allow_none=True,
            ),
            "requirements": normalized_requirements,
            "status": status,
            "search_terms": normalized_search_terms,
        }

    raw_aliases = _named_mapping(registry["aliases"], path="registry.aliases")
    aliases: dict[str, dict[str, str]] = {}
    for alias in sorted(raw_aliases):
        if not ACTION_NAME_RE.fullmatch(alias):
            raise VehicleActionRegistryError(f"registry.aliases.{alias} has an invalid name")
        if alias in actions:
            raise VehicleActionRegistryError(
                f"registry.aliases.{alias} conflicts with a canonical action"
            )
        entry = _object(
            raw_aliases[alias],
            path=f"registry.aliases.{alias}",
            required={"action", "description", "status"},
        )
        canonical = entry["action"]
        if canonical not in actions:
            raise VehicleActionRegistryError(
                f"registry.aliases.{alias}.action is not canonical"
            )
        if entry["status"] != "deprecated":
            raise VehicleActionRegistryError(
                f"registry.aliases.{alias}.status must be deprecated"
            )
        aliases[alias] = {
            "action": canonical,
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
        "actions": actions,
        "aliases": aliases,
    }


def _unique_json_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise VehicleActionRegistryError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _reject_json_constant(value: str) -> None:
    raise VehicleActionRegistryError(f"non-finite JSON number: {value}")


def load_registry(path: Path = DEFAULT_REGISTRY_PATH) -> dict[str, Any]:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise VehicleActionRegistryError(
            "vehicle action registry cannot be inspected"
        ) from exc
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_REGISTRY_BYTES:
        raise VehicleActionRegistryError(
            "vehicle action registry must be a bounded regular file"
        )
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise VehicleActionRegistryError("vehicle action registry cannot be read") from exc
    if len(content) > MAX_REGISTRY_BYTES:
        raise VehicleActionRegistryError("vehicle action registry exceeds the size limit")
    try:
        document = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VehicleActionRegistryError(
            "vehicle action registry is not valid UTF-8 JSON"
        ) from exc
    return normalize_registry(document)


@lru_cache(maxsize=1)
def _default_registry() -> dict[str, Any]:
    return load_registry(DEFAULT_REGISTRY_PATH)


def registry_payload() -> dict[str, Any]:
    """Return a defensive copy of the canonical bundled action registry."""

    return copy.deepcopy(_default_registry())


def _action_status(
    name: Any,
    registry: Mapping[str, Any],
) -> tuple[str, Optional[str]]:
    if not isinstance(name, str) or not ACTION_NAME_RE.fullmatch(name):
        return "invalid", None
    if name in registry["actions"]:
        return "canonical", name
    alias = registry["aliases"].get(name)
    if alias:
        return "alias", alias["action"]
    return "unknown", None


def action_status(
    name: Any,
    registry: Optional[Mapping[str, Any]] = None,
) -> tuple[str, Optional[str]]:
    selected = normalize_registry(registry) if registry is not None else _default_registry()
    return _action_status(name, selected)


def action_definition(name: str) -> dict[str, Any]:
    selected = _default_registry()
    status, canonical = _action_status(name, selected)
    if status == "invalid":
        raise VehicleActionRegistryError("action name is invalid", code="invalid-action")
    if status == "unknown" or canonical is None:
        raise VehicleActionRegistryError(
            f"action is not registered: {name}", code="unregistered-action"
        )
    return {
        "action": canonical,
        "requested_action": name,
        "requested_status": status,
        **copy.deepcopy(selected["actions"][canonical]),
    }


def _validate_scalar(value: Any, contract: Mapping[str, Any], *, path: str) -> Any:
    value_type = contract["type"]
    valid = False
    if value_type == "boolean":
        valid = isinstance(value, bool)
    elif value_type == "integer":
        valid = isinstance(value, int) and not isinstance(value, bool)
    elif value_type == "number":
        valid = (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and not (isinstance(value, float) and not math.isfinite(value))
        )
    elif value_type == "string":
        valid = isinstance(value, str)
    if not valid:
        raise VehicleActionRegistryError(
            f"{path} must be {value_type}", code="action-argument-type"
        )
    if "minimum" in contract and value < contract["minimum"]:
        raise VehicleActionRegistryError(
            f"{path} is below the minimum", code="action-argument-range"
        )
    if "maximum" in contract and value > contract["maximum"]:
        raise VehicleActionRegistryError(
            f"{path} exceeds the maximum", code="action-argument-range"
        )
    if "maximum_length" in contract and len(value.encode("utf-8")) > contract["maximum_length"]:
        raise VehicleActionRegistryError(
            f"{path} exceeds the maximum length", code="action-argument-length"
        )
    if "pattern" in contract and not re.fullmatch(contract["pattern"], value):
        raise VehicleActionRegistryError(
            f"{path} does not match the action contract", code="action-argument-pattern"
        )
    return copy.deepcopy(value)


def resolve_binding(
    binding: Any,
    *,
    carries_event_payload: Optional[bool] = None,
    registry: Optional[Mapping[str, Any]] = None,
    allow_legacy: bool = True,
) -> dict[str, Any]:
    """Resolve a canonical binding to one concrete runtime invocation.

    Legacy ``module``/``func`` bindings are returned unchanged when explicitly
    allowed.  Maintained bindings use ``action`` identifiers.
    """

    if not isinstance(binding, Mapping):
        raise VehicleActionRegistryError(
            "binding must be an object", code="invalid-binding"
        )
    if any(not isinstance(key, str) for key in binding):
        raise VehicleActionRegistryError(
            "binding contains an invalid field name", code="invalid-binding"
        )

    if "action" not in binding:
        if not allow_legacy:
            raise VehicleActionRegistryError(
                "maintained bindings must use a canonical action identifier",
                code="legacy-action-schema",
            )
        allowed = {"module", "func", "args"}
        unsupported = sorted(set(binding) - allowed)
        if unsupported:
            raise VehicleActionRegistryError(
                f"legacy binding contains unsupported fields: {', '.join(unsupported)}",
                code="unsupported-binding-field",
            )
        module = binding.get("module")
        func = binding.get("func")
        if not isinstance(module, str) or not PYTHON_IDENTIFIER_RE.fullmatch(module):
            raise VehicleActionRegistryError(
                "legacy binding module is invalid", code="invalid-module"
            )
        if not isinstance(func, str) or not PYTHON_IDENTIFIER_RE.fullmatch(func):
            raise VehicleActionRegistryError(
                "legacy binding function is invalid", code="invalid-func"
            )
        args = binding.get("args", [])
        if not isinstance(args, list) or len(args) > 16:
            raise VehicleActionRegistryError(
                "legacy binding args must contain at most 16 values",
                code="invalid-arguments",
            )
        normalized_args = []
        for index, value in enumerate(args):
            if (
                isinstance(value, (list, dict))
                or (isinstance(value, str) and len(value.encode("utf-8")) > 4096)
                or (isinstance(value, float) and not math.isfinite(value))
            ):
                raise VehicleActionRegistryError(
                    f"legacy binding args[{index}] must be a bounded JSON scalar",
                    code="invalid-argument",
                )
            normalized_args.append(copy.deepcopy(value))
        return {"module": module, "func": func, "args": normalized_args}

    allowed = {"action", "args"}
    unsupported = sorted(set(binding) - allowed)
    if unsupported:
        raise VehicleActionRegistryError(
            f"canonical binding contains unsupported fields: {', '.join(unsupported)}",
            code="unsupported-binding-field",
        )
    name = binding["action"]
    selected = normalize_registry(registry) if registry is not None else _default_registry()
    status, canonical = _action_status(name, selected)
    if status == "invalid":
        raise VehicleActionRegistryError(
            "binding action must be a lowercase dot-separated identifier",
            code="invalid-action",
        )
    if status == "alias" and canonical is not None:
        raise VehicleActionRegistryError(
            f"action alias {name!r} is deprecated; use {canonical!r}",
            code="deprecated-action-alias",
        )
    if status == "unknown" or canonical is None:
        raise VehicleActionRegistryError(
            (
                f"action is not registered: {name}; search with "
                "'open-mmi-config vehicle-setup actions --search <meaning>'"
            ),
            code="unregistered-action",
        )
    definition = selected["actions"][canonical]
    if definition["status"] == "deprecated":
        raise VehicleActionRegistryError(
            f"action {canonical!r} is deprecated", code="deprecated-action"
        )

    expects_payload = definition["event_payload"]["type"] != "none"
    if carries_event_payload is not None:
        if carries_event_payload and not expects_payload:
            raise VehicleActionRegistryError(
                f"action {canonical!r} does not accept an event payload",
                code="unexpected-action-payload",
            )
        if expects_payload and not carries_event_payload:
            raise VehicleActionRegistryError(
                f"action {canonical!r} requires an event payload",
                code="missing-action-payload",
            )

    args = binding.get("args", [])
    if not isinstance(args, list):
        raise VehicleActionRegistryError(
            "binding args must be an array", code="invalid-arguments"
        )
    contracts = definition["arguments"]
    required_count = sum(1 for item in contracts if item["required"])
    if not required_count <= len(args) <= len(contracts):
        raise VehicleActionRegistryError(
            f"action {canonical!r} accepts {required_count}..{len(contracts)} configured arguments",
            code="action-argument-count",
        )
    normalized_args = [
        _validate_scalar(value, contracts[index], path=f"binding.args[{index}]")
        for index, value in enumerate(args)
    ]
    implementation = definition["implementation"]
    return {
        "action": canonical,
        "module": implementation["module"],
        "func": implementation["func"],
        "args": normalized_args,
    }


def is_legacy_binding(binding: Any) -> bool:
    return isinstance(binding, Mapping) and "action" not in binding


def _search_tokens(query: Any) -> tuple[str, list[str]]:
    if not isinstance(query, str):
        raise VehicleActionRegistryError("action search query must be text")
    normalized = query.strip().lower()
    if (
        not normalized
        or len(normalized.encode("utf-8")) > 256
        or any(ord(character) < 32 for character in normalized)
    ):
        raise VehicleActionRegistryError("action search query must be bounded text")
    tokens = re.findall(r"[a-z0-9]+", normalized)
    if not tokens:
        raise VehicleActionRegistryError("action search query has no searchable terms")
    return normalized, tokens


def search_actions(
    query: Any,
    *,
    limit: int = 20,
    registry: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Search canonical actions using human wording rather than Python details."""

    normalized_query, tokens = _search_tokens(query)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise VehicleActionRegistryError("action search limit must be between 1 and 100")
    selected = normalize_registry(registry) if registry is not None else _default_registry()
    aliases_by_action: dict[str, list[str]] = {}
    for alias, definition in selected["aliases"].items():
        aliases_by_action.setdefault(definition["action"], []).append(alias)

    matches: list[tuple[int, str, dict[str, Any]]] = []
    for action, definition in selected["actions"].items():
        aliases = sorted(aliases_by_action.get(action, []))
        fields = {
            "action": action.lower(),
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
            if any(token in value.replace("_", " ").replace(".", " ") for token in tokens)
        )
        score = 0
        if normalized_query == action.lower():
            score += 100
        elif action.lower().startswith(normalized_query):
            score += 70
        for token in tokens:
            if token in action.lower().replace("_", " ").replace(".", " "):
                score += 20
            if token in definition["title"].lower():
                score += 12
            if token in definition["description"].lower():
                score += 6
            if any(token in term.lower() for term in definition.get("search_terms", [])):
                score += 8
            if token == definition["category"].lower():
                score += 4
            if any(token in alias.lower() for alias in aliases):
                score += 8
        public_definition = {
            key: copy.deepcopy(value)
            for key, value in definition.items()
            if key != "implementation"
        }
        matches.append(
            (
                -score,
                action,
                {
                    "action": action,
                    "matched_on": matched_on,
                    "aliases": aliases,
                    **public_definition,
                },
            )
        )

    ordered = [item for _, _, item in sorted(matches)[:limit]]
    return {
        "query": query.strip(),
        "count": len(ordered),
        "matches": ordered,
        "guidance": (
            "The action registry is a continuity checkpoint, not a walled garden. "
            "Reuse a matching human-readable behavior. If no result describes the "
            "needed local behavior, propose a new universal action and implementation "
            "in the same pull request."
        ),
    }


def contribution_check(
    name: Any,
    *,
    registry: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Explain whether to reuse, migrate, rename, or propose an action."""

    selected = normalize_registry(registry) if registry is not None else _default_registry()
    status, canonical = _action_status(name, selected)
    principles = [
        "The action registry is a continuity checkpoint, not a walled garden.",
        "Canonical actions describe human-visible behavior; Python modules, functions and executables remain implementation details.",
        "New universal actions may be proposed with their implementation, documentation and tests in the same pull request.",
    ]
    if status == "canonical" and canonical is not None:
        definition = {
            key: copy.deepcopy(value)
            for key, value in selected["actions"][canonical].items()
            if key != "implementation"
        }
        return {
            "requested_action": name,
            "status": status,
            "decision": "reuse",
            "action": canonical,
            "definition": definition,
            "message": "Reuse this canonical action; bindings should not name its Python implementation.",
            "principles": principles,
        }
    if status == "alias" and canonical is not None:
        definition = {
            key: copy.deepcopy(value)
            for key, value in selected["actions"][canonical].items()
            if key != "implementation"
        }
        return {
            "requested_action": name,
            "status": status,
            "decision": "use_canonical",
            "action": canonical,
            "definition": definition,
            "message": f"Use canonical action {canonical!r}; the requested name is a deprecated alias.",
            "principles": principles,
        }
    if status == "invalid":
        search_query = str(name).replace("_", " ").replace(":", " ").replace(".", " ")
        candidates = []
        try:
            candidates = search_actions(search_query, registry=selected)["matches"]
        except VehicleActionRegistryError:
            pass
        return {
            "requested_action": name,
            "status": status,
            "decision": "rename_before_proposal",
            "candidates": candidates,
            "message": (
                "Choose a lowercase dot-separated human-readable behavior before proposing it. "
                "Do not encode a Python module, function, command, package or vehicle name."
            ),
            "principles": principles,
        }

    search_query = str(name).replace("_", " ").replace(":", " ").replace(".", " ")
    candidates = search_actions(search_query, registry=selected)["matches"]
    return {
        "requested_action": name,
        "status": "unknown",
        "decision": "reuse_or_propose",
        "candidates": candidates,
        "message": (
            "No canonical action has this identifier. Reuse a candidate when its behavior matches. "
            "If the local behavior is genuinely new, add a universal action, implementation, "
            "documentation and tests in the same pull request."
        ),
        "principles": principles,
    }
