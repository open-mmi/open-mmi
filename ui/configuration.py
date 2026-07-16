"""Shared Open MMI desktop-shell and dashboard configuration helpers.

The browser-facing dashboard, the interactive CLI, and systemd all use the
same user-owned files. Secrets are kept in ``dashboard.env`` and never returned
through the dashboard API.
"""

from __future__ import annotations

import ipaddress
import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping, Optional
from urllib.parse import urlparse

DASHBOARD_SERVICE = "open-mmi-dashboard.service"
JELLYFIN_ENV_KEYS = (
    "OPEN_MMI_JELLYFIN_URL",
    "OPEN_MMI_JELLYFIN_TOKEN",
    "OPEN_MMI_JELLYFIN_USERNAME",
    "OPEN_MMI_JELLYFIN_PASSWORD",
    "OPEN_MMI_JELLYFIN_USER_ID",
    "OPEN_MMI_JELLYFIN_LIBRARY_ID",
    "OPEN_MMI_JELLYFIN_SESSION_ID",
    "OPEN_MMI_JELLYFIN_DEVICE",
    "OPEN_MMI_JELLYFIN_INSECURE_TLS",
    "OPEN_MMI_JELLYFIN_ALLOW_GLOBAL",
)
MAX_ENV_VALUE_BYTES = 4096


class ConfigurationError(RuntimeError):
    """A user-facing configuration failure."""


def config_dir() -> Path:
    home = os.getenv("XDG_CONFIG_HOME")
    if home:
        return Path(home) / "open-mmi"
    return Path.home() / ".config" / "open-mmi"


def dashboard_env_path() -> Path:
    override = os.getenv("OPEN_MMI_DASHBOARD_ENV_FILE", "").strip()
    return Path(override) if override else config_dir() / "dashboard.env"


def _validate_env_value(value: Any, label: str) -> str:
    text = str(value or "")
    if "\0" in text or "\n" in text or "\r" in text:
        raise ConfigurationError(f"{label} may not contain line breaks or NUL bytes")
    if len(text.encode("utf-8")) > MAX_ENV_VALUE_BYTES:
        raise ConfigurationError(f"{label} is too long")
    return text


