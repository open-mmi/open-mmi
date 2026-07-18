"""Read-only installed-version and trusted update-channel inspection.

The dashboard never accepts repository paths, remotes, branches, tags, channels,
or commands from HTTP requests. The installer records source metadata and a
separate administrative policy selects one fixed channel. This module performs
bounded, read-only Git inspection from those local records.
"""

from __future__ import annotations

import json
import os
import pwd
import re
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from ui import update_policy


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
_RELEASE_RE = re.compile(
    r"^v(?P<major>0|[1-9][0-9]*)\."
    r"(?P<minor>0|[1-9][0-9]*)\."
    r"(?P<patch>0|[1-9][0-9]*)"
    r"(?:-(?P<stage>alpha|beta|rc)\.(?P<number>0|[1-9][0-9]*))?$"
)
_STAGE_ORDER = {"alpha": 0, "beta": 1, "rc": 2, "stable": 3}

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
        or cleaned.startswith(("-", "/"))
        or cleaned.endswith("/")
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
    recorded_channel = str(payload.get("channel") or "").strip().lower()
    if (
        not repository_text
        or not repository.is_absolute()
        or recorded_channel not in update_policy.APPROVED_CHANNELS
    ):
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
        "recorded_channel": recorded_channel,
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
    identity: Dict[str, Any] = {}
    sudo_uid = str(environment.get("SUDO_UID") or "").strip()
    sudo_gid = str(environment.get("SUDO_GID") or "").strip()
    if os.geteuid() == 0:
        target_uid: Optional[int] = None
        target_gid: Optional[int] = None
        if sudo_uid.isdigit() and sudo_gid.isdigit() and int(sudo_uid) != 0:
            target_uid = int(sudo_uid)
            target_gid = int(sudo_gid)
        else:
            try:
                repository_owner = repository.stat()
            except OSError:
                repository_owner = None
            if repository_owner is not None and repository_owner.st_uid != 0:
                target_uid = repository_owner.st_uid
                target_gid = repository_owner.st_gid
        if target_uid is None or target_gid is None:
            raise OSError("Refusing to inspect the update checkout as root")
        try:
            account = pwd.getpwuid(target_uid)
            extra_groups = os.getgrouplist(account.pw_name, target_gid)
        except (KeyError, OSError, ValueError) as exc:
            raise OSError("Could not resolve the unprivileged Git identity") from exc
        environment["HOME"] = account.pw_dir
        environment["USER"] = account.pw_name
        environment["LOGNAME"] = account.pw_name
        identity = {
            "user": target_uid,
            "group": target_gid,
            "extra_groups": extra_groups,
        }
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
        env=environment,
        **identity,
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


def _remote_url(source: Mapping[str, str]) -> str:
    return _git_output(Path(source["repository_path"]), "remote", "get-url", source["remote"])


def _repository_snapshot(
    source: Optional[Mapping[str, str]],
    source_state: str,
    channel: str = "development",
) -> Dict[str, Any]:
    if not source:
        return {
            "configured": False,
            "state": source_state,
            "clean": None,
            "branch": "",
            "expected_branch": "",
            "upstream": "",
            "commit": "",
            "trusted": None,
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
            "trusted": None,
        }

    commit = _git_output(repository, "rev-parse", "HEAD").lower()
    branch = _git_output(repository, "symbolic-ref", "--quiet", "--short", "HEAD")
    remote_url = _remote_url(source)
    trusted = (
        update_policy.is_official_repository_url(remote_url)
        if channel in {"stable", "beta"}
        else bool(remote_url)
    )
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
    elif channel in {"stable", "beta"} and (
        source["branch"] != "main" or source["remote_branch"] != "main"
    ):
        state = "channel-source-mismatch"
    elif not trusted:
        state = "untrusted-remote"
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
        "trusted": trusted,
    }


