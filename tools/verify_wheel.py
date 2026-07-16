#!/usr/bin/env python3
"""Fail when an Open MMI wheel omits application modules or runtime assets."""

from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZipFile


REQUIRED_PATHS = {
    "actions/__init__.py",
    "bindings/default.json",
    "canbusd/core.py",
    "ui/dashboard/status_cli.py",
    "ui/web_dashboard/bluetooth.py",
    "ui/web_dashboard/jellyfin.py",
    "ui/web_dashboard/radio.py",
    "ui/web_dashboard/server.py",
    "ui/web_dashboard/usb.py",
    "ui/web_dashboard/static/api.js",
    "ui/web_dashboard/static/app.js",
    "ui/web_dashboard/static/preferences.js",
    "ui/web_dashboard/static/status.js",
    "ui/web_dashboard/static/navigation.js",
    "ui/web_dashboard/static/overlays.js",
    "ui/web_dashboard/static/vehicle.js",
    "ui/web_dashboard/static/media.js",
    "ui/web_dashboard/static/media-jellyfin.js",
    "ui/web_dashboard/static/media-radio.js",
    "ui/web_dashboard/static/media-usb.js",
    "ui/web_dashboard/static/media-bluetooth.js",
    "ui/web_dashboard/static/system-settings.js",
    "ui/web_dashboard/static/styles-system-settings.css",
    "ui/web_dashboard/static/index.html",
    "ui/web_dashboard/static/styles.css",
    "ui/web_dashboard/static/styles-core.css",
    "ui/web_dashboard/static/styles-media-layout.css",
    "ui/web_dashboard/static/styles-shell.css",
    "ui/web_dashboard/static/styles-media-sources.css",
    "ui/web_dashboard/static/styles-diagnostics.css",
    "ui/web_dashboard/static/styles-media-final.css",
    "vehicles/seat_1p/config.json",
}


def verify(wheel_path: Path) -> None:
    if not wheel_path.is_file():
        raise SystemExit(f"Wheel does not exist: {wheel_path}")

    with ZipFile(wheel_path) as archive:
        members = set(archive.namelist())

    missing = sorted(REQUIRED_PATHS - members)
    if missing:
        formatted = "\n".join(f"  - {path}" for path in missing)
        raise SystemExit(f"Wheel is missing required files:\n{formatted}")

    metadata = [name for name in members if name.endswith(".dist-info/METADATA")]
    if len(metadata) != 1:
        raise SystemExit(f"Expected exactly one METADATA file, found {len(metadata)}")

    print(f"Verified {wheel_path}: {len(members)} files, all required assets present")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    verify(args.wheel)


if __name__ == "__main__":
    main()
