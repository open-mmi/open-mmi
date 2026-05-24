#!/usr/bin/env bash
set -e

APP_NAME="open-mmi"
INSTALL_DIR="/opt/open-mmi"

echo "[install] Installing $APP_NAME..."

# ---------------------------------------------
# Dependencies
# ---------------------------------------------
echo "[install] Installing system dependencies..."

sudo apt update
sudo apt install -y \
    python3 \
    python3-can \
    python3-evdev \
    can-utils \
    systemd

# ---------------------------------------------
# Stop service if running
# ---------------------------------------------
echo "[install] Stopping existing service (if any)..."
sudo systemctl stop canbusd 2>/dev/null || true

# ---------------------------------------------
# Install files
# ---------------------------------------------
echo "[install] Installing files to $INSTALL_DIR..."

sudo mkdir -p "$INSTALL_DIR"

sudo cp -r canbusd "$INSTALL_DIR/"
sudo cp -r vehicles "$INSTALL_DIR/"
sudo cp -r bindings "$INSTALL_DIR/"
sudo cp -r actions "$INSTALL_DIR/"
sudo cp pyproject.toml "$INSTALL_DIR/" || true

# ---------------------------------------------
# systemd
# ---------------------------------------------
echo "[install] Installing systemd service..."

sudo cp systemd/canbusd.service /etc/systemd/system/canbusd.service
sudo systemctl daemon-reload
sudo systemctl enable canbusd

# ---------------------------------------------
# udev
# ---------------------------------------------
if [ -f udev/80-canbus.rules ]; then
    echo "[install] Installing udev rules..."
    sudo cp udev/80-canbus.rules /etc/udev/rules.d/
    sudo udevadm control --reload-rules
    sudo udevadm trigger
fi

# ---------------------------------------------
# Start service
# ---------------------------------------------
echo "[install] Starting service..."
sudo systemctl start canbusd

echo "[install] Done."
