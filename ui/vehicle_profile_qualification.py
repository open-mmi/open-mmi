"""Formal maintained vehicle-profile qualification records and transitions.

Qualification records live beside each maintained profile under
``evidence/qualification.v1.json``.  They record the current review state,
compatibility boundary and transition history without changing the open custom
profile workflow.
"""

from __future__ import annotations

import copy
import json
import os
import re
import stat
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from canbusd import profile_catalogue, profile_replay


RECORD_ID = "open-mmi.vehicle-profile-qualification"
SCHEMA_VERSION = 1
RECORD_NAME = "qualification.v1.json"
MAX_RECORD_BYTES = 256 * 1024
LEVELS = ("none", "replay", "hardware")
LEVEL_RANK = {level: index for index, level in enumerate(LEVELS)}
REVIEW_STATUSES = {"unreviewed", "approved"}
EVIDENCE_KINDS = {"research", "capture", "replay", "hardware", "documentation"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class VehicleProfileQualificationError(ValueError):
    """Raised when a qualification record or transition is unsafe."""


def _issue(level: str, code: str, path: str, message: str) -> dict[str, str]:
    return {"level": level, "code": code, "path": path, "message": message}


def _validation(issues: Iterable[Mapping[str, str]]) -> dict[str, Any]:
    ordered = [dict(issue) for issue in issues]
    errors = [item for item in ordered if item["level"] == "error"]
    warnings = [item for item in ordered if item["level"] == "warning"]
    return {"valid": not errors, "errors": errors, "warnings": warnings}


def _bounded_text(value: Any, maximum: int = 512) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and len(value.encode("utf-8")) <= maximum
        and not any(ord(character) < 32 for character in value)
    )


