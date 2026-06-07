"""Display power and user session control.

Uses X11 DPMS for power control and dm-tool for user switching.
"""

import os
import subprocess
import logging
from typing import Optional

logger = logging.getLogger("canbusd.actions.screen")

SUBPROCESS_TIMEOUT = 5  # seconds

DISPLAY = os.environ.get("DISPLAY", ":0")
XAUTH = os.environ.get("XAUTHORITY", os.path.expanduser("~/.Xauthority"))


def _env() -> dict:
    """Get environment with X11 variables for subprocess."""
    env = os.environ.copy()
    env.setdefault("DISPLAY", DISPLAY)
    env.setdefault("XAUTHORITY", XAUTH)
    return env


def off() -> None:
    """Turn display off via DPMS."""
    try:
        subprocess.run(
            ["xset", "dpms", "force", "off"],
            env=_env(),
            timeout=SUBPROCESS_TIMEOUT,
            check=False
        )
        logger.debug("Display turned off")
    except subprocess.TimeoutExpired:
        logger.error("xset off timeout")
    except FileNotFoundError:
        logger.error("xset not installed")
    except Exception as e:
        logger.error(f"Display off failed: {e}")


def on() -> None:
    """Turn display on via DPMS."""
    try:
        subprocess.run(
            ["xset", "dpms", "force", "on"],
            env=_env(),
            timeout=SUBPROCESS_TIMEOUT,
            check=False
        )
        logger.debug("Display turned on")
    except subprocess.TimeoutExpired:
        logger.error("xset on timeout")
    except FileNotFoundError:
        logger.error("xset not installed")
    except Exception as e:
        logger.error(f"Display on failed: {e}")


def wake_and_login(user: Optional[str] = None) -> None:
    """Wake display and optionally switch to a user session.
    
    Args:
        user: Optional username to switch to via display manager
    """
    on()

    if user is None:
        return

    try:
        subprocess.run(
            ["dm-tool", "switch-to-user", user],
            env=_env(),
            timeout=SUBPROCESS_TIMEOUT,
            check=False
        )
        logger.debug(f"Switched to user: {user}")
    except FileNotFoundError:
        logger.warning("dm-tool not found - user switch unavailable")
    except subprocess.TimeoutExpired:
        logger.error(f"dm-tool user switch timeout for {user}")
    except Exception as e:
        logger.error(f"User switch failed: {e}")
