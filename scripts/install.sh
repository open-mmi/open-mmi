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
sudo apt install -y python3 python3-pip python3-venv can-utils

pip3 install python-can evdev

# ---------------------------------------------
# Install files
# ---------------------------------------------
echo "[install] Creating install directory..."
sudo mkdir -p "$INSTALL_DIR"

echo "[install] Copying files..."
sudo cp -r canbusd "$INSTALL_DIR/"
sudo cp -r vehicles "$INSTALL_DIR/"
sudo cp -r bindings "$INSTALL_DIR/"
sudo cp -r actions "$INSTALL_DIR/"
sudo cp pyproject.toml "$INSTALL_DIR/"

# ---------------------------------------------
# systemd
# ---------------------------------------------
echo "[install] Installing systemd service..."
sudo cp systemd/canbusd.service /etc/systemd/system/canbusd.service

sudo systemctl daemon-reload
sudo systemctl enable canbusd
sudo systemctl restart canbusd

# ---------------------------------------------
# udev
# ---------------------------------------------
if [ -f udev/80-canbus.rules ]; then
    echo "[install] Installing udev rules..."
    sudo cp udev/80-canbus.rules /etc/udev/rules.d/
    sudo udevadm control --reload-rules
    sudo udevadm trigger
fi

echo "[install] Done."