def _text_list(
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
                f"must contain {minimum} to {maximum} bounded strings",
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
        issues.append(_issue("error", "duplicate-value", path, "must not contain duplicates"))
    return result


def _date_value(
    value: Any,
    *,
    path: str,
    issues: list[dict[str, str]],
    nullable: bool,
) -> Optional[date]:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not DATE_RE.fullmatch(value):
        issues.append(_issue("error", "invalid-date", path, "must be YYYY-MM-DD" + (" or null" if nullable else "")))
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        issues.append(_issue("error", "invalid-date", path, "must be a real calendar date"))
        return None
    if parsed.year < 2000 or parsed.year > 2100:
        issues.append(_issue("error", "invalid-date", path, "must use a plausible qualification year"))
    return parsed


def record_path(profile_path: Path) -> Path:
    return profile_path.parent / "evidence" / RECORD_NAME


def default_record(profile_id: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "record_id": RECORD_ID,
        "profile_id": profile_id,
        "current": {
            "level": "none",
            "tested_on": None,
            "scope": [],
            "compatibility": {"equipment": [], "variants": []},
            "review": {
                "status": "unreviewed",
                "reviewers": [],
                "reviewed_on": None,
                "recheck_after": None,
            },
        },
        "history": [],
    }


def _read_json(path: Path) -> Mapping[str, Any]:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise VehicleProfileQualificationError(f"qualification record is missing: {path}") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise VehicleProfileQualificationError(f"qualification record must be a regular file: {path}")
    if metadata.st_size > MAX_RECORD_BYTES:
        raise VehicleProfileQualificationError(f"qualification record is too large: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VehicleProfileQualificationError(f"qualification record is not valid UTF-8 JSON: {path}") from exc
    if not isinstance(payload, Mapping):
        raise VehicleProfileQualificationError("qualification record root must be an object")
    return payload


def load_record(path: Path) -> Mapping[str, Any]:
    return _read_json(path)


def _fixture_complete(fixtures: Mapping[str, Any]) -> bool:
    coverage = fixtures.get("coverage")
    if not fixtures.get("present") or not fixtures.get("valid") or not isinstance(coverage, Mapping):
        return False
    return not any(
        coverage.get(key)
        for key in (
            "missing_events",
            "missing_statuses",
            "unexpected_events",
            "unexpected_statuses",
        )
    )


def validate_record(
    record: Any,
    *,
    document: Mapping[str, Any],
    fixtures: Mapping[str, Any],
    expected_profile_id: str,
    as_of: Optional[date] = None,
) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    if not isinstance(record, Mapping):
        return {"record": {}, "stale": False, "validation": _validation([
            _issue("error", "invalid-qualification-record", "$", "must be a JSON object")
        ])}

    if set(record) != {"schema_version", "record_id", "profile_id", "current", "history"}:
        issues.append(_issue("error", "invalid-qualification-record-fields", "$", "must contain exactly schema_version, record_id, profile_id, current and history"))
    if record.get("schema_version") != SCHEMA_VERSION:
        issues.append(_issue("error", "unsupported-qualification-schema", "schema_version", "must be integer 1"))
    if record.get("record_id") != RECORD_ID:
        issues.append(_issue("error", "invalid-qualification-record-id", "record_id", f"must be {RECORD_ID!r}"))
    if record.get("profile_id") != expected_profile_id:
        issues.append(_issue("error", "qualification-profile-mismatch", "profile_id", f"must match {expected_profile_id!r}"))

    current = record.get("current")
    if not isinstance(current, Mapping):
        issues.append(_issue("error", "invalid-qualification-current", "current", "must be an object"))
        current = {}
    elif set(current) != {"level", "tested_on", "scope", "compatibility", "review"}:
        issues.append(_issue("error", "invalid-qualification-current-fields", "current", "must contain exactly level, tested_on, scope, compatibility and review"))

    level = current.get("level")
    if level not in LEVELS:
        issues.append(_issue("error", "invalid-qualification-level", "current.level", "must be none, replay or hardware"))
    tested_on = _date_value(current.get("tested_on"), path="current.tested_on", issues=issues, nullable=True)
    scope = _text_list(current.get("scope"), path="current.scope", issues=issues, maximum=32)

    compatibility = current.get("compatibility")
    if not isinstance(compatibility, Mapping) or set(compatibility) != {"equipment", "variants"}:
        issues.append(_issue("error", "invalid-qualification-compatibility", "current.compatibility", "must contain exactly equipment and variants"))
        compatibility = {}
    equipment = _text_list(compatibility.get("equipment"), path="current.compatibility.equipment", issues=issues, maximum=32)
    variants = _text_list(compatibility.get("variants"), path="current.compatibility.variants", issues=issues, maximum=32)

    review = current.get("review")
    if not isinstance(review, Mapping) or set(review) != {"status", "reviewers", "reviewed_on", "recheck_after"}:
        issues.append(_issue("error", "invalid-qualification-review", "current.review", "must contain exactly status, reviewers, reviewed_on and recheck_after"))
        review = {}
    review_status = review.get("status")
    if review_status not in REVIEW_STATUSES:
        issues.append(_issue("error", "invalid-review-status", "current.review.status", "must be unreviewed or approved"))
    reviewers = _text_list(review.get("reviewers"), path="current.review.reviewers", issues=issues, maximum=16)
    reviewed_on = _date_value(review.get("reviewed_on"), path="current.review.reviewed_on", issues=issues, nullable=True)
    recheck_after = _date_value(review.get("recheck_after"), path="current.review.recheck_after", issues=issues, nullable=True)

    history = record.get("history")
    if not isinstance(history, list) or len(history) > 64:
        issues.append(_issue("error", "invalid-qualification-history", "history", "must be an array of at most 64 transitions"))
        history = []
    normalized_history: list[Mapping[str, Any]] = []
    for index, item in enumerate(history):
        path = f"history[{index}]"
        if not isinstance(item, Mapping) or set(item) != {"from", "to", "date", "reason", "reviewers"}:
            issues.append(_issue("error", "invalid-qualification-transition", path, "must contain exactly from, to, date, reason and reviewers"))
            continue
        source = item.get("from")
        target = item.get("to")
        if source not in LEVELS or target not in LEVELS or source == target:
            issues.append(_issue("error", "invalid-qualification-transition-levels", path, "must move between distinct qualification levels"))
        elif LEVEL_RANK[target] > LEVEL_RANK[source] + 1:
            issues.append(_issue("error", "skipped-qualification-stage", path, "promotion must advance one stage at a time"))
        _date_value(item.get("date"), path=f"{path}.date", issues=issues, nullable=False)
        if not _bounded_text(item.get("reason"), 512):
            issues.append(_issue("error", "invalid-transition-reason", f"{path}.reason", "must be a bounded non-empty explanation"))
        _text_list(item.get("reviewers"), path=f"{path}.reviewers", issues=issues, minimum=1, maximum=16)
        normalized_history.append(item)

    metadata = document.get("metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    qualification = metadata.get("qualification")
    qualification = qualification if isinstance(qualification, Mapping) else {}
    maturity = metadata.get("maturity")
    if qualification.get("level") != level:
        issues.append(_issue("error", "qualification-level-mismatch", "current.level", "must match metadata.qualification.level"))
    expected_tested = tested_on.isoformat() if tested_on else None
    if qualification.get("last_tested") != expected_tested:
        issues.append(_issue("error", "qualification-date-mismatch", "current.tested_on", "must match metadata.qualification.last_tested"))
    if qualification.get("scope") != scope:
        issues.append(_issue("error", "qualification-scope-mismatch", "current.scope", "must match metadata.qualification.scope"))

    evidence = qualification.get("evidence")
    evidence = evidence if isinstance(evidence, list) else []
    evidence_kinds = {
        item.get("kind")
        for item in evidence
        if isinstance(item, Mapping) and item.get("kind") in EVIDENCE_KINDS
    }

    if level == "none":
        if tested_on is not None or scope or equipment or variants:
            issues.append(_issue("error", "unexpected-unqualified-detail", "current", "level none must have no tested scope or compatibility claims"))
        if review_status != "unreviewed" or reviewers or reviewed_on is not None or recheck_after is not None:
            issues.append(_issue("error", "unexpected-unqualified-review", "current.review", "level none must remain unreviewed"))
        if maturity not in {"experimental", "deprecated"}:
            issues.append(_issue("error", "unqualified-maturity-mismatch", "metadata.maturity", "level none requires experimental or deprecated maturity"))
    else:
        if tested_on is None or not scope:
            issues.append(_issue("error", "incomplete-qualified-scope", "current", "replay and hardware levels require a tested date and scope"))
        if review_status != "approved" or not reviewers or reviewed_on is None or recheck_after is None:
            issues.append(_issue("error", "missing-approved-review", "current.review", "replay and hardware levels require approved reviewer sign-off and a recheck date"))
        if tested_on and reviewed_on and reviewed_on < tested_on:
            issues.append(_issue("error", "review-before-test", "current.review.reviewed_on", "cannot be earlier than tested_on"))
        if reviewed_on and recheck_after and recheck_after <= reviewed_on:
            issues.append(_issue("error", "invalid-recheck-date", "current.review.recheck_after", "must be later than reviewed_on"))
        if not _fixture_complete(fixtures):
            issues.append(_issue("error", "qualification-without-complete-replay", "fixtures/mappings.v1.json", "replay and hardware qualification require complete passing fixture coverage"))
        if "replay" not in evidence_kinds:
            issues.append(_issue("error", "qualification-without-replay-evidence", "metadata.qualification.evidence", "replay and hardware qualification require replay evidence"))
        if not normalized_history or normalized_history[-1].get("to") != level:
            issues.append(_issue("error", "qualification-history-mismatch", "history", "latest transition must end at the current level"))

    if level == "replay":
        if maturity != "candidate":
            issues.append(_issue("error", "replay-maturity-mismatch", "metadata.maturity", "replay qualification requires candidate maturity"))
    elif level == "hardware":
        if maturity != "qualified":
            issues.append(_issue("error", "hardware-maturity-mismatch", "metadata.maturity", "hardware qualification requires qualified maturity"))
        if "hardware" not in evidence_kinds:
            issues.append(_issue("error", "hardware-without-hardware-evidence", "metadata.qualification.evidence", "hardware qualification requires hardware evidence"))
        if not equipment or not variants:
            issues.append(_issue("error", "hardware-without-compatibility-boundary", "current.compatibility", "hardware qualification must name tested equipment and vehicle variants"))

    selected_as_of = as_of or date.today()
    stale = bool(recheck_after and selected_as_of > recheck_after)
    if stale:
        issues.append(_issue("warning", "qualification-stale", "current.review.recheck_after", f"qualification review expired on {recheck_after.isoformat()}"))

    return {
        "record": copy.deepcopy(dict(record)),
        "level": level,
        "tested_on": expected_tested,
        "review_status": review_status,
        "reviewers": list(reviewers),
        "reviewed_on": reviewed_on.isoformat() if reviewed_on else None,
        "recheck_after": recheck_after.isoformat() if recheck_after else None,
        "compatibility": {"equipment": list(equipment), "variants": list(variants)},
        "history_count": len(history),
        "stale": stale,
        "validation": _validation(issues),
    }


def qualification_report_for_profile(
    document: Mapping[str, Any],
    *,
    profile_path: Path,
    fixtures: Mapping[str, Any],
    expected_profile_id: str,
    as_of: Optional[date] = None,
) -> dict[str, Any]:
    path = record_path(profile_path)
    try:
        record = load_record(path)
    except VehicleProfileQualificationError as exc:
        return {
            "path": path.relative_to(profile_path.parent).as_posix(),
            "present": False,
            "stale": False,
            "validation": _validation([
                _issue("error", "missing-qualification-record", "evidence/qualification.v1.json", str(exc))
            ]),
        }
    result = validate_record(
        record,
        document=document,
        fixtures=fixtures,
        expected_profile_id=expected_profile_id,
        as_of=as_of,
    )
    result.update({"path": "evidence/qualification.v1.json", "present": True})
    return result


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
        temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _parse_date_argument(value: Optional[str], *, field: str, required: bool) -> Optional[str]:
    issues: list[dict[str, str]] = []
    parsed = _date_value(value, path=field, issues=issues, nullable=not required)
    if issues:
        raise VehicleProfileQualificationError(issues[0]["message"])
    return parsed.isoformat() if parsed else None


def _normalize_strings(values: Optional[Sequence[str]], *, field: str, required: bool = False) -> list[str]:
    selected = [value.strip() for value in (values or []) if isinstance(value, str) and value.strip()]
    if required and not selected:
        raise VehicleProfileQualificationError(f"at least one {field} is required")
    if len(selected) != len(set(selected)):
        raise VehicleProfileQualificationError(f"duplicate {field} values are not allowed")
    if any(not _bounded_text(value, 256) for value in selected):
        raise VehicleProfileQualificationError(f"{field} values must be bounded non-empty text")
    return selected


def parse_evidence_argument(value: str) -> dict[str, str]:
    parts = value.split("=", 2)
    if len(parts) != 3:
        raise VehicleProfileQualificationError("evidence must use KIND=PATH=DESCRIPTION")
    kind, path, description = (part.strip() for part in parts)
    if kind not in EVIDENCE_KINDS:
        raise VehicleProfileQualificationError("evidence kind must be research, capture, replay, hardware or documentation")
    candidate = Path(path)
    if not _bounded_text(path, 240) or candidate.is_absolute() or ".." in candidate.parts:
        raise VehicleProfileQualificationError("evidence path must stay within the repository")
    if not _bounded_text(description, 512):
        raise VehicleProfileQualificationError("evidence description must be bounded non-empty text")
    return {"kind": kind, "path": candidate.as_posix(), "description": description}


def transition_profile(
    root: Path,
    profile: str,
    *,
    target: str,
    reason: str,
    reviewers: Sequence[str],
    reviewed_on: str,
    tested_on: Optional[str] = None,
    recheck_after: Optional[str] = None,
    scope: Optional[Sequence[str]] = None,
    equipment: Optional[Sequence[str]] = None,
    variants: Optional[Sequence[str]] = None,
    evidence: Optional[Sequence[Mapping[str, str]]] = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    if target not in LEVELS:
        raise VehicleProfileQualificationError("target level must be none, replay or hardware")
    if not _bounded_text(reason, 512):
        raise VehicleProfileQualificationError("transition reason must be bounded non-empty text")
    selected_reviewers = _normalize_strings(reviewers, field="reviewer", required=True)
    reviewed = _parse_date_argument(reviewed_on, field="reviewed_on", required=True)

    source_root = root.expanduser().resolve()
    resolved = profile_catalogue.resolve_profile(source_root, profile)
    profile_path = Path(resolved["path"])
    canonical_id = str(resolved["id"])
    try:
        document = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VehicleProfileQualificationError(f"cannot read maintained profile: {profile_path}") from exc
    if not isinstance(document, dict):
        raise VehicleProfileQualificationError("maintained profile must be a JSON object")

    metadata = document.get("metadata")
    if not isinstance(metadata, dict):
        raise VehicleProfileQualificationError("maintained profile metadata is missing")
    qualification = metadata.get("qualification")
    if not isinstance(qualification, dict):
        raise VehicleProfileQualificationError("maintained profile qualification metadata is missing")
    current_level = qualification.get("level")
    if current_level not in LEVELS:
        raise VehicleProfileQualificationError("current qualification level is invalid")
    if target == current_level:
        raise VehicleProfileQualificationError("target level already matches current qualification")
    if LEVEL_RANK[target] > LEVEL_RANK[current_level] + 1:
        raise VehicleProfileQualificationError("promotion must advance one stage at a time")

    record_file = record_path(profile_path)
    if record_file.exists():
        record = copy.deepcopy(dict(load_record(record_file)))
    else:
        record = default_record(canonical_id)

    selected_scope: list[str]
    selected_equipment: list[str]
    selected_variants: list[str]
    selected_tested: Optional[str]
    selected_recheck: Optional[str]
    selected_evidence = [copy.deepcopy(item) for item in qualification.get("evidence", []) if isinstance(item, Mapping)]
    for item in evidence or []:
        normalized = dict(item)
        if normalized not in selected_evidence:
            selected_evidence.append(normalized)

    if target == "none":
        selected_tested = None
        selected_recheck = None
        selected_scope = []
        selected_equipment = []
        selected_variants = []
        selected_evidence = []
        review = {"status": "unreviewed", "reviewers": [], "reviewed_on": None, "recheck_after": None}
        maturity = "experimental"
    else:
        selected_tested = _parse_date_argument(tested_on, field="tested_on", required=True)
        selected_recheck = _parse_date_argument(recheck_after, field="recheck_after", required=True)
        selected_scope = _normalize_strings(scope, field="scope item", required=True)
        selected_equipment = _normalize_strings(equipment, field="equipment entry", required=target == "hardware")
        selected_variants = _normalize_strings(variants, field="variant entry", required=target == "hardware")
        review = {
            "status": "approved",
            "reviewers": selected_reviewers,
            "reviewed_on": reviewed,
            "recheck_after": selected_recheck,
        }
        maturity = "candidate" if target == "replay" else "qualified"

    updated = copy.deepcopy(document)
    updated_metadata = updated["metadata"]
    updated_metadata["maturity"] = maturity
    updated_metadata["qualification"] = {
        "level": target,
        "last_tested": selected_tested,
        "scope": selected_scope,
        "evidence": selected_evidence,
    }
    updated_record = copy.deepcopy(record)
    updated_record["schema_version"] = SCHEMA_VERSION
    updated_record["record_id"] = RECORD_ID
    updated_record["profile_id"] = canonical_id
    updated_record["current"] = {
        "level": target,
        "tested_on": selected_tested,
        "scope": selected_scope,
        "compatibility": {"equipment": selected_equipment, "variants": selected_variants},
        "review": review,
    }
    history = list(updated_record.get("history", []))
    history.append({
        "from": current_level,
        "to": target,
        "date": reviewed,
        "reason": reason.strip(),
        "reviewers": selected_reviewers,
    })
    updated_record["history"] = history

    from ui import vehicle_profile_conformance  # Avoid an import cycle.

    fixture_path = profile_path.parent / "fixtures" / "mappings.v1.json"
    fixture_report: dict[str, Any]
    if fixture_path.exists():
        try:
            fixture = profile_replay.load_json(fixture_path)
            replay = profile_replay.replay_fixture(updated, fixture, expected_profile_id=canonical_id)
            fixture_report = {
                "present": True,
                "valid": bool(replay["valid"]),
                "coverage": copy.deepcopy(replay["coverage"]),
            }
        except profile_replay.VehicleProfileReplayError:
            fixture_report = {"present": True, "valid": False, "coverage": {}}
    else:
        fixture_report = {"present": False, "valid": False, "coverage": {}}

    metadata_validation = vehicle_profile_conformance.validate_metadata(updated, expected_id=canonical_id)
    record_validation = validate_record(
        updated_record,
        document=updated,
        fixtures=fixture_report,
        expected_profile_id=canonical_id,
        as_of=date.fromisoformat(reviewed),
    )
    errors = [*metadata_validation["errors"], *record_validation["validation"]["errors"]]
    if errors:
        raise VehicleProfileQualificationError(
            "qualification transition is not admissible: "
            + "; ".join(f"{item['code']}: {item['message']}" for item in errors)
        )

    result = {
        "ok": True,
        "dry_run": bool(dry_run),
        "profile_id": canonical_id,
        "from": current_level,
        "to": target,
        "profile_path": profile_path.relative_to(source_root).as_posix(),
        "record_path": record_file.relative_to(source_root).as_posix(),
        "reviewed_on": reviewed,
        "recheck_after": selected_recheck,
        "warnings": record_validation["validation"]["warnings"],
    }
    if dry_run:
        return result

    profile_before = profile_path.read_bytes()
    record_before = record_file.read_bytes() if record_file.exists() else None
    try:
        _atomic_json(profile_path, updated)
        _atomic_json(record_file, updated_record)
        report = vehicle_profile_conformance.catalogue_report(
            source_root,
            identifiers=[canonical_id],
            as_of=date.fromisoformat(reviewed),
        )
        if not report["valid"]:
            errors = report["profiles"][0]["validation"]["errors"]
            raise VehicleProfileQualificationError(
                "written qualification did not pass catalogue conformance: "
                + "; ".join(item["message"] for item in errors)
            )
    except Exception:
        profile_path.write_bytes(profile_before)
        if record_before is None:
            try:
                record_file.unlink()
            except FileNotFoundError:
                pass
        else:
            record_file.write_bytes(record_before)
        raise
    return result
