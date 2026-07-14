"""Audio control actions.

Supports:
- Volume control via PulseAudio/PipeWire (pactl)
- Media transport via playerctl with fallback to uinput media keys
"""

import subprocess
import logging
from typing import List, Tuple

logger = logging.getLogger("canbusd.actions.audio")

SUBPROCESS_TIMEOUT = 5  # seconds


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
    """Fallback to media key uinput if playerctl unavailable."""
    try:
        from . import keys
        getattr(keys, name)(*fargs)
    except Exception as e:
        logger.error(f"Fallback action failed: {name} - {e}")


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
    """Run a player command and use the media-key fallback on any failure."""

    ok, _err = _run_pc([command])
    if not ok:
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