def _quote_environment_value(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def read_environment_file(path: Optional[Path] = None) -> dict[str, str]:
    target = path or dashboard_env_path()
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise ConfigurationError(f"cannot read dashboard environment {target}: {exc}") from exc

    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            fields = shlex.split(line, comments=True, posix=True)
        except ValueError as exc:
            raise ConfigurationError(
                f"invalid dashboard environment syntax at {target}:{line_number}"
            ) from exc
        if len(fields) != 1 or "=" not in fields[0]:
            raise ConfigurationError(
                f"invalid dashboard environment entry at {target}:{line_number}"
            )
        key, value = fields[0].split("=", 1)
        if key not in JELLYFIN_ENV_KEYS:
            continue
        values[key] = value
    return values


def write_environment_file(
    values: Mapping[str, str],
    path: Optional[Path] = None,
) -> None:
    target = path or dashboard_env_path()
    if target.is_symlink():
        raise ConfigurationError(f"refusing to replace symlinked dashboard environment: {target}")

    cleaned: dict[str, str] = {}
    for key, raw_value in values.items():
        if key not in JELLYFIN_ENV_KEYS:
            raise ConfigurationError(f"unsupported dashboard environment key: {key}")
        value = _validate_env_value(raw_value, key)
        if value != "":
            cleaned[key] = value

    try:
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        target.parent.chmod(0o700)
    except OSError as exc:
        raise ConfigurationError(f"cannot prepare dashboard configuration directory: {exc}") from exc

    if not cleaned:
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise ConfigurationError(f"cannot remove dashboard environment {target}: {exc}") from exc
        return

    body = "# Managed by Open MMI. Do not commit this file.\n"
    body += "".join(
        f"{key}={_quote_environment_value(cleaned[key])}\n"
        for key in JELLYFIN_ENV_KEYS
        if key in cleaned
    )

    temporary: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=target.parent,
            prefix=target.name + ".",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        temporary.replace(target)
        target.chmod(0o600)
    except OSError as exc:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass
        raise ConfigurationError(f"cannot write dashboard environment {target}: {exc}") from exc


def _flag(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def jellyfin_environment_status(
    saved: Optional[Mapping[str, str]] = None,
    active: Optional[Mapping[str, str]] = None,
) -> dict[str, Any]:
    saved_values = dict(saved if saved is not None else read_environment_file())
    active_values = dict(active if active is not None else os.environ)
    url = saved_values.get("OPEN_MMI_JELLYFIN_URL", "")
    token_set = bool(saved_values.get("OPEN_MMI_JELLYFIN_TOKEN"))
    password_set = "OPEN_MMI_JELLYFIN_PASSWORD" in saved_values
    username = saved_values.get("OPEN_MMI_JELLYFIN_USERNAME", "")
    auth_mode = "token" if token_set else "username" if username and password_set else ""
    relevant_active = {key: active_values.get(key, "") for key in JELLYFIN_ENV_KEYS}
    relevant_saved = {key: saved_values.get(key, "") for key in JELLYFIN_ENV_KEYS}
    return {
        "configured": bool(url and auth_mode),
        "url": url,
        "auth_mode": auth_mode,
        "username": username,
        "user_id": saved_values.get("OPEN_MMI_JELLYFIN_USER_ID", ""),
        "library_id": saved_values.get("OPEN_MMI_JELLYFIN_LIBRARY_ID", ""),
        "session_id": saved_values.get("OPEN_MMI_JELLYFIN_SESSION_ID", ""),
        "device": saved_values.get("OPEN_MMI_JELLYFIN_DEVICE", ""),
        "token_configured": token_set,
        "password_configured": password_set,
        "insecure_tls": _flag(saved_values.get("OPEN_MMI_JELLYFIN_INSECURE_TLS")),
        "allow_global": _flag(saved_values.get("OPEN_MMI_JELLYFIN_ALLOW_GLOBAL")),
        "restart_required": relevant_active != relevant_saved,
        "path": str(dashboard_env_path()),
    }


def _normalise_url(value: Any) -> str:
    url = _validate_env_value(value, "Jellyfin URL").strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigurationError("Jellyfin URL must be an absolute http:// or https:// URL")
    if parsed.username or parsed.password:
        raise ConfigurationError("Jellyfin URL may not contain embedded credentials")
    return url


def jellyfin_values_from_payload(
    payload: Mapping[str, Any],
    existing: Optional[Mapping[str, str]] = None,
) -> dict[str, str]:
    current = dict(existing if existing is not None else read_environment_file())
    auth_mode = str(payload.get("auth_mode") or "").strip().lower()
    if auth_mode not in {"token", "username"}:
        raise ConfigurationError("Jellyfin authentication mode must be token or username")

    values: dict[str, str] = {
        "OPEN_MMI_JELLYFIN_URL": _normalise_url(payload.get("url")),
        "OPEN_MMI_JELLYFIN_USER_ID": _validate_env_value(payload.get("user_id"), "Jellyfin user ID").strip(),
        "OPEN_MMI_JELLYFIN_LIBRARY_ID": _validate_env_value(payload.get("library_id"), "Jellyfin library ID").strip(),
        "OPEN_MMI_JELLYFIN_SESSION_ID": _validate_env_value(payload.get("session_id"), "Jellyfin session ID").strip(),
        "OPEN_MMI_JELLYFIN_DEVICE": _validate_env_value(payload.get("device"), "Jellyfin device").strip(),
        "OPEN_MMI_JELLYFIN_INSECURE_TLS": "1" if bool(payload.get("insecure_tls")) else "0",
        "OPEN_MMI_JELLYFIN_ALLOW_GLOBAL": "1" if bool(payload.get("allow_global")) else "0",
    }

    if auth_mode == "token":
        token = _validate_env_value(payload.get("token"), "Jellyfin token").strip()
        if not token:
            token = current.get("OPEN_MMI_JELLYFIN_TOKEN", "")
        if not token:
            raise ConfigurationError("Jellyfin token is required")
        values["OPEN_MMI_JELLYFIN_TOKEN"] = token
        username = _validate_env_value(payload.get("username"), "Jellyfin username").strip()
        if username:
            values["OPEN_MMI_JELLYFIN_USERNAME"] = username
    else:
        username = _validate_env_value(payload.get("username"), "Jellyfin username").strip()
        password = _validate_env_value(payload.get("password"), "Jellyfin password")
        if not password and current.get("OPEN_MMI_JELLYFIN_USERNAME") == username:
            password = current.get("OPEN_MMI_JELLYFIN_PASSWORD", "")
        if not username or not password:
            raise ConfigurationError("Jellyfin username and password are required")
        values["OPEN_MMI_JELLYFIN_USERNAME"] = username
        values["OPEN_MMI_JELLYFIN_PASSWORD"] = password

    return {key: value for key, value in values.items() if value != ""}


def restart_dashboard(
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> None:
    result = runner(
        ["systemctl", "--user", "restart", DASHBOARD_SERVICE],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "systemctl failed").strip()
        raise ConfigurationError(f"could not restart {DASHBOARD_SERVICE}: {detail}")


def client_is_loopback(address: Any) -> bool:
    try:
        host = address[0] if isinstance(address, (tuple, list)) else str(address)
        return ipaddress.ip_address(str(host)).is_loopback
    except (ValueError, TypeError, IndexError):
        return False
