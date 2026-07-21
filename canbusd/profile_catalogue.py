"""Trusted maintained vehicle-profile catalogue resolution.

Maintained profiles may live in a human-browsable brand/model/generation tree.
Runtime callers address them by stable profile ID. A small checked catalogue maps
those identities (and deprecated aliases) to exact repository-relative files.
Custom profiles deliberately retain the flat user-owned ID layout.
"""

from __future__ import annotations

import copy
import json
import os
import re
import stat
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

SCHEMA_VERSION = 1
CATALOGUE_ID = "open-mmi.maintained-vehicles"
MAX_CATALOGUE_BYTES = 256 * 1024
IDENTIFIER_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
DEFAULT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CATALOGUE_PATH = DEFAULT_ROOT / "vehicles" / "catalogue.v1.json"


class VehicleProfileCatalogueError(ValueError):
    """Raised when the maintained catalogue cannot be trusted or resolved."""


def _object(
    value: Any,
    *,
    path: str,
    required: set[str],
    optional: Optional[set[str]] = None,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise VehicleProfileCatalogueError(f"{path} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise VehicleProfileCatalogueError(f"{path} contains an invalid field name")
    allowed = required | (optional or set())
    unknown = sorted(set(value) - allowed)
    missing = sorted(required - set(value))
    if unknown:
        raise VehicleProfileCatalogueError(
            f"{path} contains unsupported fields: {', '.join(unknown)}"
        )
    if missing:
        raise VehicleProfileCatalogueError(
            f"{path} is missing required fields: {', '.join(missing)}"
        )
    return value


def _unique_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise VehicleProfileCatalogueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise VehicleProfileCatalogueError(f"non-finite JSON number: {value}")


def _relative_profile_path(value: Any, *, path: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 240:
        raise VehicleProfileCatalogueError(f"{path} must be a bounded relative path")
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts or value.startswith("~"):
        raise VehicleProfileCatalogueError(f"{path} must stay beneath vehicles/")
    normalized = candidate.as_posix()
    if normalized.startswith("_") or not normalized.endswith("/config.json"):
        raise VehicleProfileCatalogueError(
            f"{path} must name a non-template */config.json file"
        )
    if any(part in {"", "."} or part.startswith(".") for part in candidate.parts):
        raise VehicleProfileCatalogueError(f"{path} contains an invalid component")
    return normalized




def _reject_symlink_components(root: Path, target: Path, *, label: str) -> None:
    """Reject symlinks in an exact maintained path, including existing parents."""

    base = root.expanduser().absolute()
    candidate = target.expanduser().absolute()
    try:
        relative = candidate.relative_to(base)
    except ValueError as exc:
        raise VehicleProfileCatalogueError(f"{label} escapes the maintained root") from exc

    current = base
    for part in relative.parts:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise VehicleProfileCatalogueError(f"{label} cannot be inspected") from exc
        if stat.S_ISLNK(mode):
            raise VehicleProfileCatalogueError(f"{label} contains a symlink: {current}")

def normalize_catalogue(value: Any) -> dict[str, Any]:
    document = _object(
        value,
        path="catalogue",
        required={"schema_version", "catalogue_id", "profiles"},
    )
    if document["schema_version"] != SCHEMA_VERSION or isinstance(
        document["schema_version"], bool
    ):
        raise VehicleProfileCatalogueError("catalogue.schema_version is unsupported")
    if document["catalogue_id"] != CATALOGUE_ID:
        raise VehicleProfileCatalogueError("catalogue.catalogue_id is unsupported")
    raw_profiles = document["profiles"]
    if not isinstance(raw_profiles, Mapping) or not raw_profiles:
        raise VehicleProfileCatalogueError("catalogue.profiles must be a non-empty object")

    profiles: dict[str, dict[str, Any]] = {}
    all_names: set[str] = set()
    all_paths: set[str] = set()
    for identifier in sorted(raw_profiles):
        if not isinstance(identifier, str) or not IDENTIFIER_RE.fullmatch(identifier):
            raise VehicleProfileCatalogueError(
                f"catalogue.profiles.{identifier} has an invalid identifier"
            )
        entry = _object(
            raw_profiles[identifier],
            path=f"catalogue.profiles.{identifier}",
            required={"path", "aliases"},
        )
        relative = _relative_profile_path(
            entry["path"], path=f"catalogue.profiles.{identifier}.path"
        )
        aliases = entry["aliases"]
        if not isinstance(aliases, list) or len(aliases) > 32:
            raise VehicleProfileCatalogueError(
                f"catalogue.profiles.{identifier}.aliases must be a bounded array"
            )
        normalized_aliases: list[str] = []
        for index, alias in enumerate(aliases):
            if not isinstance(alias, str) or not IDENTIFIER_RE.fullmatch(alias):
                raise VehicleProfileCatalogueError(
                    f"catalogue.profiles.{identifier}.aliases[{index}] is invalid"
                )
            if alias == identifier or alias in normalized_aliases:
                raise VehicleProfileCatalogueError(
                    f"catalogue.profiles.{identifier}.aliases contains a duplicate"
                )
            normalized_aliases.append(alias)
        names = {identifier, *normalized_aliases}
        conflict = sorted(names & all_names)
        if conflict:
            raise VehicleProfileCatalogueError(
                "catalogue profile identities are not unique: " + ", ".join(conflict)
            )
        if relative in all_paths:
            raise VehicleProfileCatalogueError(
                f"catalogue profile path is duplicated: {relative}"
            )
        all_names.update(names)
        all_paths.add(relative)
        profiles[identifier] = {
            "path": relative,
            "aliases": sorted(normalized_aliases),
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "catalogue_id": CATALOGUE_ID,
        "profiles": profiles,
    }


def load_catalogue(path: Path) -> dict[str, Any]:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise VehicleProfileCatalogueError(
            f"maintained vehicle catalogue cannot be inspected: {path}"
        ) from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size > MAX_CATALOGUE_BYTES
        or metadata.st_mode & 0o022
    ):
        raise VehicleProfileCatalogueError(
            "maintained vehicle catalogue must be a bounded non-writable regular file"
        )
    try:
        content = path.read_bytes()
        document = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VehicleProfileCatalogueError(
            "maintained vehicle catalogue is not valid UTF-8 JSON"
        ) from exc
    return normalize_catalogue(document)


@lru_cache(maxsize=8)
def _cached_catalogue(path_text: str, mtime_ns: int, size: int) -> dict[str, Any]:
    del mtime_ns, size
    return load_catalogue(Path(path_text))


def catalogue_payload(root: Path = DEFAULT_ROOT) -> dict[str, Any]:
    """Return the checked catalogue, or a legacy flat catalogue when absent.

    The fallback keeps older source/install trees and isolated tests readable. New
    maintained releases carry catalogue.v1.json and CI rejects orphaned profiles.
    """

    root = root.expanduser().absolute()
    path = root / "vehicles" / "catalogue.v1.json"
    if path.exists():
        _reject_symlink_components(root, path, label="maintained vehicle catalogue")
        try:
            metadata = path.stat()
        except OSError as exc:
            raise VehicleProfileCatalogueError(
                "maintained vehicle catalogue cannot be inspected"
            ) from exc
        return copy.deepcopy(
            _cached_catalogue(str(path), metadata.st_mtime_ns, metadata.st_size)
        )

    vehicles = root / "vehicles"
    profiles: dict[str, dict[str, Any]] = {}
    if vehicles.is_dir() and not vehicles.is_symlink():
        for child in sorted(vehicles.iterdir(), key=lambda item: item.name):
            if (
                child.is_dir()
                and not child.is_symlink()
                and IDENTIFIER_RE.fullmatch(child.name)
                and (child / "config.json").is_file()
            ):
                profiles[child.name] = {
                    "path": f"{child.name}/config.json",
                    "aliases": [],
                }
    return {
        "schema_version": SCHEMA_VERSION,
        "catalogue_id": CATALOGUE_ID,
        "profiles": profiles,
        "legacy_flat_fallback": True,
    }


def profile_entries(root: Path = DEFAULT_ROOT) -> list[dict[str, Any]]:
    catalogue = catalogue_payload(root)
    return [
        {"id": identifier, **copy.deepcopy(entry)}
        for identifier, entry in catalogue["profiles"].items()
    ]


def resolve_profile(root: Path, identifier: str) -> dict[str, Any]:
    if not isinstance(identifier, str) or not IDENTIFIER_RE.fullmatch(identifier):
        raise VehicleProfileCatalogueError("vehicle profile identifier is invalid")
    catalogue = catalogue_payload(root)
    canonical: Optional[str] = None
    requested_status = "canonical"
    if identifier in catalogue["profiles"]:
        canonical = identifier
    else:
        for candidate, entry in catalogue["profiles"].items():
            if identifier in entry["aliases"]:
                canonical = candidate
                requested_status = "alias"
                break
    if canonical is None and catalogue.get("legacy_flat_fallback"):
        canonical = identifier
        entry = {"path": f"{identifier}/config.json", "aliases": []}
    elif canonical is None:
        raise VehicleProfileCatalogueError(f"vehicle profile is not registered: {identifier}")
    else:
        entry = catalogue["profiles"][canonical]
    profile_path = root.expanduser().absolute() / "vehicles" / entry["path"]
    _reject_symlink_components(root, profile_path, label="maintained vehicle profile")
    return {
        "id": canonical,
        "requested_id": identifier,
        "requested_status": requested_status,
        "aliases": list(entry["aliases"]),
        "path": profile_path,
        "relative_path": f"vehicles/{entry['path']}",
    }


def verify_tree(root: Path = DEFAULT_ROOT) -> dict[str, Any]:
    """Verify manifest coverage, profile identity and symlink-free exact paths."""

    root = root.expanduser().absolute()
    catalogue = catalogue_payload(root)
    if catalogue.get("legacy_flat_fallback"):
        raise VehicleProfileCatalogueError(
            "maintained releases must provide vehicles/catalogue.v1.json"
        )
    vehicles = root / "vehicles"
    expected = {str(entry["path"]) for entry in catalogue["profiles"].values()}
    discovered: set[str] = set()
    issues: list[str] = []

    for current_text, directory_names, filenames in os.walk(
        vehicles, followlinks=False
    ):
        current = Path(current_text)
        relative_directory = current.relative_to(vehicles)
        if relative_directory.parts and relative_directory.parts[0] == "_template":
            directory_names[:] = []
            continue
        for directory_name in list(directory_names):
            directory = current / directory_name
            if directory.is_symlink():
                issues.append(
                    "symlinked catalogue directory: "
                    + directory.relative_to(vehicles).as_posix()
                )
                directory_names.remove(directory_name)
        if "config.json" in filenames:
            profile_path = current / "config.json"
            if profile_path.is_symlink():
                issues.append(
                    "symlinked profile file: "
                    + profile_path.relative_to(vehicles).as_posix()
                )
            else:
                discovered.add(profile_path.relative_to(vehicles).as_posix())

    missing = sorted(expected - discovered)
    orphaned = sorted(discovered - expected)
    if missing:
        issues.append("missing registered profiles: " + ", ".join(missing))
    if orphaned:
        issues.append("unregistered profile files: " + ", ".join(orphaned))
    for identifier in catalogue["profiles"]:
        try:
            resolved = resolve_profile(root, identifier)
        except VehicleProfileCatalogueError as exc:
            issues.append(str(exc))
            continue
        try:
            document = json.loads(resolved["path"].read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        metadata = document.get("metadata") if isinstance(document, Mapping) else None
        actual = metadata.get("id") if isinstance(metadata, Mapping) else None
        if actual != identifier:
            issues.append(
                f"profile ID mismatch for {resolved['relative_path']}: "
                f"{actual!r} != {identifier!r}"
            )
    return {
        "valid": not issues,
        "count": len(catalogue["profiles"]),
        "issues": issues,
        "profiles": profile_entries(root),
    }
