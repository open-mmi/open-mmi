"""Read-only installed-version and update-source inspection.

The dashboard never accepts repository paths, remotes, branches, or commands from
HTTP requests.  The installer records a small managed descriptor in the managed
installation and this module performs bounded, read-only Git inspection from
that descriptor. The descriptor is authoritative against browser input for this
unprivileged read-only feature; it is not a future privileged-execution policy.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple


API_VERSION = 1
SOURCE_SCHEMA_VERSION = 1
DEFAULT_INSTALL_DIR = Path("/opt/open-mmi")
DEFAULT_VERSION_FILE = DEFAULT_INSTALL_DIR / ".version"
DEFAULT_SOURCE_FILE = DEFAULT_INSTALL_DIR / ".update-source.json"
LOCAL_GIT_TIMEOUT_SECONDS = 5.0
REMOTE_GIT_TIMEOUT_SECONDS = 15.0
_COMMIT_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_REMOTE_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_REF_RE = re.compile(r"^[A-Za-z0-9._/-]+$")

_CHECK_LOCK = threading.Lock()
_CACHE_LOCK = threading.Lock()
_LAST_CHECK: Optional[Dict[str, Any]] = None


class UpdateStatusError(RuntimeError):
    """Safe, user-facing update-status failure."""


def _configured_path(environment_name: str, default: Path) -> Path:
    value = str(os.getenv(environment_name, "") or "").strip()
    return Path(value).expanduser() if value else default


def _version_file() -> Path:
    return _configured_path("OPEN_MMI_VERSION_FILE", DEFAULT_VERSION_FILE)


def _source_file() -> Path:
    return _configured_path("OPEN_MMI_UPDATE_SOURCE_FILE", DEFAULT_SOURCE_FILE)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _short_commit(value: str) -> str:
    cleaned = str(value or "").strip().lower()
    return cleaned[:12] if _COMMIT_RE.fullmatch(cleaned) else ""


def _timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_remote(value: object) -> str:
    cleaned = str(value or "").strip()
    if not cleaned or not _REMOTE_RE.fullmatch(cleaned) or cleaned.startswith("-"):
        raise UpdateStatusError("Configured update remote is invalid")
    return cleaned


def _safe_ref(value: object, label: str) -> str:
    cleaned = str(value or "").strip()
    if (
        not cleaned
        or not _REF_RE.fullmatch(cleaned)
        or cleaned.startswith(('-', '/'))
        or cleaned.endswith('/')
        or ".." in cleaned
        or "//" in cleaned
    ):
        raise UpdateStatusError(f"Configured update {label} is invalid")
    return cleaned


def _read_source_descriptor(path: Optional[Path] = None) -> Tuple[Optional[Dict[str, str]], str]:
    descriptor_path = path or _source_file()
    try:
        payload = json.loads(descriptor_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "unconfigured"
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None, "invalid"

    if not isinstance(payload, dict) or payload.get("schema_version") != SOURCE_SCHEMA_VERSION:
        return None, "invalid"

    repository_text = str(payload.get("repository_path") or "").strip()
    repository = Path(repository_text).expanduser()
    installed_commit = str(payload.get("installed_commit") or "").strip().lower()
    installed_version = str(payload.get("installed_version") or "").strip()
    channel = str(payload.get("channel") or "").strip().lower()
    if not repository_text or not repository.is_absolute() or channel != "development":
        return None, "invalid"
    if not _COMMIT_RE.fullmatch(installed_commit):
        return None, "invalid"

    try:
        branch = _safe_ref(payload.get("branch"), "branch")
        upstream = str(payload.get("upstream") or "").strip()
        if "/" not in upstream:
            raise UpdateStatusError("Configured update upstream is invalid")
        remote_text, remote_branch_text = upstream.split("/", 1)
        remote = _safe_remote(remote_text)
        remote_branch = _safe_ref(remote_branch_text, "upstream branch")
    except UpdateStatusError:
        return None, "invalid"

    return {
        "repository_path": str(repository),
        "channel": channel,
        "branch": branch,
        "upstream": f"{remote}/{remote_branch}",
        "remote": remote,
        "remote_branch": remote_branch,
        "installed_commit": installed_commit,
        "installed_version": installed_version,
    }, "configured"


def _run_git(
    repository: Path,
    arguments: Sequence[str],
    *,
    timeout: float = LOCAL_GIT_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["GIT_TERMINAL_PROMPT"] = "0"
    environment.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
        env=environment,
    )


def _git_output(repository: Path, *arguments: str) -> str:
    try:
        result = _run_git(repository, arguments)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _git_success(repository: Path, *arguments: str) -> bool:
    try:
        return _run_git(repository, arguments).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _repository_snapshot(source: Optional[Mapping[str, str]], source_state: str) -> Dict[str, Any]:
    if not source:
        return {
            "configured": False,
            "state": source_state,
            "clean": None,
            "branch": "",
            "expected_branch": "",
            "upstream": "",
            "commit": "",
        }

    repository = Path(source["repository_path"])
    if not repository.is_dir() or not _git_success(repository, "rev-parse", "--is-inside-work-tree"):
        return {
            "configured": True,
            "state": "unavailable",
            "clean": None,
            "branch": "",
            "expected_branch": source["branch"],
            "upstream": source["upstream"],
            "commit": "",
        }

    commit = _git_output(repository, "rev-parse", "HEAD").lower()
    branch = _git_output(repository, "symbolic-ref", "--quiet", "--short", "HEAD")
    try:
        dirty_result = _run_git(repository, ("status", "--porcelain", "--untracked-files=normal"))
        clean: Optional[bool] = dirty_result.returncode == 0 and not dirty_result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        clean = None

    if not _COMMIT_RE.fullmatch(commit):
        state = "unavailable"
    elif not branch:
        state = "detached"
    elif branch != source["branch"]:
        state = "branch-mismatch"
    elif commit != source["installed_commit"]:
        state = "source-changed"
    elif clean is False:
        state = "dirty"
    elif clean is None:
        state = "unavailable"
    else:
        state = "ready"

    return {
        "configured": True,
        "state": state,
        "clean": clean,
        "branch": branch,
        "expected_branch": source["branch"],
        "upstream": source["upstream"],
        "commit": _short_commit(commit),
    }


def _source_signature(source: Optional[Mapping[str, str]]) -> str:
    if not source:
        return ""
    return "|".join(
        source.get(key, "")
        for key in ("repository_path", "branch", "upstream", "installed_commit")
    )


def _cached_check(signature: str) -> Optional[Dict[str, Any]]:
    with _CACHE_LOCK:
        if _LAST_CHECK and _LAST_CHECK.get("source_signature") == signature:
            return dict(_LAST_CHECK)
    return None


def _store_check(result: Mapping[str, Any]) -> None:
    global _LAST_CHECK
    with _CACHE_LOCK:
        _LAST_CHECK = dict(result)


def clear_cached_status() -> None:
    """Clear process-local check state. Intended for deterministic tests."""

    global _LAST_CHECK
    with _CACHE_LOCK:
        _LAST_CHECK = None


def _default_check() -> Dict[str, Any]:
    return {
        "state": "not-checked",
        "checked_at": None,
        "available_version": "",
        "available_commit": "",
        "remote_differs": None,
        "update_available": None,
        "error": "",
    }


def status_payload() -> Dict[str, Any]:
    source, source_state = _read_source_descriptor()
    repository = _repository_snapshot(source, source_state)
    signature = _source_signature(source)
    check = _cached_check(signature) or _default_check()
    check.pop("source_signature", None)

    version_file_value = _read_text(_version_file())
    recorded_version = source.get("installed_version", "") if source else ""
    installed_version = version_file_value or recorded_version

    blockers = []
    if not version_file_value:
        blockers.append("installed-version-unknown")
    if version_file_value and recorded_version and version_file_value != recorded_version:
        blockers.append("installed-metadata-mismatch")
    if repository["state"] != "ready":
        blockers.append(f"repository-{repository['state']}")

    return {
        "api_version": API_VERSION,
        "read_only": True,
        "installed": {
            "managed": bool(version_file_value),
            "version": installed_version or "unknown",
            "commit": _short_commit(source.get("installed_commit", "") if source else ""),
        },
        "channel": source.get("channel", "unconfigured") if source else "unconfigured",
        "source": repository,
        "update": check,
        "readiness": {
            "state": "ready" if not blockers else "blocked",
            "blockers": blockers,
        },
    }


def _remote_commit(source: Mapping[str, str]) -> str:
    repository = Path(source["repository_path"])
    reference = f"refs/heads/{source['remote_branch']}"
    try:
        result = _run_git(
            repository,
            ("ls-remote", "--exit-code", "--refs", source["remote"], reference),
            timeout=REMOTE_GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise UpdateStatusError("Update source check timed out") from exc
    except OSError as exc:
        raise UpdateStatusError("Git is unavailable for update checks") from exc

    if result.returncode != 0:
        raise UpdateStatusError("Update source could not be reached")

    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == reference and _COMMIT_RE.fullmatch(parts[0]):
            return parts[0].lower()
    raise UpdateStatusError("Update source returned an invalid branch response")


def _comparison_state(repository: Path, installed_commit: str, remote_commit: str) -> Tuple[str, Optional[bool]]:
    if installed_commit == remote_commit:
        return "up-to-date", False
    if (
        not _git_success(repository, "cat-file", "-e", f"{installed_commit}^{{commit}}")
        or not _git_success(repository, "cat-file", "-e", f"{remote_commit}^{{commit}}")
    ):
        return "remote-different", None
    if _git_success(repository, "merge-base", "--is-ancestor", installed_commit, remote_commit):
        return "update-available", True
    if _git_success(repository, "merge-base", "--is-ancestor", remote_commit, installed_commit):
        return "local-ahead", False
    return "diverged", None


def check_for_updates() -> Dict[str, Any]:
    if not _CHECK_LOCK.acquire(blocking=False):
        raise UpdateStatusError("An update check is already in progress")

    try:
        source, source_state = _read_source_descriptor()
        signature = _source_signature(source)
        checked_at = _timestamp()
        if not source:
            result = {
                **_default_check(),
                "state": "source-unavailable" if source_state == "unconfigured" else "source-invalid",
                "checked_at": checked_at,
                "error": "Managed update source is not configured" if source_state == "unconfigured" else "Managed update source is invalid",
                "source_signature": signature,
            }
            _store_check(result)
            return status_payload()

        repository = _repository_snapshot(source, source_state)
        if repository["state"] in {"unavailable", "detached", "branch-mismatch"}:
            labels = {
                "unavailable": "Managed update repository is unavailable",
                "detached": "Managed update repository is in detached HEAD state",
                "branch-mismatch": "Managed update repository is on a different branch",
            }
            result = {
                **_default_check(),
                "state": "blocked",
                "checked_at": checked_at,
                "error": labels[repository["state"]],
                "source_signature": signature,
            }
            _store_check(result)
            return status_payload()

        try:
            remote_commit = _remote_commit(source)
            state, update_available = _comparison_state(
                Path(source["repository_path"]), source["installed_commit"], remote_commit
            )
            result = {
                "state": state,
                "checked_at": checked_at,
                "available_version": _short_commit(remote_commit),
                "available_commit": remote_commit,
                "remote_differs": remote_commit != source["installed_commit"],
                "update_available": update_available,
                "error": "",
                "source_signature": signature,
            }
        except UpdateStatusError as exc:
            result = {
                **_default_check(),
                "state": "unavailable",
                "checked_at": checked_at,
                "error": str(exc),
                "source_signature": signature,
            }
        _store_check(result)
        return status_payload()
    finally:
        _CHECK_LOCK.release()
