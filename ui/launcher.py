#!/usr/bin/env python3
"""Universal launcher for Open MMI user interfaces.

The launcher keeps dashboard process management in systemd, waits for the
local health endpoint, and only then starts the configured browser.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, List, Mapping, MutableMapping, Optional, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

SERVICE_NAME = "open-mmi-dashboard.service"
DEFAULT_CONFIG: dict[str, Any] = {
    "default_ui": "web",
    "web_url": "http://127.0.0.1:8765",
    "browser_mode": "kiosk",
    "browser_command": "auto",
    "startup_timeout_seconds": 12.0,
    "health_poll_interval_seconds": 0.25,
}
BROWSER_CANDIDATES = (
    "chromium",
    "chromium-browser",
    "google-chrome",
    "google-chrome-stable",
    "firefox",
)
TERMINAL_CANDIDATES = (
    "x-terminal-emulator",
    "gnome-terminal",
    "konsole",
    "xfce4-terminal",
    "xterm",
)


class LauncherError(RuntimeError):
    """A user-facing launcher failure."""


def default_config_path() -> Path:
    config_home = os.getenv("XDG_CONFIG_HOME")
    if config_home:
        return Path(config_home) / "open-mmi" / "launcher.json"
    return Path.home() / ".config" / "open-mmi" / "launcher.json"


def _validate_config(config: MutableMapping[str, Any]) -> None:
    if config["default_ui"] not in {"web", "tui"}:
        raise LauncherError("default_ui must be 'web' or 'tui'")

    if config["browser_mode"] not in {"kiosk", "fullscreen", "window"}:
        raise LauncherError("browser_mode must be 'kiosk', 'fullscreen', or 'window'")

    parsed = urlparse(str(config["web_url"]))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise LauncherError("web_url must be an absolute http:// or https:// URL")

    for key in ("startup_timeout_seconds", "health_poll_interval_seconds"):
        try:
            value = float(config[key])
        except (TypeError, ValueError) as exc:
            raise LauncherError(f"{key} must be numeric") from exc
        if value <= 0:
            raise LauncherError(f"{key} must be greater than zero")
        config[key] = value

    command = config["browser_command"]
    if not isinstance(command, (str, list, tuple)):
        raise LauncherError("browser_command must be 'auto', a command string, or an argument list")
    if isinstance(command, (list, tuple)) and not all(isinstance(item, str) for item in command):
        raise LauncherError("browser_command argument lists may contain strings only")


def load_config(path: Optional[Path] = None) -> dict[str, Any]:
    """Load user configuration, merging it over conservative defaults."""

    target = path or default_config_path()
    config = dict(DEFAULT_CONFIG)
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        _validate_config(config)
        return config
    except json.JSONDecodeError as exc:
        raise LauncherError(f"invalid launcher configuration in {target}: {exc}") from exc
    except OSError as exc:
        raise LauncherError(f"cannot read launcher configuration {target}: {exc}") from exc

    if not isinstance(raw, Mapping):
        raise LauncherError(f"launcher configuration root must be an object: {target}")

    unknown = sorted(set(raw) - set(DEFAULT_CONFIG))
    if unknown:
        raise LauncherError(f"unknown launcher configuration keys: {', '.join(unknown)}")

    config.update(raw)
    _validate_config(config)
    return config


def save_default_ui(ui_name: str, path: Optional[Path] = None) -> None:
    """Persist only the selected default while preserving existing settings."""

    target = path or default_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    current: dict[str, Any] = {}
    try:
        loaded = json.loads(target.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            current.update(loaded)
    except FileNotFoundError:
        pass
    except (OSError, json.JSONDecodeError) as exc:
        raise LauncherError(f"cannot update launcher configuration {target}: {exc}") from exc

    current["default_ui"] = ui_name
    merged = dict(DEFAULT_CONFIG)
    merged.update(current)
    _validate_config(merged)

    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(target)


def health_url(web_url: str) -> str:
    return urljoin(web_url.rstrip("/") + "/", "api/health")


def check_health(endpoint: str, timeout: float = 1.0) -> bool:
    """Return true when the dashboard HTTP server returns its health payload."""

    request = Request(endpoint, headers={"Accept": "application/json", "User-Agent": "open-mmi-launcher"})
    try:
        with urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                return False
            payload = json.loads(response.read(1024 * 1024).decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError, OSError):
        return False
    return isinstance(payload, dict) and "health" in payload


def run_command(args: Sequence[str], *, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        check=False,
        text=True,
        stdout=subprocess.PIPE if capture_output else None,
        stderr=subprocess.PIPE if capture_output else None,
    )


def service_is_active(
    command_runner: Callable[..., subprocess.CompletedProcess[str]] = run_command,
) -> bool:
    result = command_runner(
        ["systemctl", "--user", "is-active", "--quiet", SERVICE_NAME],
        capture_output=True,
    )
    return result.returncode == 0


def ensure_dashboard_ready(
    config: Mapping[str, Any],
    *,
    health_checker: Callable[[str, float], bool] = check_health,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] = run_command,
    sleeper: Callable[[float], None] = time.sleep,
) -> None:
    """Start or restart the dashboard service and wait for HTTP readiness."""

    endpoint = health_url(str(config["web_url"]))
    if health_checker(endpoint, 0.75):
        return

    action = "restart" if service_is_active(command_runner) else "start"
    result = command_runner(
        ["systemctl", "--user", action, SERVICE_NAME],
        capture_output=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "systemctl failed").strip()
        raise LauncherError(f"could not {action} {SERVICE_NAME}: {detail}")

    timeout = float(config["startup_timeout_seconds"])
    interval = float(config["health_poll_interval_seconds"])
    attempts = max(1, math.ceil(timeout / interval))
    request_timeout = min(0.75, max(0.1, interval))
    for _ in range(attempts):
        sleeper(interval)
        if health_checker(endpoint, request_timeout):
            return

    raise LauncherError(
        f"dashboard did not become healthy within {timeout:g} seconds; "
        f"check: journalctl --user -u {SERVICE_NAME}"
    )


def _configured_browser_parts(value: Any) -> Optional[List[str]]:
    if value == "auto":
        return None
    if isinstance(value, str):
        parts = shlex.split(value)
    else:
        parts = list(value)
    if not parts:
        raise LauncherError("browser_command may not be empty")
    return parts


def resolve_browser(configured: Any) -> list[str]:
    parts = _configured_browser_parts(configured)
    if parts is not None:
        executable = shutil.which(parts[0])
        if executable is None:
            raise LauncherError(f"configured browser was not found: {parts[0]}")
        parts[0] = executable
        return parts

    for candidate in BROWSER_CANDIDATES:
        executable = shutil.which(candidate)
        if executable:
            return [executable]
    raise LauncherError(
        "no supported browser found; install Chromium/Firefox or set browser_command in launcher.json"
    )


def build_browser_command(base_command: Sequence[str], web_url: str, mode: str) -> list[str]:
    """Build a browser invocation without invoking a shell."""

    command = [part.replace("{url}", web_url) for part in base_command]
    if any("{url}" in part for part in base_command):
        return command

    name = Path(command[0]).name.lower()
    if "chrom" in name or "chrome" in name:
        common = ["--no-first-run", "--disable-session-crashed-bubble"]
        if mode == "kiosk":
            return command + ["--kiosk", f"--app={web_url}"] + common
        if mode == "fullscreen":
            return command + ["--start-fullscreen", f"--app={web_url}"] + common
        return command + [web_url] + common

    if "firefox" in name:
        if mode in {"kiosk", "fullscreen"}:
            return command + ["--kiosk", web_url]
        return command + [web_url]

    return command + [web_url]


def launch_browser(config: Mapping[str, Any]) -> list[str]:
    base = resolve_browser(config["browser_command"])
    command = build_browser_command(base, str(config["web_url"]), str(config["browser_mode"]))
    try:
        subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        raise LauncherError(f"could not start browser: {exc}") from exc
    return command


def _status_command() -> list[str]:
    installed = shutil.which("open-mmi-status")
    if installed:
        return [installed]
    return [sys.executable, "-m", "ui.dashboard.status_cli"]


def _terminal_command(terminal: str, status_command: Sequence[str]) -> list[str]:
    name = Path(terminal).name
    if name == "gnome-terminal":
        return [terminal, "--"] + list(status_command)
    if name == "xfce4-terminal":
        return [terminal, "--command", shlex.join(status_command)]
    return [terminal, "-e"] + list(status_command)


def launch_tui() -> int:
    status_command = _status_command()

    if sys.stdin.isatty() and sys.stdout.isatty():
        return run_command(status_command).returncode

    for candidate in TERMINAL_CANDIDATES:
        terminal = shutil.which(candidate)
        if terminal:
            try:
                subprocess.Popen(
                    _terminal_command(terminal, status_command),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
            except OSError as exc:
                raise LauncherError(f"could not start terminal: {exc}") from exc
            return 0
    raise LauncherError("no terminal emulator found for the TUI")


def choose_ui() -> str:
    if not sys.stdin.isatty():
        raise LauncherError("--choose requires an interactive terminal")
    print("Open MMI interface")
    print("  1. Web dashboard")
    print("  2. Terminal UI")
    while True:
        answer = input("Select [1-2]: ").strip().lower()
        if answer in {"1", "web", "w"}:
            return "web"
        if answer in {"2", "tui", "terminal", "t"}:
            return "tui"
        print("Please choose 1 or 2.", file=sys.stderr)


def status_payload(config: Mapping[str, Any], config_path: Path) -> dict[str, Any]:
    endpoint = health_url(str(config["web_url"]))
    return {
        "config_path": str(config_path),
        "default_ui": config["default_ui"],
        "web_url": config["web_url"],
        "health_url": endpoint,
        "service": SERVICE_NAME,
        "service_active": service_is_active(),
        "dashboard_reachable": check_health(endpoint),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch an Open MMI interface")
    parser.add_argument("ui", nargs="?", choices=("web", "tui"), help="override the configured interface")
    parser.add_argument("--choose", action="store_true", help="select the interface interactively")
    parser.add_argument("--remember", action="store_true", help="remember an explicit or chosen interface")
    parser.add_argument("--status", action="store_true", help="show launcher and dashboard status")
    parser.add_argument("--stop", action="store_true", help="stop the dashboard service")
    parser.add_argument("--config", type=Path, help="use an alternate launcher configuration file")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config_path = args.config or default_config_path()

    try:
        config = load_config(config_path)
        operation_count = sum(bool(value) for value in (args.choose, args.status, args.stop))
        if operation_count > 1:
            raise LauncherError("--choose, --status, and --stop are mutually exclusive")

        if args.status:
            print(json.dumps(status_payload(config, config_path), indent=2, sort_keys=True))
            return 0

        if args.stop:
            result = run_command(
                ["systemctl", "--user", "stop", SERVICE_NAME],
                capture_output=True,
            )
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "systemctl failed").strip()
                raise LauncherError(f"could not stop {SERVICE_NAME}: {detail}")
            return 0

        selected = choose_ui() if args.choose else (args.ui or str(config["default_ui"]))
        if args.remember:
            save_default_ui(selected, config_path)

        if selected == "tui":
            return launch_tui()

        ensure_dashboard_ready(config)
        launch_browser(config)
        return 0
    except LauncherError as exc:
        print(f"open-mmi-launcher: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
