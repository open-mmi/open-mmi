#!/usr/bin/env bash
set -euo pipefail

APP_NAME="open-mmi"
INSTALL_DIR="/opt/open-mmi"

REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)

SERVICE_FILE="$REAL_HOME/.config/systemd/user/canbusd.service"

echo "[uninstall] Removing $APP_NAME..."

# ---------------------------------------------
# Stop and disable user service
# ---------------------------------------------
echo "[uninstall] Stopping systemd user service..."

USER_ID=$(id -u "$REAL_USER")
export XDG_RUNTIME_DIR="/run/user/$USER_ID"

if sudo -u "$REAL_USER" \
    XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
    systemctl --user list-unit-files | grep -q "^canbusd.service"; then

    sudo -u "$REAL_USER" \
        XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
        systemctl --user stop canbusd || true

    sudo -u "$REAL_USER" \
        XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
        systemctl --user disable canbusd || true
fi

# ---------------------------------------------
# Remove service file
# ---------------------------------------------
echo "[uninstall] Removing user service file..."

rm -f "$SERVICE_FILE"

sudo -u "$REAL_USER" \
    XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
    systemctl --user daemon-reload

# ---------------------------------------------
# Remove application files
# ---------------------------------------------
echo "[uninstall] Removing application files..."

sudo rm -rf "$INSTALL_DIR"

# ---------------------------------------------
# Remove udev rules
# ---------------------------------------------
if [ -f /etc/udev/rules.d/80-canbus.rules ]; then

    echo "[uninstall] Removing udev rules..."

    sudo rm -f /etc/udev/rules.d/80-canbus.rules

    sudo udevadm control --reload-rules
    sudo udevadm trigger
fi

echo "[uninstall] Uninstall complete."