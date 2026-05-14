#!/usr/bin/env bash
set -e

APP_NAME="open-mmi"
INSTALL_DIR="/opt/open-mmi"

echo "[uninstall] Removing $APP_NAME..."

# ---------------------------------------------
# systemd
# ---------------------------------------------
echo "[uninstall] Stopping systemd service..."
sudo systemctl stop canbusd || true
sudo systemctl disable canbusd || true

echo "[uninstall] Removing systemd file..."
sudo rm -f /etc/systemd/system/canbusd.service
sudo systemctl daemon-reload

# ---------------------------------------------
# udev
# ---------------------------------------------
echo "[uninstall] Removing udev rules..."
sudo rm -f /etc/udev/rules.d/80-canbus.rules
sudo udevadm control --reload-rules
sudo udevadm trigger

# ---------------------------------------------
# install directory
# ---------------------------------------------
echo "[uninstall] Removing install directory..."
sudo rm -rf "$INSTALL_DIR"

echo "[uninstall] Done."