def _source_signature(
    source: Optional[Mapping[str, str]],
    channel: str = "",
    policy_state: str = "",
    policy_updated_at: object = None,
) -> str:
    if not source:
        return f"{channel}|{policy_state}|{policy_updated_at or ''}"
    values = [
        source.get(key, "")
        for key in ("repository_path", "branch", "upstream", "installed_commit", "installed_version")
    ]
    values.extend((channel, policy_state, str(policy_updated_at or "")))
    return "|".join(values)


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


def _policy_snapshot() -> Tuple[Optional[Dict[str, Any]], str]:
    return update_policy.read_policy()


def status_payload() -> Dict[str, Any]:
    source, source_state = _read_source_descriptor()
    policy, policy_state = _policy_snapshot()
    channel = str(policy.get("channel") or "") if policy else "invalid"
    repository = _repository_snapshot(source, source_state, channel)
    signature = _source_signature(
        source,
        channel,
        policy_state,
        policy.get("updated_at") if policy else None,
    )
    check = _cached_check(signature) or _default_check()
    check.pop("source_signature", None)

    version_file_value = _read_text(_version_file())
    recorded_version = source.get("installed_version", "") if source else ""
    installed_version = version_file_value or recorded_version

    blockers = []
    if not policy:
        blockers.append("update-policy-invalid")
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
        "channel": channel,
        "policy": {
            "state": policy_state,
            "implicit": bool(policy and policy.get("implicit")),
            "updated_at": policy.get("updated_at") if policy else None,
        },
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


def _release_key(tag: str, channel: str) -> Optional[Tuple[int, int, int, int, int]]:
    match = _RELEASE_RE.fullmatch(str(tag or ""))
    if not match:
        return None
    stage = match.group("stage") or "stable"
    if channel == "stable" and stage != "stable":
        return None
    if channel not in {"stable", "beta"}:
        return None
    return (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
        _STAGE_ORDER[stage],
        int(match.group("number") or 0),
    )


def _remote_release(source: Mapping[str, str], channel: str) -> Tuple[str, str, Tuple[int, int, int, int, int]]:
    repository = Path(source["repository_path"])
    if not update_policy.is_official_repository_url(_remote_url(source)):
        raise UpdateStatusError("Selected release channel requires the official Open MMI repository")
    try:
        result = _run_git(
            repository,
            ("ls-remote", "--tags", source["remote"], "refs/tags/v*"),
            timeout=REMOTE_GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise UpdateStatusError("Update source check timed out") from exc
    except OSError as exc:
        raise UpdateStatusError("Git is unavailable for update checks") from exc
    if result.returncode != 0:
        raise UpdateStatusError("Update source could not be reached")

    releases: Dict[str, Dict[str, str]] = {}
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) != 2 or not _COMMIT_RE.fullmatch(parts[0]):
            continue
        reference = parts[1]
        if not reference.startswith("refs/tags/"):
            continue
        tag = reference[len("refs/tags/") :]
        peeled = tag.endswith("^{}")
        if peeled:
            tag = tag[:-3]
        if _release_key(tag, channel) is None:
            continue
        entry = releases.setdefault(tag, {})
        entry["peeled" if peeled else "direct"] = parts[0].lower()

    candidates = []
    for tag, commits in releases.items():
        key = _release_key(tag, channel)
        commit = commits.get("peeled") or commits.get("direct")
        if key is not None and commit:
            candidates.append((key, tag, commit))
    if not candidates:
        raise UpdateStatusError(f"No approved {channel} release is available")
    key, tag, commit = max(candidates, key=lambda item: item[0])
    return tag, commit, key


