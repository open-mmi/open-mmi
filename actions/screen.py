# actions/screen.py
import os, subprocess

DISPLAY = os.environ.get("DISPLAY", ":0")
XAUTH = os.environ.get("XAUTHORITY", os.path.expanduser("~/.Xauthority"))

def _env():
    env = os.environ.copy()
    env.setdefault("DISPLAY", DISPLAY)
    env.setdefault("XAUTHORITY", XAUTH)
    return env

def off():
    subprocess.Popen(["xset", "dpms", "force", "off"], env=_env())

def on():
    subprocess.Popen(["xset", "dpms", "force", "on"], env=_env())

def wake_and_login(user=None):
    """
    Wake display and optionally switch to a user session if a display manager exists.
    """
    on()

    if user is None:
        return

    try:
        subprocess.Popen(
            ["dm-tool", "switch-to-user", user],
            env=_env()
        )
    except FileNotFoundError:
        pass
