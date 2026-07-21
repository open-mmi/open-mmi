"""Bounded CAN capture import and comparison for reverse-engineering work.

The tooling in this module is deliberately research-only. It normalizes common
``candump`` text formats, compares two captures, and can export candidate replay
cases outside the maintained vehicle catalogue. It never edits a profile or the
checked catalogue.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence


SCHEMA_VERSION = 1
CAPTURE_ID = "open-mmi.vehicle-capture"
COMPARISON_ID = "open-mmi.vehicle-capture-comparison"
FIXTURE_ID = "open-mmi.vehicle-mapping-fixtures"
MAX_CAPTURE_BYTES = 64 * 1024 * 1024
MAX_CAPTURE_FRAMES = 500_000
MAX_LINE_BYTES = 4096
MAX_CHANGES = 1024
BUS_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
PROFILE_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LOG_LINE_RE = re.compile(
    r"^(?:\((?P<seconds>\d+)(?:\.(?P<fraction>\d{1,9}))?\)\s+)?"
    r"(?P<bus>[A-Za-z0-9][A-Za-z0-9_.-]{0,63})\s+"
    r"(?P<id>[0-9A-Fa-f]{1,8})#(?P<data>[0-9A-Fa-f]*)$"
)
BRACKET_LINE_RE = re.compile(
    r"^(?:\((?P<seconds>\d+)(?:\.(?P<fraction>\d{1,9}))?\)\s+)?"
    r"(?P<bus>[A-Za-z0-9][A-Za-z0-9_.-]{0,63})\s+"
    r"(?P<id>[0-9A-Fa-f]{1,8})\s+\[(?P<dlc>\d{1,2})\]"
    r"(?:\s+(?P<data>(?:[0-9A-Fa-f]{2}(?:\s+|$))*))?$"
)


class VehicleCaptureAnalysisError(ValueError):
    """Raised when capture research input or output is unsafe or invalid."""


@dataclass(frozen=True)
class CaptureFrame:
    sequence: int
    line: int
    timestamp_ns: Optional[int]
    relative_ns: Optional[int]
    bus: str
    can_id: int
    data: bytes

    @property
    def extended(self) -> bool:
        return self.can_id > 0x7FF


def _parse_timestamp(seconds: Optional[str], fraction: Optional[str]) -> Optional[int]:
    if seconds is None:
        return None
    digits = (fraction or "").ljust(9, "0")[:9]
    return int(seconds) * 1_000_000_000 + int(digits or "0")


def _parse_id(value: Any) -> int:
    if isinstance(value, bool):
        raise VehicleCaptureAnalysisError("CAN identifier must be an integer or hexadecimal string")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        try:
            parsed = int(text, 16) if text.lower().startswith("0x") else int(text, 16)
        except ValueError as exc:
            raise VehicleCaptureAnalysisError(f"invalid CAN identifier: {value}") from exc
    else:
        raise VehicleCaptureAnalysisError("CAN identifier must be an integer or hexadecimal string")
    if not 0 <= parsed <= 0x1FFFFFFF:
        raise VehicleCaptureAnalysisError(f"CAN identifier is out of range: {value}")
    return parsed


def _format_id(can_id: int) -> str:
    width = 3 if can_id <= 0x7FF else 8
    return f"0x{can_id:0{width}X}"


def _format_data(data: bytes) -> str:
    return " ".join(f"{value:02X}" for value in data)


def _bounded_input(path: Path) -> tuple[Path, bytes]:
    selected = path.expanduser()
    try:
        metadata = selected.lstat()
    except OSError as exc:
        raise VehicleCaptureAnalysisError(f"cannot inspect capture input: {selected}") from exc
    if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise VehicleCaptureAnalysisError("capture input must be a non-symlink regular file")
    if metadata.st_size > MAX_CAPTURE_BYTES:
        raise VehicleCaptureAnalysisError("capture input exceeds the 64 MiB research limit")
    try:
        payload = selected.read_bytes()
    except OSError as exc:
        raise VehicleCaptureAnalysisError(f"cannot read capture input: {selected}") from exc
    return selected, payload


def _parse_line(text: str, line_number: int, sequence: int) -> CaptureFrame:
    line = text.strip()
    if "##" in line:
        raise VehicleCaptureAnalysisError(
            f"line {line_number}: CAN FD frames are not supported by this importer"
        )
    match = LOG_LINE_RE.fullmatch(line) or BRACKET_LINE_RE.fullmatch(line)
    if match is None:
        raise VehicleCaptureAnalysisError(
            f"line {line_number}: unsupported candump line; use candump -L or bracket output"
        )
    bus = match.group("bus")
    if not BUS_RE.fullmatch(bus):
        raise VehicleCaptureAnalysisError(f"line {line_number}: invalid bus name")
    can_id = int(match.group("id"), 16)
    if can_id > 0x1FFFFFFF:
        raise VehicleCaptureAnalysisError(f"line {line_number}: CAN identifier is out of range")
    compact = re.sub(r"\s+", "", match.group("data") or "")
    if len(compact) % 2:
        raise VehicleCaptureAnalysisError(f"line {line_number}: CAN payload has an odd number of hex digits")
    try:
        data = bytes.fromhex(compact)
    except ValueError as exc:
        raise VehicleCaptureAnalysisError(f"line {line_number}: CAN payload is not hexadecimal") from exc
    if len(data) > 8:
        raise VehicleCaptureAnalysisError(
            f"line {line_number}: classic CAN payload must contain at most eight bytes"
        )
    raw_dlc = match.groupdict().get("dlc")
    if raw_dlc is not None and int(raw_dlc) != len(data):
        raise VehicleCaptureAnalysisError(
            f"line {line_number}: declared DLC {raw_dlc} does not match {len(data)} payload bytes"
        )
    return CaptureFrame(
        sequence=sequence,
        line=line_number,
        timestamp_ns=_parse_timestamp(match.group("seconds"), match.group("fraction")),
        relative_ns=None,
        bus=bus,
        can_id=can_id,
        data=data,
    )


def load_capture(path: Path) -> tuple[list[CaptureFrame], dict[str, Any]]:
    selected, payload = _bounded_input(path)
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise VehicleCaptureAnalysisError("capture input must be UTF-8 text") from exc
    frames: list[CaptureFrame] = []
    for line_number, raw in enumerate(text.splitlines(), start=1):
        if len(raw.encode("utf-8")) > MAX_LINE_BYTES:
            raise VehicleCaptureAnalysisError(f"line {line_number}: capture line exceeds the limit")
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if len(frames) >= MAX_CAPTURE_FRAMES:
            raise VehicleCaptureAnalysisError("capture input exceeds the 500000-frame limit")
        frames.append(_parse_line(stripped, line_number, len(frames)))
    if not frames:
        raise VehicleCaptureAnalysisError("capture input does not contain any supported CAN frames")
    timestamps = [frame.timestamp_ns for frame in frames if frame.timestamp_ns is not None]
    first_timestamp = min(timestamps) if timestamps else None
    if first_timestamp is not None:
        frames = [
            CaptureFrame(
                sequence=frame.sequence,
                line=frame.line,
                timestamp_ns=frame.timestamp_ns,
                relative_ns=(
                    frame.timestamp_ns - first_timestamp
                    if frame.timestamp_ns is not None
                    else None
                ),
                bus=frame.bus,
                can_id=frame.can_id,
                data=frame.data,
            )
            for frame in frames
        ]
    return frames, {
        "name": selected.name,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "byte_count": len(payload),
        "frame_count": len(frames),
        "timestamped": len(timestamps),
    }


def _filter_values(
    frames: Sequence[CaptureFrame],
    *,
    buses: Optional[Iterable[str]] = None,
    can_ids: Optional[Iterable[Any]] = None,
    start_ms: Optional[float] = None,
    end_ms: Optional[float] = None,
) -> tuple[list[CaptureFrame], dict[str, Any]]:
    selected_buses = set(buses or ())
    if any(not BUS_RE.fullmatch(value) for value in selected_buses):
        raise VehicleCaptureAnalysisError("bus filters must be safe interface names")
    selected_ids = {_parse_id(value) for value in (can_ids or ())}
    for value, label in ((start_ms, "from-ms"), (end_ms, "to-ms")):
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0
        ):
            raise VehicleCaptureAnalysisError(f"{label} must be a finite non-negative number")
    if start_ms is not None and end_ms is not None and start_ms > end_ms:
        raise VehicleCaptureAnalysisError("from-ms must not be greater than to-ms")
    identity_selected = [
        frame
        for frame in frames
        if (not selected_buses or frame.bus in selected_buses)
        and (not selected_ids or frame.can_id in selected_ids)
    ]
    if (start_ms is not None or end_ms is not None) and any(
        frame.relative_ns is None for frame in identity_selected
    ):
        raise VehicleCaptureAnalysisError("time-range filtering requires timestamps on every selected capture line")
    start_ns = int(start_ms * 1_000_000) if start_ms is not None else None
    end_ns = int(end_ms * 1_000_000) if end_ms is not None else None
    result = []
    for frame in identity_selected:
        if start_ns is not None and (frame.relative_ns or 0) < start_ns:
            continue
        if end_ns is not None and (frame.relative_ns or 0) > end_ns:
            continue
        result.append(frame)
    return result, {
        "buses": sorted(selected_buses),
        "ids": [_format_id(value) for value in sorted(selected_ids)],
        "from_ms": start_ms,
        "to_ms": end_ms,
    }


def _frame_payload(frame: CaptureFrame) -> dict[str, Any]:
    return {
        "sequence": frame.sequence,
        "line": frame.line,
        "timestamp_ns": frame.timestamp_ns,
        "relative_us": frame.relative_ns // 1000 if frame.relative_ns is not None else None,
        "bus": frame.bus,
        "id": _format_id(frame.can_id),
        "extended": frame.extended,
        "dlc": len(frame.data),
        "data": _format_data(frame.data),
    }


def normalize_capture(
    path: Path,
    *,
    buses: Optional[Iterable[str]] = None,
    can_ids: Optional[Iterable[Any]] = None,
    start_ms: Optional[float] = None,
    end_ms: Optional[float] = None,
) -> dict[str, Any]:
    frames, source = load_capture(path)
    selected, filters = _filter_values(
        frames,
        buses=buses,
        can_ids=can_ids,
        start_ms=start_ms,
        end_ms=end_ms,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "capture_id": CAPTURE_ID,
        "source": source,
        "filters": filters,
        "summary": {
            "input_frames": len(frames),
            "selected_frames": len(selected),
            "buses": sorted({frame.bus for frame in selected}),
            "ids": [_format_id(value) for value in sorted({frame.can_id for frame in selected})],
        },
        "frames": [_frame_payload(frame) for frame in selected],
    }


def _distribution(values: Sequence[int]) -> dict[str, Any]:
    counts = Counter(values)
    total = len(values)
    ordered = sorted(counts.items())
    dominant = min(
        ordered,
        key=lambda item: (-item[1], item[0]),
    )[0] if ordered else None
    return {
        "total": total,
        "dominant": dominant,
        "values": {f"0x{value:02X}": count for value, count in ordered},
    }


def _variation(before: Sequence[int], after: Sequence[int]) -> float:
    if not before and not after:
        return 0.0
    if not before or not after:
        return 1.0
    before_counts = Counter(before)
    after_counts = Counter(after)
    before_total = len(before)
    after_total = len(after)
    values = set(before_counts) | set(after_counts)
    return sum(
        abs(before_counts[value] / before_total - after_counts[value] / after_total)
        for value in values
    ) / 2.0


def _bit_deltas(before: Sequence[int], after: Sequence[int]) -> list[dict[str, Any]]:
    result = []
    for bit in range(8):
        before_ratio = (
            sum(bool(value & (1 << bit)) for value in before) / len(before)
            if before
            else 0.0
        )
        after_ratio = (
            sum(bool(value & (1 << bit)) for value in after) / len(after)
            if after
            else 0.0
        )
        delta = after_ratio - before_ratio
        if abs(delta) > 1e-12:
            result.append(
                {
                    "bit": bit,
                    "before_one_ratio": round(before_ratio, 6),
                    "after_one_ratio": round(after_ratio, 6),
                    "delta": round(delta, 6),
                }
            )
    return result


def _representative(frames: Sequence[CaptureFrame]) -> Optional[bytes]:
    if not frames:
        return None
    counts = Counter(frame.data for frame in frames)
    return min(counts, key=lambda data: (-counts[data], data))


def _group_frames(frames: Sequence[CaptureFrame]) -> dict[tuple[str, int], list[CaptureFrame]]:
    grouped: dict[tuple[str, int], list[CaptureFrame]] = defaultdict(list)
    for frame in frames:
        grouped[(frame.bus, frame.can_id)].append(frame)
    return dict(grouped)


def compare_captures(
    before_path: Path,
    after_path: Path,
    *,
    buses: Optional[Iterable[str]] = None,
    can_ids: Optional[Iterable[Any]] = None,
    start_ms: Optional[float] = None,
    end_ms: Optional[float] = None,
    minimum_score: float = 0.0,
    limit: int = 128,
) -> dict[str, Any]:
    if (
        isinstance(minimum_score, bool)
        or not isinstance(minimum_score, (int, float))
        or not math.isfinite(minimum_score)
        or not 0 <= minimum_score <= 1
    ):
        raise VehicleCaptureAnalysisError("minimum-score must be between 0 and 1")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_CHANGES:
        raise VehicleCaptureAnalysisError(f"limit must be between 1 and {MAX_CHANGES}")
    before_frames, before_source = load_capture(before_path)
    after_frames, after_source = load_capture(after_path)
    before_selected, filters = _filter_values(
        before_frames,
        buses=buses,
        can_ids=can_ids,
        start_ms=start_ms,
        end_ms=end_ms,
    )
    after_selected, _ = _filter_values(
        after_frames,
        buses=buses,
        can_ids=can_ids,
        start_ms=start_ms,
        end_ms=end_ms,
    )
    before_groups = _group_frames(before_selected)
    after_groups = _group_frames(after_selected)
    changes: list[dict[str, Any]] = []
    for bus, can_id in sorted(set(before_groups) | set(after_groups)):
        before = before_groups.get((bus, can_id), [])
        after = after_groups.get((bus, can_id), [])
        maximum_dlc = max([len(frame.data) for frame in before + after] or [0])
        changed_bytes = []
        scores = []
        for index in range(maximum_dlc):
            before_values = [frame.data[index] for frame in before if index < len(frame.data)]
            after_values = [frame.data[index] for frame in after if index < len(frame.data)]
            score = _variation(before_values, after_values)
            if score <= 1e-12:
                continue
            scores.append(score)
            changed_bytes.append(
                {
                    "index": index,
                    "score": round(score, 6),
                    "before": _distribution(before_values),
                    "after": _distribution(after_values),
                    "bit_deltas": _bit_deltas(before_values, after_values),
                }
            )
        group_score = max(scores or [1.0 if bool(before) != bool(after) else 0.0])
        if group_score <= 1e-12 or group_score < minimum_score:
            continue
        representative_before = _representative(before)
        representative_after = _representative(after)
        changes.append(
            {
                "bus": bus,
                "id": _format_id(can_id),
                "extended": can_id > 0x7FF,
                "score": round(group_score, 6),
                "before_count": len(before),
                "after_count": len(after),
                "before_dlcs": sorted({len(frame.data) for frame in before}),
                "after_dlcs": sorted({len(frame.data) for frame in after}),
                "representative_before": (
                    _format_data(representative_before)
                    if representative_before is not None
                    else None
                ),
                "representative_after": (
                    _format_data(representative_after)
                    if representative_after is not None
                    else None
                ),
                "changed_bytes": changed_bytes,
            }
        )
    changes.sort(key=lambda item: (-float(item["score"]), item["bus"], _parse_id(item["id"])))
    total_changes = len(changes)
    changes = changes[:limit]
    return {
        "schema_version": SCHEMA_VERSION,
        "analysis_id": COMPARISON_ID,
        "sources": {"before": before_source, "after": after_source},
        "filters": {**filters, "minimum_score": minimum_score, "limit": limit},
        "summary": {
            "before_selected_frames": len(before_selected),
            "after_selected_frames": len(after_selected),
            "changed_ids": total_changes,
            "reported_ids": len(changes),
            "truncated": total_changes > len(changes),
        },
        "changes": changes,
    }


def _checked_output(path: Path, *, root: Path, force: bool) -> Path:
    source_root = root.expanduser().resolve()
    original = path.expanduser()
    if not original.is_absolute():
        original = Path.cwd() / original
    for component in (original.parent, *original.parent.parents):
        try:
            metadata = component.lstat()
        except OSError as exc:
            raise VehicleCaptureAnalysisError(
                f"output parent does not exist or cannot be inspected: {component}"
            ) from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise VehicleCaptureAnalysisError(
                f"output path contains a symlinked parent: {component}"
            )
    try:
        output_metadata = original.lstat()
    except FileNotFoundError:
        output_metadata = None
    except OSError as exc:
        raise VehicleCaptureAnalysisError(f"cannot inspect output path: {original}") from exc
    if output_metadata is not None and stat.S_ISLNK(output_metadata.st_mode):
        raise VehicleCaptureAnalysisError("output path must not be a symlink")

    selected = original.resolve(strict=False)
    protected_roots = [source_root / "vehicles"]
    protected_roots.extend(
        ancestor
        for ancestor in (selected.parent, *selected.parent.parents)
        if ancestor.name == "vehicles"
        and (ancestor / "catalogue.v1.json").is_file()
    )
    for vehicles_root in protected_roots:
        try:
            selected.relative_to(vehicles_root)
        except ValueError:
            continue
        raise VehicleCaptureAnalysisError(
            "generated capture analysis must remain outside vehicles/ until manually reviewed"
        )

    parent = selected.parent
    try:
        parent_metadata = parent.lstat()
    except OSError as exc:
        raise VehicleCaptureAnalysisError(f"output parent does not exist: {parent}") from exc
    if not stat.S_ISDIR(parent_metadata.st_mode) or stat.S_ISLNK(parent_metadata.st_mode):
        raise VehicleCaptureAnalysisError("output parent must be a non-symlink directory")
    if output_metadata is None:
        return selected
    if not force:
        raise VehicleCaptureAnalysisError(f"output already exists: {selected}; pass --force to replace it")
    if not stat.S_ISREG(output_metadata.st_mode):
        raise VehicleCaptureAnalysisError("existing output must be a non-symlink regular file")
    return selected


def write_json_report(
    document: Mapping[str, Any],
    output: Path,
    *,
    root: Path,
    force: bool = False,
) -> dict[str, Any]:
    selected = _checked_output(output, root=root, force=force)
    payload = (json.dumps(dict(document), indent=2, sort_keys=True) + "\n").encode("utf-8")
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{selected.name}.",
            dir=selected.parent,
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, selected)
    except OSError as exc:
        try:
            temporary.unlink()
        except (NameError, OSError):
            pass
        raise VehicleCaptureAnalysisError(f"cannot write output: {selected}") from exc
    return {
        "ok": True,
        "path": str(selected),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "byte_count": len(payload),
    }


def candidate_fixture(
    comparison: Mapping[str, Any],
    *,
    profile_id: str,
    fixture_bus: Optional[str] = None,
) -> dict[str, Any]:
    if not PROFILE_ID_RE.fullmatch(profile_id):
        raise VehicleCaptureAnalysisError("profile-id must be a lowercase stable identifier")
    if fixture_bus is not None and not BUS_RE.fullmatch(fixture_bus):
        raise VehicleCaptureAnalysisError("fixture-bus must be a safe bus name")
    raw_changes = comparison.get("changes")
    if not isinstance(raw_changes, list):
        raise VehicleCaptureAnalysisError("comparison report does not contain changes")
    cases = []
    for number, raw in enumerate(raw_changes, start=1):
        if not isinstance(raw, Mapping) or not isinstance(raw.get("representative_after"), str):
            continue
        capture_bus = str(raw.get("bus") or "")
        can_id = str(raw.get("id") or "")
        changed_bytes = raw.get("changed_bytes")
        indexes = [
            item.get("index")
            for item in changed_bytes if isinstance(item, Mapping)
        ] if isinstance(changed_bytes, list) else []
        safe_bus = re.sub(r"[^a-z0-9]+", "-", capture_bus.lower()).strip("-") or "bus"
        safe_id = can_id.lower().replace("0x", "")
        cases.append(
            {
                "name": f"candidate-{number:03d}-{safe_bus}-{safe_id}",
                "bus": fixture_bus or capture_bus,
                "frames": [{"id": can_id, "data": raw["representative_after"]}],
                "expect": {"events": [], "statuses": {}},
                "analysis": {
                    "experimental": True,
                    "review_required": True,
                    "score": raw.get("score"),
                    "changed_bytes": indexes,
                    "capture_bus": capture_bus,
                    "note": "Replace empty expectations only after the human meaning is confirmed.",
                },
            }
        )
    if not cases:
        raise VehicleCaptureAnalysisError("comparison has no after-state frames to export")
    sources = comparison.get("sources") if isinstance(comparison.get("sources"), Mapping) else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "fixture_id": FIXTURE_ID,
        "profile_id": profile_id,
        "experimental": True,
        "review_required": True,
        "source_analysis": {
            "analysis_id": comparison.get("analysis_id"),
            "before_sha256": (
                sources.get("before", {}).get("sha256")
                if isinstance(sources.get("before"), Mapping)
                else None
            ),
            "after_sha256": (
                sources.get("after", {}).get("sha256")
                if isinstance(sources.get("after"), Mapping)
                else None
            ),
        },
        "cases": cases,
    }


def export_candidate_fixture(
    comparison: Mapping[str, Any],
    output: Path,
    *,
    profile_id: str,
    root: Path,
    fixture_bus: Optional[str] = None,
    force: bool = False,
) -> dict[str, Any]:
    document = candidate_fixture(
        comparison,
        profile_id=profile_id,
        fixture_bus=fixture_bus,
    )
    written = write_json_report(document, output, root=root, force=force)
    return {
        **written,
        "profile_id": profile_id,
        "case_count": len(document["cases"]),
        "experimental": True,
        "review_required": True,
    }
