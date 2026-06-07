#!/usr/bin/env bash
set -euo pipefail

APP_NAME="open-mmi"
INSTALL_DIR="/opt/open-mmi"

REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)
USER_ID=$(id -u "$REAL_USER")

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[update] Updating $APP_NAME..."

# Check if installed
if [ ! -d "$INSTALL_DIR" ]; then
    echo "[update] ERROR: $APP_NAME not installed at $INSTALL_DIR"
    echo "[update] Run './scripts/install.sh' first"
    exit 1
fi

# Stop daemon
echo "[update] Stopping daemon..."
export XDG_RUNTIME_DIR="/run/user/$USER_ID"

sudo -u "$REAL_USER" \
    XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
    systemctl --user stop canbusd || true

# Pull latest changes
echo "[update] Pulling latest changes..."
cd "$REPO_ROOT"
git fetch origin main
git merge origin/main

# Upgrade Python dependencies
echo "[update] Upgrading Python dependencies..."
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install --upgrade \
    python-can \
    evdev

# Update application files
echo "[update] Updating application files..."
cp -r "$REPO_ROOT/canbusd" "$INSTALL_DIR/"
cp -r "$REPO_ROOT/vehicles" "$INSTALL_DIR/"
cp -r "$REPO_ROOT/bindings" "$INSTALL_DIR/"
cp -r "$REPO_ROOT/actions" "$INSTALL_DIR/"
cp "$REPO_ROOT/pyproject.toml" "$INSTALL_DIR/"

# Update systemd service if changed
if [ -f "$REPO_ROOT/systemd/user/canbusd.service" ]; then
    echo "[update] Updating systemd service..."
    cp \
      "$REPO_ROOT/systemd/user/canbusd.service" \
      "$REAL_HOME/.config/systemd/user/canbusd.service"
    
    chown "$REAL_USER:$REAL_USER" \
      "$REAL_HOME/.config/systemd/user/canbusd.service"
    
    sudo -u "$REAL_USER" \
        XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
        systemctl --user daemon-reload
fi

# Update udev rules if changed
if [ -f "$REPO_ROOT/udev/80-canbus.rules" ]; then
    echo "[update] Updating udev rules..."
    sudo cp \
      "$REPO_ROOT/udev/80-canbus.rules" \
      /etc/udev/rules.d/
    
    sudo udevadm control --reload-rules
    sudo udevadm trigger
fi

# Restart daemon
echo "[update] Restarting daemon..."
sudo -u "$REAL_USER" \
    XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
    systemctl --user restart canbusd

# Verify
echo "[update] Verifying installation..."
if sudo -u "$REAL_USER" \
    XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
    systemctl --user is-active canbusd > /dev/null 2>&1; then
    echo "[update] ✓ Update complete - daemon running"
else
    echo "[update] ✗ Update complete but daemon failed to start"
    echo "[update] Check logs: journalctl --user -u canbusd -f"
    exit 1
fi