def _release_comparison(
    source: Mapping[str, str],
    channel: str,
    available_tag: str,
    available_commit: str,
    available_key: Tuple[int, int, int, int, int],
) -> Tuple[str, Optional[bool], str]:
    installed_commit = source["installed_commit"]
    installed_version = source.get("installed_version", "")
    if installed_commit == available_commit:
        return "up-to-date", False, ""
    installed_key = _release_key(installed_version, "beta")
    if installed_key is None:
        return "remote-different", None, "Installed release version cannot be compared safely"
    if available_key < installed_key:
        return "downgrade-blocked", False, "Selected channel would require a downgrade"
    if available_key == installed_key:
        return "release-rewritten", None, f"Release tag {available_tag} no longer identifies the installed commit"
    return "update-available", True, ""


def _blocked_check(signature: str, checked_at: str, error: str) -> Dict[str, Any]:
    result = {
        **_default_check(),
        "state": "blocked",
        "checked_at": checked_at,
        "error": error,
        "source_signature": signature,
    }
    _store_check(result)
    return status_payload()


def check_for_updates() -> Dict[str, Any]:
    if not _CHECK_LOCK.acquire(blocking=False):
        raise UpdateStatusError("An update check is already in progress")

    try:
        source, source_state = _read_source_descriptor()
        policy, policy_state = _policy_snapshot()
        channel = str(policy.get("channel") or "") if policy else "invalid"
        signature = _source_signature(
            source,
            channel,
            policy_state,
            policy.get("updated_at") if policy else None,
        )
        checked_at = _timestamp()
        if not policy:
            return _blocked_check(signature, checked_at, "Managed update policy is invalid")
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

        repository = _repository_snapshot(source, source_state, channel)
        blocked_states = {
            "unavailable": "Managed update repository is unavailable",
            "detached": "Managed update repository is in detached HEAD state",
            "branch-mismatch": "Managed update repository is on a different branch",
            "channel-source-mismatch": "Selected release channel requires the main branch and its tracked main upstream",
            "untrusted-remote": "Selected update source is not trusted for this channel",
        }
        if repository["state"] in blocked_states:
            return _blocked_check(signature, checked_at, blocked_states[repository["state"]])

        try:
            if channel == "development":
                remote_commit = _remote_commit(source)
                state, update_available = _comparison_state(
                    Path(source["repository_path"]), source["installed_commit"], remote_commit
                )
                available_version = _short_commit(remote_commit)
                error = ""
            else:
                available_version, remote_commit, release_key = _remote_release(source, channel)
                state, update_available, error = _release_comparison(
                    source,
                    channel,
                    available_version,
                    remote_commit,
                    release_key,
                )
            result = {
                "state": state,
                "checked_at": checked_at,
                "available_version": available_version,
                "available_commit": remote_commit,
                "remote_differs": remote_commit != source["installed_commit"],
                "update_available": update_available,
                "error": error,
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


def configure_channel(channel: object) -> Dict[str, Any]:
    """Select one fixed channel through the administrative CLI only."""

    try:
        selected = update_policy.validate_channel(channel)
    except update_policy.UpdatePolicyError as exc:
        raise UpdateStatusError(str(exc)) from exc
    source, source_state = _read_source_descriptor()
    if not source:
        raise UpdateStatusError(
            "Managed update source is not configured" if source_state == "unconfigured" else "Managed update source is invalid"
        )
    repository = _repository_snapshot(source, source_state, selected)
    if repository["state"] != "ready":
        labels = {
            "unavailable": "Managed update repository is unavailable",
            "detached": "Managed update repository is in detached HEAD state",
            "branch-mismatch": "Managed update repository is on a different branch",
            "channel-source-mismatch": "Stable and beta channels require the main branch and origin/main-style tracking",
            "untrusted-remote": "Stable and beta channels require the official Open MMI repository",
            "source-changed": "Managed update source does not match the installed commit",
            "dirty": "Managed update source has local changes",
        }
        raise UpdateStatusError(labels.get(repository["state"], "Managed update source is not ready"))
    try:
        update_policy.write_policy(selected)
    except update_policy.UpdatePolicyError as exc:
        raise UpdateStatusError(str(exc)) from exc
    clear_cached_status()
    return status_payload()
