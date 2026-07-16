"""Display brightness control via brightnessctl."""

import subprocess
import logging

logger = logging.getLogger("canbusd.actions.brightness")

SUBPROCESS_TIMEOUT = 5  # seconds


def _set_brightness(percent: int) -> None:
    """Set brightness to a percentage with range validation.
    
    Args:
        percent: Brightness percentage (0-100)
    """
    percent = max(0, min(100, int(percent)))

    try:
        subprocess.run(
            ["brightnessctl", "set", f"{percent}%"],
            timeout=SUBPROCESS_TIMEOUT,
            check=False
        )
        logger.debug(f"Brightness set to {percent}%")
    except subprocess.TimeoutExpired:
        logger.error(f"brightnessctl timeout")
    except FileNotFoundError:
        logger.error("brightnessctl not installed")
    except Exception as e:
        logger.error(f"Brightness control failed: {e}")


def _apply_percent(p: int) -> None:
    """Apply brightness with optional inversion.
    
    Args:
        p: Percentage value (0-100)
    """
    # OPTIONAL: invert if your UI/dimmer expects it
    p = 100 - p
    _set_brightness(p)


def set_percent(percent: int) -> None:
    """Set brightness directly (0-100).
    
    Args:
        percent: Brightness percentage
    """
    _apply_percent(percent)


def from_can(value: int) -> None:
    """Convert CAN dimmer byte to brightness.
    
    CAN protocol: 0x00-0x64 → 0-100%
    
    Args:
        value: CAN dimmer value (0x00-0x64)
    """
    try:
        v = int(value)
        # Clamp to valid range
        v = max(0, min(0x64, v))
        # Convert: 0x64 (100 decimal) = 100%
        percent = round((v / 0x64) * 100)
        _apply_percent(percent)
    except (ValueError, TypeError) as e:
        logger.error(f"Invalid CAN value: {value} - {e}")
