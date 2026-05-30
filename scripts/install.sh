#!/usr/bin/env bash
set -euo pipefail

APP_NAME="open-mmi"
INSTALL_DIR="/opt/open-mmi"

REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)
USER_ID=$(id -u "$REAL_USER")

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[install] Installing $APP_NAME..."

# ---------------------------------------------
# Dependencies
# ---------------------------------------------
echo "[install] Installing system dependencies..."

sudo apt update

sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    can-utils \
    udev \
    dbus-x11

# ---------------------------------------------
# Install directory
# ---------------------------------------------
echo "[install] Creating install directory..."

sudo mkdir -p "$INSTALL_DIR"
sudo chown -R "$REAL_USER:$REAL_USER" "$INSTALL_DIR"

# ---------------------------------------------
# Python virtual environment
# ---------------------------------------------
echo "[install] Creating virtual environment..."

python3 -m venv "$INSTALL_DIR/venv"

echo "[install] Installing Python dependencies..."

"$INSTALL_DIR/venv/bin/pip" install --upgrade pip

"$INSTALL_DIR/venv/bin/pip" install \
    python-can \
    evdev \
    pulsectl

# ---------------------------------------------
# Install files
# ---------------------------------------------
echo "[install] Copying application files..."

cp -r "$REPO_ROOT/canbusd" "$INSTALL_DIR/"
cp -r "$REPO_ROOT/vehicles" "$INSTALL_DIR/"
cp -r "$REPO_ROOT/bindings" "$INSTALL_DIR/"
cp -r "$REPO_ROOT/actions" "$INSTALL_DIR/"
cp "$REPO_ROOT/pyproject.toml" "$INSTALL_DIR/"

# ---------------------------------------------
# User systemd service
# ---------------------------------------------
echo "[install] Installing user systemd service..."

mkdir -p "$REAL_HOME/.config/systemd/user"

cp \
  "$REPO_ROOT/systemd/user/canbusd.service" \
  "$REAL_HOME/.config/systemd/user/canbusd.service"

chown "$REAL_USER:$REAL_USER" \
  "$REAL_HOME/.config/systemd/user/canbusd.service"

export XDG_RUNTIME_DIR="/run/user/$USER_ID"

sudo -u "$REAL_USER" \
    XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
    systemctl --user daemon-reload

sudo -u "$REAL_USER" \
    XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
    systemctl --user enable canbusd

sudo -u "$REAL_USER" \
    XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
    systemctl --user restart canbusd

# ---------------------------------------------
# udev rules
# ---------------------------------------------
if [ -f "$REPO_ROOT/udev/80-canbus.rules" ]; then
    echo "[install] Installing udev rules..."

    sudo cp \
      "$REPO_ROOT/udev/80-canbus.rules" \
      /etc/udev/rules.d/

    sudo udevadm control --reload-rules
    sudo udevadm trigger
fi

# ---------------------------------------------
# Permissions fixes (IMPORTANT)
# ---------------------------------------------
echo "[install] Applying device permissions..."

# uinput + backlight access group
sudo usermod -aG video "$REAL_USER"

# ensure immediate backlight fix (udev sometimes lags)
if [ -e /sys/class/backlight/intel_backlight/brightness ]; then
    sudo chgrp video /sys/class/backlight/intel_backlight/brightness || true
    sudo chmod 664 /sys/class/backlight/intel_backlight/brightness || true
fi

echo "[install] Done."
