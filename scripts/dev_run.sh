#!/usr/bin/env bash
set -euo pipefail

# Development run script - runs canbusd without systemd.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Check dependencies before replacing this shell with the daemon process.
if ! python3 -c "import can, evdev" 2>/dev/null; then
    echo "[dev] ERROR: required Python dependencies are not installed" >&2
    echo "[dev] Install with: python3 -m pip install -e ." >&2
    exit 1
fi

echo "[dev] Starting open-mmi canbusd (development mode)"
echo "[dev] Press Ctrl+C to stop"
echo "[dev]"

export OPEN_MMI_LOG_LEVEL="${OPEN_MMI_LOG_LEVEL:-DEBUG}"
export OPEN_MMI_VEHICLE="${OPEN_MMI_VEHICLE:-seat_1p}"
export OPEN_MMI_BINDINGS="${OPEN_MMI_BINDINGS:-default}"

cd "$REPO_ROOT"
exec python3 -m canbusd.core "$@"
