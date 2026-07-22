"""Maintained vehicle-profile admission and conformance reporting.

This module is deliberately stricter than normal custom-profile validation. Custom
profiles remain an open workspace for discovery. A profile entering the maintained
catalogue must also carry stable identity, maturity, evidence and qualification
metadata so users can understand exactly what has been tested.
"""

from __future__ import annotations

import copy
import json
import re
import stat
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from canbusd import profile_catalogue, profile_replay, status_registry
from ui import vehicle_setup


STANDARD_ID = "open-mmi.maintained-vehicle-profile"
SCHEMA_VERSION = 1
MAX_PROFILE_BYTES = 1024 * 1024
PROFILE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
MATURITY_LEVELS = {"experimental", "candidate", "qualified", "deprecated"}
QUALIFICATION_LEVELS = {"none", "replay", "hardware"}
EVIDENCE_KINDS = {"research", "capture", "replay", "hardware", "documentation"}
TOP_LEVEL_FIELDS = {
    "schema_version",
    "metadata",
    "default_bus",
    "can_buses",
    "rules",
    "presence",
    "status",
}
METADATA_FIELDS = {
    "id",
    "display_name",
    "manufacturer",
    "model",
    "generation",
    "platform",
    "model_years",
    "maturity",
    "license",
    "maintainers",
    "qualification",
    "limitations",
    "market_aliases",
}


class VehicleProfileConformanceError(ValueError):
    """Raised when a profile or maintained-catalogue root cannot be inspected."""


def _issue(level: str, code: str, path: str, message: str) -> dict[str, str]:
    return {"level": level, "code": code, "path": path, "message": message}


def _validation(issues: Iterable[Mapping[str, str]]) -> dict[str, Any]:
    ordered = [dict(issue) for issue in issues]
    errors = [issue for issue in ordered if issue["level"] == "error"]
    warnings = [issue for issue in ordered if issue["level"] == "warning"]
    return {"valid": not errors, "errors": errors, "warnings": warnings}


def _bounded_text(value: Any, maximum: int = 256) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and len(value.encode("utf-8")) <= maximum
        and not any(ord(character) < 32 for character in value)
    )


def _validate_text_list(
    value: Any,
    *,
    path: str,
    issues: list[dict[str, str]],
    minimum: int = 0,
    maximum: int = 32,
) -> list[str]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        issues.append(
            _issue(
                "error",
                "invalid-text-list",
                path,
                f"must be an array containing {minimum} to {maximum} bounded strings",
            )
        )
        return []
    result: list[str] = []
    for index, item in enumerate(value):
        if not _bounded_text(item, 256):
            issues.append(
                _issue(
                    "error",
                    "invalid-text",
                    f"{path}[{index}]",
                    "must be a non-empty bounded string",
                )
            )
            continue
        result.append(item.strip())
    if len(set(result)) != len(result):
        issues.append(
            _issue("error", "duplicate-value", path, "must not contain duplicates")
        )
    return result


def _date_text(value: Any, *, path: str, issues: list[dict[str, str]]) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        issues.append(_issue("error", "invalid-date", path, "must be YYYY-MM-DD or null"))
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        issues.append(_issue("error", "invalid-date", path, "must be YYYY-MM-DD or null"))
        return None
    if parsed.year < 2000 or parsed.year > 2100:
        issues.append(_issue("error", "invalid-date", path, "must use a plausible qualification year"))
    return value


def _relative_evidence_path(value: Any, *, path: str, issues: list[dict[str, str]]) -> Optional[str]:
    if not _bounded_text(value, 240):
        issues.append(_issue("error", "invalid-evidence-path", path, "must be a bounded repository-relative path"))
        return None
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts or value.startswith("~"):
        issues.append(_issue("error", "invalid-evidence-path", path, "must stay within the repository"))
        return None
    normalized = candidate.as_posix()
    if normalized in {"", "."}:
        issues.append(_issue("error", "invalid-evidence-path", path, "must name an evidence file"))
        return None
    return normalized


