#!/usr/bin/env python3
import glob, os
import subprocess
import shutil

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

# Optional tuning
MIN_PERCENT = 5
GAMMA = 1.0  # set ~1.6 for smoother low-end control


# ---------------------------
# Backend layer (NEW CORE FIX)
# ---------------------------

def _set_brightness(percent: int):
    percent = max(0, min(100, int(percent)))

    # Preferred cross-device backend
    if shutil.which("brightnessctl"):
        subprocess.run(
            ["brightnessctl", "set", f"{percent}%"],
            check=False
        )
        return

    # Fallback: sysfs
    _set_sysfs(percent)


def _set_sysfs(percent: int):
    p = max(MIN_PERCENT, min(100, int(percent)))

    # gamma curve (optional)
    if GAMMA != 1.0:
        p_norm = (p / 100.0) ** GAMMA
    else:
        p_norm = (p / 100.0)

    val = max(1, int(round(p_norm * MAX)))

    try:
        with open(BL_BRIGHT, "w") as f:
            f.write(str(val))
    except PermissionError as e:
        print("[brightness] Permission error writing sysfs:", e)


# ---------------------------
# CAN mapping layer
# ---------------------------

def _apply_percent(p):
    # p comes in already scaled 0–100

    # OPTIONAL inversion (keep if your UI expects it)
    p = 100 - p

    _set_brightness(p)


def set_percent(percent):
    """Direct brightness control (0–100)."""
    _apply_percent(percent)


def from_can(value):
    """
    CAN dimmer byte:
    0x00–0x64 → 0–100%
    """
    v = int(value)

    if v < 0:
        v = 0
    if v > 0x64:
        v = 0x64

    percent = round((v / 0x64) * 100)

    _apply_percent(percent)