"""Read-only pre-update readiness checks for the managed update coordinator.

All inspected paths, commands, services, and thresholds are fixed locally.  The
browser cannot turn this module into a filesystem or process-inspection API.
"""

from __future__ import annotations

import os
import fcntl
import shutil
import socket
import stat
import subprocess
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from ui import update_coordinator
from ui.web_dashboard import runtime_diagnostics


API_VERSION = 1
MIN_FREE_BYTES = 1024 * 1024 * 1024
MIN_BATTERY_PERCENT = 30
MAX_SERVICE_RESTARTS = 3
SYSTEMCTL_TIMEOUT_SECONDS = 3.0
COORDINATOR_SOCKET = Path("/run/open-mmi/update-coordinator.sock")
UPDATE_LOCK = Path("/run/open-mmi/update.lock")
REQUIRED_COMMANDS = ("git", "systemctl", "curl", "python3", "sudo", "realpath")
REQUIRED_SERVICES = ("canbusd.service", "open-mmi-dashboard.service")
BLOCKED_THERMAL_STATES = {"thermal-limit-active", "hot", "critical"}


def _check(code: str, state: str, summary: str, **details: Any) -> Dict[str, Any]:
    return {"code": code, "state": state, "summary": summary, **details}


def _disk_check(install_dir: Path) -> Dict[str, Any]:
    target = install_dir if install_dir.exists() else install_dir.parent
    try:
        free = shutil.disk_usage(target).free
    except OSError:
        return _check("disk-space", "unknown", "Available update disk space could not be measured")
    return _check(
        "disk-space",
        "pass" if free >= MIN_FREE_BYTES else "block",
        "Sufficient disk space is available" if free >= MIN_FREE_BYTES else "At least 1 GiB of free disk space is required",
        free_bytes=free,
        required_bytes=MIN_FREE_BYTES,
    )


def _command_check() -> Dict[str, Any]:
    missing = [name for name in REQUIRED_COMMANDS if shutil.which(name) is None]
    return _check(
        "required-commands",
        "block" if missing else "pass",
        "Required update commands are available" if not missing else "Required update commands are unavailable",
        missing=missing,
    )


def _coordinator_check(path: Path) -> Dict[str, Any]:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return _check("privileged-coordinator", "block", "The privileged update coordinator is not installed")
    except OSError:
        return _check("privileged-coordinator", "block", "The privileged update coordinator cannot be inspected")
    # A coordinator socket may deliberately be group-writable by a dedicated
    # authorization group, but it must never be writable by every local user.
    trusted = stat.S_ISSOCK(metadata.st_mode) and metadata.st_uid == 0 and not metadata.st_mode & 0o002
    responsive = False
    execution_enabled = False
    if trusted:
        try:
            response = update_coordinator.client_status(path)
            responsive = bool(response.get("ok"))
            execution_enabled = response.get("execution_enabled") is True
        except update_coordinator.CoordinatorError:
            responsive = False
    return _check(
        "privileged-coordinator",
        "pass" if trusted and responsive else "block",
        "The privileged update coordinator boundary is available" if trusted and responsive else "The privileged update coordinator boundary is unavailable or untrusted",
        execution_enabled=execution_enabled,
    )


def _execution_check(coordinator: Mapping[str, Any]) -> Dict[str, Any]:
    enabled = coordinator.get("state") == "pass" and coordinator.get("execution_enabled") is True
    return _check(
        "execution-authorization",
        "pass" if enabled else "block",
        "Coordinator execution is authorized" if enabled else "Coordinator execution actions are not enabled",
    )


