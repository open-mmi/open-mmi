"""Audio control actions.

Supports:
- Volume control via PulseAudio/PipeWire (pactl)
- Media transport via playerctl with fallback to uinput media keys
"""

import subprocess
import logging
from typing import Tuple

logger = logging.getLogger("canbusd.actions.audio")

SUBPROCESS_TIMEOUT = 5  # seconds


def _run_pc(args: list) -> Tuple[bool, str]:
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


def play_pause() -> None:
    """Play/pause via playerctl, fallback to media key."""
    ok, err = _run_pc(["play-pause"])
    if not ok and "No players found" in err:
        _fallback("play_pause")


def next_track() -> None:
    """Next track via playerctl, fallback to media key."""
    ok, err = _run_pc(["next"])
    if not ok and "No players found" in err:
        _fallback("next_track")


def prev_track() -> None:
    """Previous track via playerctl, fallback to media key."""
    ok, err = _run_pc(["previous"])
    if not ok and "No players found" in err:
        _fallback("prev_track")


def stop() -> None:
    """Stop playback via playerctl, fallback to media key."""
    ok, err = _run_pc(["stop"])
    if not ok and "No players found" in err:
        _fallback("stop")
