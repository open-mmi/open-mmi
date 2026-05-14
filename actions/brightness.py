#!/usr/bin/env python3
import glob, os

# Prefer common device names but fall back gracefully
PREFER = ["intel_backlight", "amdgpu_bl0", "acpi_video0", "surface_acpi"]

def _find_backlight():
    cands = []
    for p in glob.glob("/sys/class/backlight/*/brightness"):
        name = os.path.basename(os.path.dirname(p))
        priority = PREFER.index(name) if name in PREFER else len(PREFER) + 1
        cands.append((priority, p))
    if not cands:
        raise RuntimeError("No backlight device found in /sys/class/backlight")
    cands.sort()
    return cands[0][1]

BL_BRIGHT = _find_backlight()
BL_MAX = BL_BRIGHT.replace("brightness", "max_brightness")
MAX = int(open(BL_MAX).read().strip())

# Optional floor so the screen never goes totally dark
MIN_PERCENT = 5
GAMMA = 1.0  # set to ~1.6 if you want more control at low levels

def _apply_percent(p):
    # Invert brightness so higher percent = dimmer screen
    p = 100 - p
    p = max(MIN_PERCENT, min(100, int(p)))

    # simple gamma mapping
    if GAMMA != 1.0:
        p_norm = (p / 100.0) ** GAMMA
    else:
        p_norm = (p / 100.0)

    val = max(1, int(round(p_norm * MAX)))
    with open(BL_BRIGHT, "w") as f:
        f.write(str(val))

def set_percent(percent):
    """Direct percent (0–100) control (inverted mapping)."""
    _apply_percent(percent)

def from_can(value):
    """
    Map CAN dimmer byte (0x00..0x64) to inverted 0..100%.
    Value arrives as an int from canbusd.
    """
    v = int(value)
    if v < 0: v = 0
    if v > 0x64: v = 0x64
    percent = round((v / 0x64) * 100)
    _apply_percent(percent)
