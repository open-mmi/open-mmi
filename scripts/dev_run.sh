#!/usr/bin/env bash
set -euo pipefail

# Development run script - runs canbusd without systemd

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Check dependencies
if ! python3 -c "import can" 2>/dev/null; then
    echo "[dev] ERROR: python-can not installed"
    echo "[dev] Install with: pip install python-can evdev"
    exit 1
fi

echo "[dev] Starting open-mmi canbusd (development mode)"
echo "[dev] Press Ctrl+C to stop"
echo "[dev]"

# Run with debug logging by default
export OPEN_MMI_LOG_LEVEL="${OPEN_MMI_LOG_LEVEL:-DEBUG}"
export OPEN_MMI_VEHICLE="${OPEN_MMI_VEHICLE:-seat_1p}"
export OPEN_MMI_BINDINGS="${OPEN_MMI_BINDINGS:-default}"

cd "$REPO_ROOT"
python3 canbusd/canbusd.py
