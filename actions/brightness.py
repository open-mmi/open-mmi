#!/usr/bin/env python3

import subprocess
import shutil

if not shutil.which("brightnessctl"):
    raise RuntimeError(
        "brightnessctl is required but not installed - Install with: sudo apt install brightnessctl"
    )


def _set_brightness(percent: int):
    percent = max(0, min(100, int(percent)))

    subprocess.run(
        ["brightnessctl", "set", f"{percent}%"],
        check=False
    )


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
