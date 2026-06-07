"""Virtual keyboard input actions via uinput.

Provides synthetic media key injection with thread-safe access.
"""

import threading
import logging
from evdev import UInput, ecodes as e

logger = logging.getLogger("canbusd.actions.keys")

# Singleton persistent virtual keyboard with required key capabilities
_caps = {
    e.EV_KEY: [
        e.KEY_PLAYPAUSE, e.KEY_NEXTSONG, e.KEY_PREVIOUSSONG, e.KEY_STOPCD,
        e.KEY_MUTE, e.KEY_VOLUMEUP, e.KEY_VOLUMEDOWN, e.KEY_LEFT, e.KEY_RIGHT
    ]
}

_ui: UInput | None = None
_lock = threading.Lock()


def _get_ui() -> UInput:
    """Get or create the virtual input device with thread safety."""
    global _ui
    with _lock:
        if _ui is None:
            try:
                _ui = UInput(_caps, name="canbusd-input")
                logger.debug("Virtual input device created")
            except Exception as e:
                logger.error(f"Failed to create virtual input device: {e}")
                raise
        return _ui


def _press(code: int) -> None:
    """Inject a key press and release event."""
    try:
        ui = _get_ui()
        with _lock:  # Ensure atomic key press/release
            ui.write(e.EV_KEY, code, 1)  # Press
            ui.write(e.EV_KEY, code, 0)  # Release
            ui.syn()  # Sync
    except Exception as e:
        logger.error(f"Key press failed: {e}")


def play_pause() -> None:
    """Inject PLAY/PAUSE media key."""
    _press(e.KEY_PLAYPAUSE)


def next_track() -> None:
    """Inject NEXT TRACK media key."""
    _press(e.KEY_NEXTSONG)


def prev_track() -> None:
    """Inject PREVIOUS TRACK media key."""
    _press(e.KEY_PREVIOUSSONG)


def stop() -> None:
    """Inject STOP media key."""
    _press(e.KEY_STOPCD)


def mute_toggle() -> None:
    """Inject MUTE media key."""
    _press(e.KEY_MUTE)


def volume_up() -> None:
    """Inject VOLUME UP media key."""
    _press(e.KEY_VOLUMEUP)


def volume_down() -> None:
    """Inject VOLUME DOWN media key."""
    _press(e.KEY_VOLUMEDOWN)


def arrow_left() -> None:
    """Inject LEFT ARROW key."""
    _press(e.KEY_LEFT)


def arrow_right() -> None:
    """Inject RIGHT ARROW key."""
    _press(e.KEY_RIGHT)