def validate_metadata(
    document: Any,
    *,
    expected_id: Optional[str] = None,
) -> dict[str, Any]:
    """Validate the maintained-profile identity and qualification envelope."""

    issues: list[dict[str, str]] = []
    if not isinstance(document, Mapping):
        return _validation([_issue("error", "invalid-document", "$", "profile must be a JSON object")])

    unknown_top = sorted(set(document) - TOP_LEVEL_FIELDS)
    for field in unknown_top:
        issues.append(
            _issue(
                "error",
                "unsupported-profile-field",
                field,
                "is not part of maintained profile schema version 1",
            )
        )

    schema_version = document.get("schema_version")
    if isinstance(schema_version, bool) or schema_version != SCHEMA_VERSION:
        issues.append(
            _issue(
                "error",
                "unsupported-profile-schema",
                "schema_version",
                "must be integer 1",
            )
        )

    metadata = document.get("metadata")
    if not isinstance(metadata, Mapping):
        issues.append(
            _issue(
                "error",
                "missing-profile-metadata",
                "metadata",
                "is required for maintained catalogue admission",
            )
        )
        return _validation(issues)

    unknown_metadata = sorted(set(metadata) - METADATA_FIELDS)
    for field in unknown_metadata:
        issues.append(
            _issue(
                "error",
                "unsupported-metadata-field",
                f"metadata.{field}",
                "is not part of maintained profile schema version 1",
            )
        )

    required = METADATA_FIELDS - {"limitations", "market_aliases"}
    for field in sorted(required - set(metadata)):
        issues.append(
            _issue("error", "missing-metadata-field", f"metadata.{field}", "is required")
        )

    profile_id = metadata.get("id")
    if not isinstance(profile_id, str) or not PROFILE_ID_RE.fullmatch(profile_id):
        issues.append(
            _issue(
                "error",
                "invalid-profile-id",
                "metadata.id",
                "must match ^[a-z0-9][a-z0-9_-]{0,63}$",
            )
        )
    elif expected_id is not None and profile_id != expected_id:
        issues.append(
            _issue(
                "error",
                "profile-id-mismatch",
                "metadata.id",
                f"must match maintained catalogue identity {expected_id!r}",
            )
        )

    for field in (
        "display_name",
        "manufacturer",
        "model",
        "generation",
        "platform",
    ):
        if not _bounded_text(metadata.get(field), 128):
            issues.append(
                _issue(
                    "error",
                    "invalid-metadata-text",
                    f"metadata.{field}",
                    "must be a non-empty bounded human-readable string",
                )
            )

    if metadata.get("license") != "GPL-3.0-only":
        issues.append(
            _issue(
                "error",
                "invalid-profile-license",
                "metadata.license",
                "must be GPL-3.0-only for maintained catalogue content",
            )
        )

    years = metadata.get("model_years")
    if not isinstance(years, Mapping) or set(years) != {"from", "to"}:
        issues.append(
            _issue(
                "error",
                "invalid-model-years",
                "metadata.model_years",
                "must contain exactly from and to years",
            )
        )
    else:
        start = years.get("from")
        end = years.get("to")
        valid_start = isinstance(start, int) and not isinstance(start, bool) and 1886 <= start <= 2100
        valid_end = isinstance(end, int) and not isinstance(end, bool) and 1886 <= end <= 2100
        if not valid_start or not valid_end or start > end:
            issues.append(
                _issue(
                    "error",
                    "invalid-model-years",
                    "metadata.model_years",
                    "must contain an ordered inclusive year range from 1886 to 2100",
                )
            )

    maturity = metadata.get("maturity")
    if maturity not in MATURITY_LEVELS:
        issues.append(
            _issue(
                "error",
                "invalid-profile-maturity",
                "metadata.maturity",
                "must be experimental, candidate, qualified or deprecated",
            )
        )

    _validate_text_list(
        metadata.get("maintainers"),
        path="metadata.maintainers",
        issues=issues,
        minimum=1,
        maximum=16,
    )
    if "market_aliases" in metadata:
        _validate_text_list(
            metadata.get("market_aliases"),
            path="metadata.market_aliases",
            issues=issues,
            maximum=32,
        )
    if "limitations" in metadata:
        _validate_text_list(
            metadata.get("limitations"),
            path="metadata.limitations",
            issues=issues,
            maximum=32,
        )

    qualification = metadata.get("qualification")
    if not isinstance(qualification, Mapping):
        issues.append(
            _issue(
                "error",
                "invalid-qualification",
                "metadata.qualification",
                "must contain level, last_tested, scope and evidence",
            )
        )
        return _validation(issues)

    expected_qualification_fields = {"level", "last_tested", "scope", "evidence"}
    if set(qualification) != expected_qualification_fields:
        issues.append(
            _issue(
                "error",
                "invalid-qualification-fields",
                "metadata.qualification",
                "must contain exactly level, last_tested, scope and evidence",
            )
        )

    level = qualification.get("level")
    if level not in QUALIFICATION_LEVELS:
        issues.append(
            _issue(
                "error",
                "invalid-qualification-level",
                "metadata.qualification.level",
                "must be none, replay or hardware",
            )
        )

    last_tested = _date_text(
        qualification.get("last_tested"),
        path="metadata.qualification.last_tested",
        issues=issues,
    )
    scope = _validate_text_list(
        qualification.get("scope"),
        path="metadata.qualification.scope",
        issues=issues,
        maximum=32,
    )

    raw_evidence = qualification.get("evidence")
    evidence_kinds: list[str] = []
    if not isinstance(raw_evidence, list) or len(raw_evidence) > 64:
        issues.append(
            _issue(
                "error",
                "invalid-evidence",
                "metadata.qualification.evidence",
                "must be an array of at most 64 evidence records",
            )
        )
        raw_evidence = []
    for index, item in enumerate(raw_evidence):
        path = f"metadata.qualification.evidence[{index}]"
        if not isinstance(item, Mapping) or set(item) != {"kind", "path", "description"}:
            issues.append(
                _issue(
                    "error",
                    "invalid-evidence-record",
                    path,
                    "must contain exactly kind, path and description",
                )
            )
            continue
        kind = item.get("kind")
        if kind not in EVIDENCE_KINDS:
            issues.append(
                _issue(
                    "error",
                    "invalid-evidence-kind",
                    f"{path}.kind",
                    "must be research, capture, replay, hardware or documentation",
                )
            )
        else:
            evidence_kinds.append(kind)
        _relative_evidence_path(item.get("path"), path=f"{path}.path", issues=issues)
        if not _bounded_text(item.get("description"), 512):
            issues.append(
                _issue(
                    "error",
                    "invalid-evidence-description",
                    f"{path}.description",
                    "must be a non-empty bounded human-readable description",
                )
            )

    if level == "none":
        if last_tested is not None or scope or raw_evidence:
            issues.append(
                _issue(
                    "error",
                    "unexpected-qualification-evidence",
                    "metadata.qualification",
                    "level none must use null last_tested and empty scope/evidence",
                )
            )
    elif level in {"replay", "hardware"}:
        if last_tested is None:
            issues.append(
                _issue(
                    "error",
                    "missing-qualification-date",
                    "metadata.qualification.last_tested",
                    "is required for replay or hardware qualification",
                )
            )
        if not scope:
            issues.append(
                _issue(
                    "error",
                    "missing-qualification-scope",
                    "metadata.qualification.scope",
                    "must state exactly what was tested",
                )
            )
        if not raw_evidence:
            issues.append(
                _issue(
                    "error",
                    "missing-qualification-evidence",
                    "metadata.qualification.evidence",
                    "must reference reviewable evidence",
                )
            )

    if maturity == "candidate" and level not in {"replay", "hardware"}:
        issues.append(
            _issue(
                "error",
                "candidate-without-qualification",
                "metadata.maturity",
                "candidate profiles require replay or hardware qualification",
            )
        )
    if maturity == "candidate" and not ({"replay", "hardware"} & set(evidence_kinds)):
        issues.append(
            _issue(
                "error",
                "candidate-without-test-evidence",
                "metadata.qualification.evidence",
                "candidate profiles require replay or hardware evidence",
            )
        )
    if maturity == "qualified" and level != "hardware":
        issues.append(
            _issue(
                "error",
                "qualified-without-hardware",
                "metadata.maturity",
                "qualified profiles require hardware qualification",
            )
        )
    if maturity == "qualified" and "hardware" not in evidence_kinds:
        issues.append(
            _issue(
                "error",
                "qualified-without-hardware-evidence",
                "metadata.qualification.evidence",
                "qualified profiles require at least one hardware evidence record",
            )
        )

    return _validation(issues)


