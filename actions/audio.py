import subprocess

def _run_pc(args):
    # Run playerctl; return (ok, stderr)
    p = subprocess.run(["playerctl", *args], capture_output=True, text=True)
    ok = (p.returncode == 0)
    return ok, (p.stderr or "")

def _fallback(name, *fargs):
    # Lazy import to avoid circulars if actions package reloads
    from . import keys
    getattr(keys, name)(*fargs)

# Volume via PulseAudio/PipeWire directly (works regardless of MPRIS)
def volume_up(step="+5%"):
    subprocess.Popen(["pactl", "set-sink-volume", "@DEFAULT_SINK@", step])

def volume_down(step="-5%"):
    subprocess.Popen(["pactl", "set-sink-volume", "@DEFAULT_SINK@", step])

def mute_toggle():
    subprocess.Popen(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"])

# Transport: playerctl first, else media keys via uinput
def play_pause():
    ok, err = _run_pc(["play-pause"])
    if not ok and "No players found" in err:
        _fallback("play_pause")

def next_track():
    ok, err = _run_pc(["next"])
    if not ok and "No players found" in err:
        _fallback("next_track")

def prev_track():
    ok, err = _run_pc(["previous"])
    if not ok and "No players found" in err:
        _fallback("prev_track")

def stop():
    ok, err = _run_pc(["stop"])
    if not ok and "No players found" in err:
        _fallback("stop")
