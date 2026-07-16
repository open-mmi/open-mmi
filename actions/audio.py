"""Audio control actions.

Supports:
- Volume control via PulseAudio/PipeWire (pactl)
- BlueZ AVRCP transport for connected phones
- MPRIS transport via playerctl
- uinput media-key fallback
"""

import logging
import os
import re
import shlex
import shutil
import subprocess
from typing import List, Optional, Tuple

logger = logging.getLogger("canbusd.actions.audio")

SUBPROCESS_TIMEOUT = 5  # seconds
BLUEZ_TIMEOUT = 2  # seconds

_BLUEZ_PLAYER_RE = re.compile(r"(/org/bluez/[A-Za-z0-9_./-]+/player[0-9]+)\b")


def _run_pc(args: List[str]) -> Tuple[bool, str]:
    """Run playerctl command safely with timeout.
    
    Args:
        args: playerctl command arguments
        
    Returns:
        (success: bool, stderr: str)
    """
    try:
        p = subprocess.run(
            ["playerctl", *args],
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT
        )
        ok = (p.returncode == 0)
        return ok, (p.stderr or "")
    except subprocess.TimeoutExpired:
        logger.warning(f"playerctl timeout: {' '.join(args)}")
        return False, "timeout"
    except FileNotFoundError:
        logger.warning("playerctl not installed")
        return False, "not found"
    except Exception as e:
        logger.error(f"playerctl error: {e}")
        return False, str(e)


def _fallback(name: str, *fargs) -> None:
    """Fallback to media key uinput if local media control is unavailable."""
    try:
        from . import keys
        getattr(keys, name)(*fargs)
    except Exception as e:
        logger.error(f"Fallback action failed: {name} - {e}")


def _bluez_busctl_executable() -> Optional[str]:
    configured = os.getenv("OPEN_MMI_BLUETOOTH_BUSCTL", "").strip()
    if configured:
        return configured if os.path.isfile(configured) and os.access(configured, os.X_OK) else None
    return shutil.which("busctl")


def _bluez_busctl(*arguments: str) -> Optional[str]:
    executable = _bluez_busctl_executable()
    if not executable:
        return None
    try:
        completed = subprocess.run(
            [executable, "--system", "--no-pager", *arguments],
            capture_output=True,
            text=True,
            timeout=BLUEZ_TIMEOUT,
            check=False,
            env={**os.environ, "LC_ALL": "C", "LANG": "C"},
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _bluez_player_status(path: str) -> Optional[str]:
    output = _bluez_busctl(
        "get-property",
        "org.bluez",
        path,
        "org.bluez.MediaPlayer1",
        "Status",
    )
    if not output:
        return None
    try:
        tokens = shlex.split(output)
    except ValueError:
        return None
    if len(tokens) < 2 or tokens[0] != "s":
        return None
    return tokens[1].strip().lower()


def _bluez_players() -> List[Tuple[str, str]]:
    output = _bluez_busctl("tree", "org.bluez")
    if not output:
        return []
    records = []
    for path in sorted(set(_BLUEZ_PLAYER_RE.findall(output))):
        status = _bluez_player_status(path)
        if status:
            records.append((path, status))
    records.sort(
        key=lambda item: {
            "playing": 0,
            "forward-seek": 1,
            "reverse-seek": 1,
            "paused": 2,
            "stopped": 3,
        }.get(item[1], 4)
    )
    return records


def _run_bluez_transport(command: str, *, active_only: bool = False) -> bool:
    """Control the current BlueZ AVRCP player without using the web server."""

    players = _bluez_players()
    if active_only:
        players = [
            item for item in players
            if item[1] in {"playing", "forward-seek", "reverse-seek"}
        ]
    if not players:
        return False

    path, status = players[0]
    methods = {
        "next": "Next",
        "previous": "Previous",
        "stop": "Stop",
    }
    if command == "play-pause":
        method = "Pause" if status in {"playing", "forward-seek", "reverse-seek"} else "Play"
    else:
        method = methods.get(command)
    if not method:
        return False

    result = _bluez_busctl(
        "call",
        "org.bluez",
        path,
        "org.bluez.MediaPlayer1",
        method,
    )
    if result is None:
        return False
    logger.debug("BlueZ media action=%s player=%s status=%s", method, path, status)
    return True


def volume_up(step: str = "+5%") -> None:
    """Increase volume via PulseAudio/PipeWire."""
    try:
        subprocess.run(
            ["pactl", "set-sink-volume", "@DEFAULT_SINK@", step],
            timeout=SUBPROCESS_TIMEOUT,
            check=False
        )
    except subprocess.TimeoutExpired:
        logger.error(f"pactl volume_up timeout")
    except FileNotFoundError:
        logger.error("pactl not installed")
    except Exception as e:
        logger.error(f"volume_up failed: {e}")


def volume_down(step: str = "-5%") -> None:
    """Decrease volume via PulseAudio/PipeWire."""
    try:
        subprocess.run(
            ["pactl", "set-sink-volume", "@DEFAULT_SINK@", step],
            timeout=SUBPROCESS_TIMEOUT,
            check=False
        )
    except subprocess.TimeoutExpired:
        logger.error(f"pactl volume_down timeout")
    except FileNotFoundError:
        logger.error("pactl not installed")
    except Exception as e:
        logger.error(f"volume_down failed: {e}")


def mute_toggle() -> None:
    """Toggle mute via PulseAudio/PipeWire."""
    try:
        subprocess.run(
            ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"],
            timeout=SUBPROCESS_TIMEOUT,
            check=False
        )
    except subprocess.TimeoutExpired:
        logger.error(f"pactl mute_toggle timeout")
    except FileNotFoundError:
        logger.error("pactl not installed")
    except Exception as e:
        logger.error(f"mute_toggle failed: {e}")


def _transport(command: str, fallback: str) -> None:
    """Control active Bluetooth, then MPRIS, then paused Bluetooth or uinput."""

    # A playing phone is unambiguously the active remote target and should be
    # controlled directly through BlueZ. This fixes steering-wheel pause while
    # avoiding dependence on browser focus or synthetic-key handling.
    if _run_bluez_transport(command, active_only=True):
        return

    ok, _err = _run_pc([command])
    if ok:
        return

    # If no local MPRIS player accepted the command, allow a connected paused
    # phone to resume through AVRCP before falling back to a synthetic key.
    if _run_bluez_transport(command, active_only=False):
        return

    _fallback(fallback)


def play_pause() -> None:
    """Play/pause via playerctl, falling back to a media key."""
    _transport("play-pause", "play_pause")


def next_track() -> None:
    """Select the next track, falling back to a media key."""
    _transport("next", "next_track")


def prev_track() -> None:
    """Select the previous track, falling back to a media key."""
    _transport("previous", "prev_track")


def stop() -> None:
    """Stop playback, falling back to a media key."""
    _transport("stop", "stop")