def _unique_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise VehicleProfileConformanceError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise VehicleProfileConformanceError(f"non-finite JSON number: {value}")


def _read_profile(path: Path) -> Mapping[str, Any]:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise VehicleProfileConformanceError(f"cannot inspect profile: {path}") from exc
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_PROFILE_BYTES:
        raise VehicleProfileConformanceError(f"profile must be a bounded regular file: {path}")
    try:
        content = path.read_bytes()
        document = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VehicleProfileConformanceError(f"profile is not valid UTF-8 JSON: {path}") from exc
    if not isinstance(document, Mapping):
        raise VehicleProfileConformanceError(f"profile root must be an object: {path}")
    return document


def _evidence_issues(
    document: Mapping[str, Any],
    *,
    root: Path,
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    metadata = document.get("metadata")
    if not isinstance(metadata, Mapping):
        return issues
    qualification = metadata.get("qualification")
    if not isinstance(qualification, Mapping):
        return issues
    evidence = qualification.get("evidence")
    if not isinstance(evidence, list):
        return issues
    root_resolved = root.resolve()
    for index, record in enumerate(evidence):
        if not isinstance(record, Mapping):
            continue
        relative = record.get("path")
        if not isinstance(relative, str):
            continue
        candidate = root / relative
        try:
            resolved = candidate.resolve(strict=True)
            mode = candidate.lstat().st_mode
        except OSError:
            issues.append(
                _issue(
                    "error",
                    "missing-evidence-file",
                    f"metadata.qualification.evidence[{index}].path",
                    f"does not exist beneath the catalogue root: {relative}",
                )
            )
            continue
        if root_resolved not in (resolved, *resolved.parents) or not stat.S_ISREG(mode):
            issues.append(
                _issue(
                    "error",
                    "untrusted-evidence-file",
                    f"metadata.qualification.evidence[{index}].path",
                    "must resolve to a regular file beneath the catalogue root",
                )
            )
    return issues


def _event_names(document: Mapping[str, Any]) -> list[str]:
    events: set[str] = set()
    rules = document.get("rules")
    if isinstance(rules, list):
        for rule in rules:
            if isinstance(rule, Mapping) and isinstance(rule.get("event"), str):
                events.add(rule["event"])
    presence = document.get("presence")
    if isinstance(presence, list):
        for rule in presence:
            if not isinstance(rule, Mapping):
                continue
            for key in ("on_present", "on_absent"):
                if isinstance(rule.get(key), str):
                    events.add(rule[key])
    return sorted(events)


def _fixture_report(
    document: Mapping[str, Any],
    *,
    profile_path: Path,
    identifier: str,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    fixture_path = profile_path.parent / "fixtures" / "mappings.v1.json"
    metadata = document.get("metadata")
    maturity = metadata.get("maturity") if isinstance(metadata, Mapping) else None
    issues: list[dict[str, str]] = []
    if not fixture_path.exists():
        level = "error" if maturity in {"candidate", "qualified"} else "warning"
        issues.append(
            _issue(
                level,
                "missing-mapping-fixtures",
                "fixtures/mappings.v1.json",
                "candidate and qualified profiles require deterministic mapping fixtures",
            )
        )
        return {
            "present": False,
            "valid": maturity not in {"candidate", "qualified"},
            "path": "fixtures/mappings.v1.json",
            "case_count": 0,
            "coverage": {},
        }, issues
    try:
        fixture = profile_replay.load_json(fixture_path)
        report = profile_replay.replay_fixture(
            document,
            fixture,
            expected_profile_id=identifier,
        )
    except profile_replay.VehicleProfileReplayError as exc:
        issues.append(
            _issue(
                "error",
                "invalid-mapping-fixtures",
                "fixtures/mappings.v1.json",
                str(exc),
            )
        )
        return {
            "present": True,
            "valid": False,
            "path": "fixtures/mappings.v1.json",
            "case_count": 0,
            "coverage": {},
        }, issues
    if not report["valid"]:
        coverage = report["coverage"]
        missing = [*coverage["missing_events"], *coverage["missing_statuses"]]
        failed = [case["name"] for case in report["cases"] if not case["valid"]]
        message_parts = []
        if missing:
            message_parts.append("missing coverage: " + ", ".join(missing))
        if failed:
            message_parts.append("failed cases: " + ", ".join(failed))
        if coverage["unexpected_events"] or coverage["unexpected_statuses"]:
            message_parts.append("fixture declares outputs not produced by the profile")
        issues.append(
            _issue(
                "error",
                "mapping-fixture-failed",
                "fixtures/mappings.v1.json",
                "; ".join(message_parts) or "mapping replay did not pass",
            )
        )
    return {
        "present": True,
        "valid": bool(report["valid"]),
        "path": "fixtures/mappings.v1.json",
        "case_count": report["case_count"],
        "coverage": copy.deepcopy(report["coverage"]),
    }, issues


def profile_report(
    path: Path,
    *,
    root: Path,
    expected_id: Optional[str] = None,
    check_evidence_files: bool = True,
    as_of: Optional[date] = None,
) -> dict[str, Any]:
    document = _read_profile(path)
    identifier = expected_id or path.parent.name
    technical = vehicle_setup.validate_profile(document)
    metadata = validate_metadata(document, expected_id=identifier)
    issues = [*technical["errors"], *technical["warnings"], *metadata["errors"], *metadata["warnings"]]
    if check_evidence_files:
        issues.extend(_evidence_issues(document, root=root))
    fixtures, fixture_issues = _fixture_report(
        document,
        profile_path=path,
        identifier=identifier,
    )
    issues.extend(fixture_issues)
    from ui import vehicle_profile_qualification

    qualification_record = vehicle_profile_qualification.qualification_report_for_profile(
        document,
        profile_path=path,
        fixtures=fixtures,
        expected_profile_id=identifier,
        as_of=as_of,
    )
    issues.extend(qualification_record["validation"]["errors"])
    issues.extend(qualification_record["validation"]["warnings"])
    validation = _validation(issues)

    metadata_document = document.get("metadata")
    safe_metadata = copy.deepcopy(metadata_document) if isinstance(metadata_document, Mapping) else {}
    outputs = status_registry.profile_outputs(document)
    canonical_statuses = sorted(
        {
            str(item["path"])
            for item in outputs
            if item.get("role") != "alias" and isinstance(item.get("path"), str)
        }
    )
    buses = document.get("can_buses")
    bus_names = sorted(str(name) for name in buses) if isinstance(buses, Mapping) else []
    return {
        "id": identifier,
        "path": path.relative_to(root).as_posix(),
        "valid": validation["valid"],
        "metadata": safe_metadata,
        "capabilities": {
            "buses": bus_names,
            "events": _event_names(document),
            "statuses": canonical_statuses,
            "event_count": len(_event_names(document)),
            "status_count": len(canonical_statuses),
        },
        "fixtures": fixtures,
        "qualification": qualification_record,
        "validation": validation,
    }


def catalogue_report(
    root: Path,
    *,
    identifiers: Optional[Sequence[str]] = None,
    check_evidence_files: bool = True,
    as_of: Optional[date] = None,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    vehicles = root / "vehicles"
    if not vehicles.is_dir() or vehicles.is_symlink():
        raise VehicleProfileConformanceError(
            f"maintained vehicle catalogue is not a trusted directory: {vehicles}"
        )
    try:
        tree = profile_catalogue.verify_tree(root)
        entries = profile_catalogue.profile_entries(root)
    except profile_catalogue.VehicleProfileCatalogueError as exc:
        raise VehicleProfileConformanceError(str(exc)) from exc

    by_id = {str(entry["id"]): entry for entry in entries}
    requested: list[str]
    if identifiers:
        requested = []
        for item in identifiers:
            if not PROFILE_ID_RE.fullmatch(item):
                raise VehicleProfileConformanceError(
                    f"invalid profile identifier: {item}"
                )
            try:
                resolved = profile_catalogue.resolve_profile(root, item)
            except profile_catalogue.VehicleProfileCatalogueError as exc:
                raise VehicleProfileConformanceError(str(exc)) from exc
            canonical = str(resolved["id"])
            if canonical not in requested:
                requested.append(canonical)
    else:
        requested = sorted(by_id)

    profiles: list[dict[str, Any]] = []
    for identifier in requested:
        entry = by_id[identifier]
        path = root / "vehicles" / str(entry["path"])
        try:
            report = profile_report(
                path,
                root=root,
                expected_id=identifier,
                check_evidence_files=check_evidence_files,
                as_of=as_of,
            )
            report["aliases"] = list(entry["aliases"])
            profiles.append(report)
        except VehicleProfileConformanceError as exc:
            profiles.append(
                {
                    "id": identifier,
                    "aliases": list(entry["aliases"]),
                    "path": f"vehicles/{entry['path']}",
                    "valid": False,
                    "metadata": {},
                    "capabilities": {
                        "buses": [],
                        "events": [],
                        "statuses": [],
                        "event_count": 0,
                        "status_count": 0,
                    },
                    "fixtures": {
                        "present": False,
                        "valid": False,
                        "case_count": 0,
                        "coverage": {},
                    },
                    "qualification": {
                        "present": False,
                        "stale": False,
                        "validation": _validation([]),
                    },
                    "validation": _validation(
                        [_issue("error", "unreadable-profile", "$", str(exc))]
                    ),
                }
            )

    if tree["issues"]:
        profiles.append(
            {
                "id": "_catalogue",
                "aliases": [],
                "path": "vehicles/catalogue.v1.json",
                "valid": False,
                "metadata": {},
                "capabilities": {
                    "buses": [], "events": [], "statuses": [],
                    "event_count": 0, "status_count": 0,
                },
                "fixtures": {"present": False, "valid": False, "case_count": 0, "coverage": {}},
                "qualification": {"present": False, "stale": False, "validation": _validation([])},
                "validation": _validation([
                    _issue("error", "invalid-catalogue-tree", "vehicles", issue)
                    for issue in tree["issues"]
                ]),
            }
        )

    maturity_counts = Counter(
        str(profile.get("metadata", {}).get("maturity") or "missing")
        for profile in profiles
        if profile["id"] != "_catalogue"
    )
    valid = bool(profiles) and all(profile["valid"] for profile in profiles)
    return {
        "standard": STANDARD_ID,
        "schema_version": SCHEMA_VERSION,
        "valid": valid,
        "count": len([profile for profile in profiles if profile["id"] != "_catalogue"]),
        "summary": {
            "valid": sum(1 for profile in profiles if profile["valid"]),
            "invalid": sum(1 for profile in profiles if not profile["valid"]),
            "maturity": dict(sorted(maturity_counts.items())),
        },
        "profiles": profiles,
        "guidance": (
            "This is a catalogue continuity, replay and evidence checkpoint, not permission to "
            "research a vehicle. Discovery and custom profiles remain open; a maintained "
            "profile must state its identity, maturity, test scope and reviewable evidence."
        ),
    }
