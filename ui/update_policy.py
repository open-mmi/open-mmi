"""Trusted update-channel policy shared by CLI and dashboard inspection.

The policy file selects one of three fixed channels.  It never contains a
repository URL, path, branch, tag pattern, or command.  Those values come from
installer-owned source metadata and fixed application policy.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


POLICY_SCHEMA_VERSION = 1
APPROVED_CHANNELS = ("stable", "beta", "development")
DEFAULT_POLICY_FILE = Path("/etc/open-mmi/update-policy.json")
OFFICIAL_REPOSITORY_SLUG = "github.com/open-mmi/open-mmi"


class UpdatePolicyError(RuntimeError):
    """Safe, user-facing update-policy failure."""


def policy_file() -> Path:
    """Return the fixed production policy path."""

    return DEFAULT_POLICY_FILE


def _timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def validate_channel(value: object) -> str:
    channel = str(value or "").strip().lower()
    if channel not in APPROVED_CHANNELS:
        raise UpdatePolicyError("Update channel must be stable, beta, or development")
    return channel


def _production_path(path: Path) -> bool:
    """Compare the configured path without following symlinks."""

    try:
        return Path(os.path.abspath(path)) == DEFAULT_POLICY_FILE
    except (OSError, TypeError, ValueError):
        return path == DEFAULT_POLICY_FILE




def _trusted_production_directory(path: Path) -> bool:
    if not _production_path(path):
        return True
    try:
        metadata = path.parent.lstat()
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return (
        stat.S_ISDIR(metadata.st_mode)
        and metadata.st_uid == 0
        and not metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
    )

def _trusted_existing_file(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        return False
    if metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        return False
    if _production_path(path) and metadata.st_uid != 0:
        return False
    return True


def read_policy(path: Optional[Path] = None) -> Tuple[Optional[Dict[str, Any]], str]:
    """Read channel policy.

    A missing policy is a deliberate compatibility migration for descriptors
    produced by the first read-only slice: it means implicit development mode.
    Invalid or untrusted files never fall back silently.
    """

    destination = path or policy_file()
    if not _trusted_production_directory(destination):
        return None, "invalid"
    try:
        destination.lstat()
    except FileNotFoundError:
        return {
            "schema_version": POLICY_SCHEMA_VERSION,
            "channel": "development",
            "implicit": True,
            "updated_at": None,
        }, "legacy-development"
    except OSError:
        return None, "invalid"
    if not _trusted_existing_file(destination):
        return None, "invalid"
    try:
        payload = json.loads(destination.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None, "invalid"
    if not isinstance(payload, dict):
        return None, "invalid"
    if set(payload) - {"schema_version", "channel", "updated_at"}:
        return None, "invalid"
    if payload.get("schema_version") != POLICY_SCHEMA_VERSION:
        return None, "invalid"
    try:
        channel = validate_channel(payload.get("channel"))
    except UpdatePolicyError:
        return None, "invalid"
    updated_at = payload.get("updated_at")
    if updated_at is not None and not isinstance(updated_at, str):
        return None, "invalid"
    return {
        "schema_version": POLICY_SCHEMA_VERSION,
        "channel": channel,
        "implicit": False,
        "updated_at": updated_at,
    }, "configured"


def write_policy(channel: object, path: Optional[Path] = None) -> Dict[str, Any]:
    """Atomically write the fixed channel selection.

    The production path requires root. Tests may pass an explicit temporary
    path without weakening the fixed production-path ownership checks.
    """

    selected = validate_channel(channel)
    destination = path or policy_file()
    production = _production_path(destination)
    if production and os.geteuid() != 0:
        raise UpdatePolicyError("Changing the update channel requires root privileges")
    if destination.is_symlink():
        raise UpdatePolicyError("Update policy path must not be a symlink")
    if production and destination.parent.is_symlink():
        raise UpdatePolicyError("Update policy directory must not be a symlink")

    destination.parent.mkdir(parents=True, exist_ok=True)
    if production:
        try:
            parent_metadata = destination.parent.lstat()
            if not stat.S_ISDIR(parent_metadata.st_mode) or parent_metadata.st_uid != 0:
                raise OSError("production policy directory is not a root-owned directory")
            if parent_metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
                raise OSError("production policy directory is group/world writable")
            os.chmod(destination.parent, 0o755)
        except OSError as exc:
            raise UpdatePolicyError("Could not secure the update policy directory") from exc

    payload = {
        "schema_version": POLICY_SCHEMA_VERSION,
        "channel": selected,
        "updated_at": _timestamp(),
    }
    temporary_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            json.dump(payload, temporary, indent=2, sort_keys=True)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.chmod(temporary_name, 0o644)
        os.replace(temporary_name, destination)
        directory_fd = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except (OSError, TypeError, ValueError) as exc:
        if temporary_name:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
        raise UpdatePolicyError("Could not write update channel policy") from exc
    return {**payload, "implicit": False}


def normalize_repository_url(value: object) -> str:
    """Return the canonical official repository slug or an empty string."""

    raw = str(value or "").strip()
    if not raw:
        return ""
    lowered = raw.lower().rstrip("/")
    if lowered.endswith(".git"):
        lowered = lowered[:-4]

    accepted = {
        "https://github.com/open-mmi/open-mmi": OFFICIAL_REPOSITORY_SLUG,
        "ssh://git@github.com/open-mmi/open-mmi": OFFICIAL_REPOSITORY_SLUG,
        "git@github.com:open-mmi/open-mmi": OFFICIAL_REPOSITORY_SLUG,
    }
    return accepted.get(lowered, "")


def is_official_repository_url(value: object) -> bool:
    return normalize_repository_url(value) == OFFICIAL_REPOSITORY_SLUG
