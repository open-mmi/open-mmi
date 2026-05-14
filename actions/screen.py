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

def wake_and_login(user="pitto"):
    """
    Wake display and *attempt* to switch to (or start) the user's session.
    - LightDM: dm-tool will switch to user (may still prompt for password unless autologin is set).
    - If you don’t use LightDM, you can replace the command below with what your greeter supports.
    """
    on()
    # Try LightDM’s dm-tool (safe no-op if not present)
    try:
        subprocess.Popen(["dm-tool", "switch-to-user", user], env=_env())
    except FileNotFoundError:
        pass