def _transaction_check(path: Path) -> Dict[str, Any]:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return _check("active-transaction", "pass", "No update transaction is active")
    except OSError:
        return _check("active-transaction", "block", "Update transaction state cannot be inspected")
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 0 or metadata.st_mode & 0o022:
        return _check("active-transaction", "block", "Update transaction lock is untrusted")
    try:
        with path.open("r", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except BlockingIOError:
        return _check("active-transaction", "block", "An update transaction is active")
    except OSError:
        return _check("active-transaction", "block", "Update transaction state cannot be inspected")
    return _check("active-transaction", "pass", "No update transaction is active")


def _configuration_check(config_dir: Path) -> Dict[str, Any]:
    if not config_dir.exists():
        return _check("configuration-preservation", "pass", "No user configuration directory needs preservation")
    try:
        metadata = config_dir.lstat()
        readable = os.access(config_dir, os.R_OK | os.X_OK)
    except OSError:
        readable = False
        metadata = None
    safe = bool(metadata and stat.S_ISDIR(metadata.st_mode) and readable)
    return _check(
        "configuration-preservation",
        "pass" if safe else "block",
        "User configuration can be read for preservation" if safe else "User configuration cannot be preserved safely",
    )


def _power_check(power: Mapping[str, Any]) -> Dict[str, Any]:
    ac_online = power.get("ac_online")
    capacity = power.get("capacity_percent")
    if ac_online is True:
        return _check("power", "pass", "External power is connected", ac_online=True, capacity_percent=capacity)
    if isinstance(capacity, (int, float)):
        okay = capacity >= MIN_BATTERY_PERCENT
        return _check(
            "power", "pass" if okay else "block",
            "Battery level satisfies update policy" if okay else "Connect external power or charge the battery to at least 30%",
            ac_online=ac_online,
            capacity_percent=capacity,
        )
    return _check("power", "unknown", "Power state is not exposed by this hardware", ac_online=ac_online, capacity_percent=None)


def _thermal_check(thermal: Mapping[str, Any]) -> Dict[str, Any]:
    summary = str(thermal.get("summary") or "unavailable")
    if summary in BLOCKED_THERMAL_STATES:
        return _check("thermal", "block", "Thermal constraints must clear before updating", thermal_state=summary)
    if summary == "unavailable":
        return _check("thermal", "unknown", "Thermal state is not exposed by this hardware", thermal_state=summary)
    return _check("thermal", "pass", "Thermal state permits an update", thermal_state=summary)


def _service_check() -> Dict[str, Any]:
    command = ["systemctl", "--user", "show", *REQUIRED_SERVICES, "--property=Id,ActiveState,SubState,NRestarts", "--value"]
    try:
        result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False, timeout=SYSTEMCTL_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        return _check("service-health", "unknown", "Service restart state could not be inspected")
    if result.returncode != 0:
        return _check("service-health", "unknown", "Service restart state could not be inspected")
    restarts = []
    for line in result.stdout.splitlines():
        value = line.strip()
        if value.isdigit():
            restarts.append(int(value))
    looping = bool(restarts) and max(restarts) > MAX_SERVICE_RESTARTS
    return _check(
        "service-health",
        "block" if looping else "pass",
        "A required service is restarting repeatedly" if looping else "Required services are not in a restart loop",
        maximum_restarts=max(restarts) if restarts else 0,
    )


def readiness_payload(
    update_status_payload: Mapping[str, Any],
    *,
    install_dir: Path = Path("/opt/open-mmi"),
    config_dir: Optional[Path] = None,
    coordinator_socket: Path = COORDINATOR_SOCKET,
    update_lock: Path = UPDATE_LOCK,
    diagnostics: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Return the complete fixed pre-update readiness gate."""

    base = update_status_payload.get("readiness", {})
    base_blockers = list(base.get("blockers", [])) if isinstance(base, Mapping) else ["update-status-invalid"]
    runtime = diagnostics or runtime_diagnostics.runtime_diagnostics_payload()
    home_config = config_dir or (Path.home() / ".config/open-mmi")
    coordinator = _coordinator_check(coordinator_socket)
    checks = [
        _check("managed-source", "block" if base_blockers else "pass", "Managed update source is ready" if not base_blockers else "Managed update source is not ready", blockers=base_blockers),
        _transaction_check(update_lock),
        _disk_check(install_dir),
        _command_check(),
        coordinator,
        _execution_check(coordinator),
        _configuration_check(home_config),
        _power_check(runtime.get("power", {})),
        _thermal_check(runtime.get("thermal", {})),
        _service_check(),
    ]
    blockers = [item["code"] for item in checks if item["state"] == "block"]
    unknown = [item["code"] for item in checks if item["state"] == "unknown"]
    return {
        "api_version": API_VERSION,
        "read_only": True,
        "state": "blocked" if blockers else ("indeterminate" if unknown else "ready"),
        "install_allowed": not blockers and not unknown,
        "blockers": blockers,
        "unknown": unknown,
        "checks": checks,
    }
