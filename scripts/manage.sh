#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Open-MMI Installation Manager
# =============================================================================
# Unified script for install, update, uninstall, and management operations
# =============================================================================

APP_NAME="open-mmi"
INSTALL_DIR="/opt/open-mmi"
BACKUP_DIR="/opt/open-mmi-backups"
VERSION_FILE="$INSTALL_DIR/.version"

# Color output
RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
BLUE=$'\033[0;34m'
NC=$'\033[0m' # No Color

# Get real user (accounting for sudo)
REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)
USER_ID=$(id -u "$REAL_USER")
USER_CONFIG_DIR="$REAL_HOME/.config/open-mmi"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESKTOP_ENTRY_SOURCE="$REPO_ROOT/packaging/linux-desktop/open-mmi-status.desktop"
DESKTOP_ICON_SOURCE="$REPO_ROOT/packaging/linux-desktop/icons"
APPLICATIONS_DIR="$REAL_HOME/.local/share/applications"
APPLICATION_ENTRY="$APPLICATIONS_DIR/open-mmi.desktop"
ICON_THEME_DIR="$REAL_HOME/.local/share/icons"
DESKTOP_ENTRY_NAME="Open MMI.desktop"
COMMAND_LINK_DIR="${OPEN_MMI_COMMAND_LINK_DIR:-/usr/local/bin}"
OPEN_MMI_COMMANDS=(
    open-mmi-canbusd
    open-mmi-config
    open-mmi-dashboard
    open-mmi-launcher
    open-mmi-status
)

# =============================================================================
# UTILITIES
# =============================================================================

log_info() {
    echo -e "${BLUE}[info]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $*"
}

log_error() {
    echo -e "${RED}[✗]${NC} $*" >&2
}

log_warn() {
    echo -e "${YELLOW}[!]${NC} $*"
}

confirm() {
    local prompt="$1"
    local response
    read -p "$(echo -e ${YELLOW}$prompt${NC}) (y/N) " -r response
    [[ "$response" =~ ^[Yy]$ ]]
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run with sudo"
        exit 1
    fi
}

check_dependencies() {
    local missing=()
    
    for cmd in git python3 pip; do
        if ! command -v "$cmd" &> /dev/null; then
            missing+=("$cmd")
        fi
    done
    
    if [ ${#missing[@]} -gt 0 ]; then
        log_error "Missing required commands: ${missing[*]}"
        log_info "Install with: sudo apt install ${missing[*]}"
        return 1
    fi
    return 0
}

is_installed() {
    [ -d "$INSTALL_DIR" ] && [ -f "$VERSION_FILE" ]
}

get_installed_version() {
    if [ -f "$VERSION_FILE" ]; then
        cat "$VERSION_FILE"
    else
        echo "unknown"
    fi
}

get_current_version() {
    sudo -u "$REAL_USER" git -C "$REPO_ROOT" describe --tags --always 2>/dev/null \
        || echo "dev-$(sudo -u "$REAL_USER" git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo 'local')"
}

daemon_running() {
    export XDG_RUNTIME_DIR="/run/user/$USER_ID"
    sudo -u "$REAL_USER" \
        XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
        systemctl --user is-active canbusd > /dev/null 2>&1
}

get_repo_branch() {
    sudo -u "$REAL_USER" git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main"
}

get_repo_upstream() {
    local upstream
    upstream=$(sudo -u "$REAL_USER" git -C "$REPO_ROOT" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)

    if [ -n "$upstream" ]; then
        echo "$upstream"
    else
        echo "origin/$(get_repo_branch)"
    fi
}


copy_if_missing() {
    local src="$1"
    local dst="$2"

    if [ -e "$dst" ]; then
        log_warn "Keeping existing user file: $dst"
        return 0
    fi

    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"
    chown "$REAL_USER:$REAL_USER" "$dst"
    log_success "Created $dst"
}

open_editor_as_user() {
    local file="$1"
    local editor="${EDITOR:-nano}"

    sudo -u "$REAL_USER" \
        HOME="$REAL_HOME" \
        XDG_RUNTIME_DIR="/run/user/$USER_ID" \
        "$editor" "$file"
}


get_desktop_dir() {
    local desktop_dir=""

    if command -v xdg-user-dir > /dev/null 2>&1; then
        desktop_dir=$(sudo -u "$REAL_USER" env HOME="$REAL_HOME" xdg-user-dir DESKTOP 2>/dev/null || true)
    fi

    if [[ -z "$desktop_dir" || "$desktop_dir" != /* || "$desktop_dir" = "$REAL_HOME" ]]; then
        desktop_dir="$REAL_HOME/Desktop"
    fi

    printf '%s\n' "$desktop_dir"
}

refresh_desktop_caches() {
    if command -v update-desktop-database > /dev/null 2>&1; then
        sudo -u "$REAL_USER" env HOME="$REAL_HOME" update-desktop-database "$APPLICATIONS_DIR" > /dev/null 2>&1 || true
    fi

    if command -v gtk-update-icon-cache > /dev/null 2>&1 && [ -d "$ICON_THEME_DIR/hicolor" ]; then
        sudo -u "$REAL_USER" env HOME="$REAL_HOME" gtk-update-icon-cache -f -t "$ICON_THEME_DIR/hicolor" > /dev/null 2>&1 || true
    fi
}

install_desktop_icons() {
    if [ ! -d "$DESKTOP_ICON_SOURCE" ]; then
        log_error "Desktop icon source not found: $DESKTOP_ICON_SOURCE"
        return 1
    fi

    while IFS= read -r -d '' source_icon; do
        local relative_path target_icon target_dir
        relative_path="${source_icon#"$DESKTOP_ICON_SOURCE"/}"
        target_icon="$ICON_THEME_DIR/$relative_path"
        target_dir=$(dirname "$target_icon")
        install -d -m 0755 -o "$REAL_USER" -g "$REAL_USER" "$target_dir"
        install -m 0644 -o "$REAL_USER" -g "$REAL_USER" "$source_icon" "$target_icon"
    done < <(find "$DESKTOP_ICON_SOURCE" -type f -print0)
}

remove_desktop_icons() {
    if [ ! -d "$DESKTOP_ICON_SOURCE" ]; then
        return 0
    fi

    while IFS= read -r -d '' source_icon; do
        local relative_path
        relative_path="${source_icon#"$DESKTOP_ICON_SOURCE"/}"
        rm -f "$ICON_THEME_DIR/$relative_path"
    done < <(find "$DESKTOP_ICON_SOURCE" -type f -print0)
}

install_desktop_entry() {
    local desktop_dir
    desktop_dir=$(get_desktop_dir)

    if [ ! -f "$DESKTOP_ENTRY_SOURCE" ]; then
        log_error "Desktop entry source not found: $DESKTOP_ENTRY_SOURCE"
        return 1
    fi

    log_info "Installing desktop launcher and icons..."
    install_desktop_icons
    install -d -m 0755 -o "$REAL_USER" -g "$REAL_USER" "$APPLICATIONS_DIR" "$desktop_dir"
    install -m 0644 -o "$REAL_USER" -g "$REAL_USER" "$DESKTOP_ENTRY_SOURCE" "$APPLICATION_ENTRY"
    install -m 0755 -o "$REAL_USER" -g "$REAL_USER" "$DESKTOP_ENTRY_SOURCE" "$desktop_dir/$DESKTOP_ENTRY_NAME"

    if command -v gio > /dev/null 2>&1; then
        sudo -u "$REAL_USER" env HOME="$REAL_HOME" gio set "$desktop_dir/$DESKTOP_ENTRY_NAME" metadata::trusted true > /dev/null 2>&1 || true
    fi

    refresh_desktop_caches
}

remove_desktop_entry() {
    local desktop_dir
    desktop_dir=$(get_desktop_dir)

    log_info "Removing desktop launcher and icons..."
    rm -f "$APPLICATION_ENTRY" "$desktop_dir/$DESKTOP_ENTRY_NAME"
    remove_desktop_icons
    refresh_desktop_caches
}

verify_console_commands() {
    local command wrapper

    for command in "${OPEN_MMI_COMMANDS[@]}"; do
        wrapper="$INSTALL_DIR/venv/bin/$command"
        if [ ! -x "$wrapper" ]; then
            log_error "Installed command wrapper is missing or not executable: $wrapper"
            return 1
        fi
    done
}

install_open_mmi_package() {
    local python="$INSTALL_DIR/venv/bin/python"

    if [ ! -x "$python" ]; then
        log_error "Deployment Python is missing or not executable: $python"
        return 1
    fi

    log_info "Installing Open MMI package and console commands..."
    if ! "$python" -m pip install --upgrade --force-reinstall "$INSTALL_DIR"; then
        log_error "Failed to install Open MMI package"
        return 1
    fi

    verify_console_commands
}

install_command_links() {
    local command wrapper link current_target

    install -d -m 0755 "$COMMAND_LINK_DIR"

    for command in "${OPEN_MMI_COMMANDS[@]}"; do
        wrapper="$INSTALL_DIR/venv/bin/$command"
        link="$COMMAND_LINK_DIR/$command"

        if [ -e "$link" ] || [ -L "$link" ]; then
            if [ -L "$link" ]; then
                current_target=$(readlink "$link")
                if [ "$current_target" = "$wrapper" ]; then
                    continue
                fi
            fi

            log_error "Refusing to replace unrelated command: $link"
            return 1
        fi
    done

    for command in "${OPEN_MMI_COMMANDS[@]}"; do
        wrapper="$INSTALL_DIR/venv/bin/$command"
        link="$COMMAND_LINK_DIR/$command"
        if [ ! -L "$link" ]; then
            ln -s "$wrapper" "$link"
        fi
    done
}

remove_command_links() {
    local command wrapper link

    for command in "${OPEN_MMI_COMMANDS[@]}"; do
        wrapper="$INSTALL_DIR/venv/bin/$command"
        link="$COMMAND_LINK_DIR/$command"
        if [ -L "$link" ] && [ "$(readlink "$link")" = "$wrapper" ]; then
            rm -f "$link"
        fi
    done
}

dashboard_start_at_login() {
    local config_file="$USER_CONFIG_DIR/launcher.json"

    if [ ! -f "$config_file" ]; then
        return 0
    fi

    python3 - "$config_file" <<'PY_CONFIG'
import json
import sys
from pathlib import Path

try:
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    raise SystemExit(0)

raise SystemExit(0 if payload.get("start_at_login", True) is not False else 1)
PY_CONFIG
}

configure_dashboard_autostart() {
    export XDG_RUNTIME_DIR="/run/user/$USER_ID"
    sudo -u "$REAL_USER" env HOME="$REAL_HOME" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" systemctl --user enable canbusd.service

    if dashboard_start_at_login; then
        sudo -u "$REAL_USER" env HOME="$REAL_HOME" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" systemctl --user enable open-mmi-dashboard.service
    else
        sudo -u "$REAL_USER" env HOME="$REAL_HOME" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" systemctl --user disable open-mmi-dashboard.service
    fi
}


# =============================================================================
# PROFILE-DRIVEN PROVISIONING
# =============================================================================
apply_profile_provisioning() {
    local vehicle="${1:-seat_1p}"
    local bindings="${2:-default}"

    log_info "Applying profile-driven provisioning: vehicle=$vehicle bindings=$bindings"

    python3 "$REPO_ROOT/scripts/profile_provision.py" \
        --repo-root "$REPO_ROOT" \
        --install-dir "$INSTALL_DIR" \
        --user-config-dir "$USER_CONFIG_DIR" \
        --systemd-user-dir "$REAL_HOME/.config/systemd/user" \
        --vehicle "$vehicle" \
        --bindings "$bindings" \
        --real-user "$REAL_USER"

    chown -R "$REAL_USER:$REAL_USER" "$USER_CONFIG_DIR" "$REAL_HOME/.config/systemd/user" || true
}

reload_profile_provisioning() {
    export XDG_RUNTIME_DIR="/run/user/$USER_ID"

    log_info "Reloading systemd user service files..."
    sudo -u "$REAL_USER" \
        HOME="$REAL_HOME" \
        XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
        systemctl --user daemon-reload

    log_info "Reloading udev rules..."
    sudo udevadm control --reload-rules
    sudo udevadm trigger

    if daemon_running; then
        log_info "Restarting daemon..."
        sudo -u "$REAL_USER" \
            HOME="$REAL_HOME" \
            XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
            systemctl --user restart canbusd.service
    fi
}

# =============================================================================
# INSTALL
# =============================================================================

cmd_install() {
    log_info "Installing $APP_NAME..."
    
    # Pre-flight checks
    if is_installed; then
        log_error "$APP_NAME already installed at $INSTALL_DIR"
        log_info "Use './manage.sh update' to update"
        return 1
    fi
    
    if ! check_dependencies; then
        log_info "Install missing dependencies first: sudo apt install git python3 python3-pip"
        return 1
    fi
    
    # Install system dependencies
    log_info "Installing system dependencies..."
    if ! sudo apt update; then
        log_error "Failed to update package list"
        return 1
    fi
    
    if ! sudo apt install -y \
        python3 \
        python3-pip \
        python3-venv \
        can-utils \
        udev \
        dbus-x11 \
        zenity; then
        log_error "Failed to install system dependencies"
        return 1
    fi
    
    # Create install directory
    log_info "Creating install directory..."
    sudo mkdir -p "$INSTALL_DIR"
    sudo chown -R "$REAL_USER:$REAL_USER" "$INSTALL_DIR"
    
    # Create Python virtual environment
    log_info "Creating Python virtual environment..."
    if ! python3 -m venv "$INSTALL_DIR/venv"; then
        log_error "Failed to create virtual environment"
        return 1
    fi
    
    log_info "Preparing Python packaging tools..."
    if ! "$INSTALL_DIR/venv/bin/python" -m pip install --upgrade pip; then
        log_error "Failed to upgrade pip"
        return 1
    fi
    
    # Copy application files
    log_info "Copying application files..."
    cp -r "$REPO_ROOT/canbusd" "$INSTALL_DIR/"
    cp -r "$REPO_ROOT/vehicles" "$INSTALL_DIR/"
    cp -r "$REPO_ROOT/bindings" "$INSTALL_DIR/"
    cp -r "$REPO_ROOT/actions" "$INSTALL_DIR/"

    if [ -d "$REPO_ROOT/ui" ]; then
        cp -r "$REPO_ROOT/ui" "$INSTALL_DIR/"
    fi

    cp -r "$REPO_ROOT/scripts" "$INSTALL_DIR/"
    cp -r "$REPO_ROOT/packaging" "$INSTALL_DIR/"
    cp "$REPO_ROOT/pyproject.toml" "$INSTALL_DIR/"
    cp "$REPO_ROOT/README.md" "$INSTALL_DIR/"
    cp "$REPO_ROOT/LICENSE" "$INSTALL_DIR/"

    if ! install_open_mmi_package; then
        return 1
    fi
    if ! install_command_links; then
        return 1
    fi
    
    # Store version
    get_current_version > "$VERSION_FILE"
    
    # Install systemd service
    log_info "Installing systemd user service..."
    local user_systemd_dir="$REAL_HOME/.config/systemd/user"
    install -d -m 0755 -o "$REAL_USER" -g "$REAL_USER" "$user_systemd_dir"
    install -m 0644 -o "$REAL_USER" -g "$REAL_USER" "$REPO_ROOT/systemd/user/canbusd.service" "$user_systemd_dir/canbusd.service"
    install -m 0644 -o "$REAL_USER" -g "$REAL_USER" "$REPO_ROOT/systemd/user/open-mmi-dashboard.service" "$user_systemd_dir/open-mmi-dashboard.service"
    install_desktop_entry
    export XDG_RUNTIME_DIR="/run/user/$USER_ID"
    mkdir -p "$REAL_HOME/.config/systemd/user/default.target.wants"
    chown -R "$REAL_USER:$REAL_USER" "$REAL_HOME/.config/systemd/user"

    sudo -u "$REAL_USER" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" systemctl --user daemon-reload
    configure_dashboard_autostart
    # Apply default profile-driven CAN provisioning.
    # This creates user config if missing, writes the daemon runtime drop-in,
    # and generates udev rules from the selected vehicle profile metadata.
    apply_profile_provisioning "seat_1p" "default"
    reload_profile_provisioning
    
    # Set permissions
    log_info "Configuring user permissions..."
    sudo usermod -aG video,input "$REAL_USER"
    
    # Try to fix backlight immediately
    if [ -e /sys/class/backlight/intel_backlight/brightness ]; then
        sudo chgrp video /sys/class/backlight/intel_backlight/brightness || true
        sudo chmod 664 /sys/class/backlight/intel_backlight/brightness || true
    fi
    
    # Start services
    log_info "Starting Open MMI services..."
    sudo -u "$REAL_USER" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" systemctl --user restart canbusd open-mmi-dashboard
    
    # Verify
    sleep 1
    if daemon_running; then
        log_success "Installation complete!"
        cmd_status
    else
        log_warn "Installation complete but daemon failed to start"
        log_info "Check logs: journalctl --user -u canbusd -f"
        return 1
    fi
}

# =============================================================================
# UPDATE
# =============================================================================

cmd_update() {
    log_info "Updating $APP_NAME..."

    if ! is_installed; then
        log_error "$APP_NAME not installed"
        return 1
    fi

    local old_version
    old_version=$(get_installed_version)

    # =========================================================
    # PHASE 1: SAFE GIT UPDATE (RUN AS REAL USER, NOT ROOT)
    # =========================================================
    log_info "Syncing repository (user-level)..."

    local branch
    local upstream
    branch=$(get_repo_branch)
    upstream=$(get_repo_upstream)

    log_info "Repo branch: $branch"
    log_info "Repo upstream: $upstream"

    sudo -u "$REAL_USER" git -C "$REPO_ROOT" fetch origin

    # Detect local changes as the real user so SSH keys and Git config work.
    if ! sudo -u "$REAL_USER" git -C "$REPO_ROOT" diff --quiet ||        ! sudo -u "$REAL_USER" git -C "$REPO_ROOT" diff --cached --quiet; then
        log_warn "Local changes detected:"
        sudo -u "$REAL_USER" git -C "$REPO_ROOT" status -s

        if ! confirm "Continue and overwrite local changes?"; then
            log_info "Update cancelled"
            return 1
        fi

        sudo -u "$REAL_USER" git -C "$REPO_ROOT" reset --hard "$upstream"
    else
        sudo -u "$REAL_USER" git -C "$REPO_ROOT" merge --ff-only "$upstream" || log_warn "No fast-forward update applied"
    fi

    # =========================================================
    # FIX OWNERSHIP SAFETY NET (ONLY IF NEEDED)
    # =========================================================
    if [ "$(stat -c '%U' "$REPO_ROOT")" = "root" ]; then
        log_warn "Repo owned by root — fixing permissions..."
        sudo chown -R "$REAL_USER:$REAL_USER" "$REPO_ROOT"
    fi

    local new_version
    new_version=$(get_current_version)

    log_info "Repo version: $new_version"
    log_info "Installed version: $old_version"

    # If nothing changed, exit early
    if [ "$old_version" = "$new_version" ]; then
        log_success "Already up to date"
        return 0
    fi

    # =========================================================
    # PHASE 2: SYSTEM DEPLOY (SUDO REQUIRED)
    # =========================================================
    log_info "Deploying to system..."

    sudo rm -rf         "$INSTALL_DIR/canbusd"         "$INSTALL_DIR/vehicles"         "$INSTALL_DIR/bindings"         "$INSTALL_DIR/actions"         "$INSTALL_DIR/ui"         "$INSTALL_DIR/scripts"         "$INSTALL_DIR/packaging"

    sudo cp -r "$REPO_ROOT/canbusd" "$INSTALL_DIR/"
    sudo cp -r "$REPO_ROOT/vehicles" "$INSTALL_DIR/"
    sudo cp -r "$REPO_ROOT/bindings" "$INSTALL_DIR/"
    sudo cp -r "$REPO_ROOT/actions" "$INSTALL_DIR/"

    if [ -d "$REPO_ROOT/ui" ]; then
        sudo cp -r "$REPO_ROOT/ui" "$INSTALL_DIR/"
    fi

    sudo cp -r "$REPO_ROOT/scripts" "$INSTALL_DIR/"
    sudo cp -r "$REPO_ROOT/packaging" "$INSTALL_DIR/"
    sudo cp "$REPO_ROOT/pyproject.toml" "$INSTALL_DIR/"
    sudo cp "$REPO_ROOT/README.md" "$INSTALL_DIR/"
    sudo cp "$REPO_ROOT/LICENSE" "$INSTALL_DIR/"

    if ! install_open_mmi_package; then
        return 1
    fi
    if ! install_command_links; then
        return 1
    fi

    local user_systemd_dir="$REAL_HOME/.config/systemd/user"
    sudo install -d -m 0755 -o "$REAL_USER" -g "$REAL_USER" "$user_systemd_dir"
    sudo install -m 0644 -o "$REAL_USER" -g "$REAL_USER" "$REPO_ROOT/systemd/user/canbusd.service" "$user_systemd_dir/canbusd.service"
    sudo install -m 0644 -o "$REAL_USER" -g "$REAL_USER" "$REPO_ROOT/systemd/user/open-mmi-dashboard.service" "$user_systemd_dir/open-mmi-dashboard.service"
    install_desktop_entry

    export XDG_RUNTIME_DIR="/run/user/$USER_ID"

    sudo -u "$REAL_USER" env HOME="$REAL_HOME" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" systemctl --user daemon-reload
    configure_dashboard_autostart

    # Version write (needs sudo because /opt is root-owned)
    sudo bash -c "echo '$new_version' > '$VERSION_FILE'"

    # Restart services
    sudo -u "$REAL_USER" env HOME="$REAL_HOME" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" systemctl --user restart canbusd.service open-mmi-dashboard.service

    log_success "Update complete → $new_version"

    log_info "Fixing repository ownership..."
    sudo chown -R "$REAL_USER:$REAL_USER" "$REPO_ROOT"
}
 
# =============================================================================
# UNINSTALL
# =============================================================================

cmd_uninstall() {
    log_warn "This will uninstall $APP_NAME"
    
    if ! is_installed; then
        log_error "$APP_NAME not installed"
        return 1
    fi
    
    if ! confirm "Are you sure you want to uninstall?"; then
        log_info "Uninstall cancelled"
        return 0
    fi
    
    # Create backup before uninstall
    if confirm "Create backup before uninstalling?"; then
        log_info "Creating backup..."
        sudo mkdir -p "$BACKUP_DIR"
        local backup_name="backup-uninstall-$(date +%Y%m%d-%H%M%S)"
        local backup_path="$BACKUP_DIR/$backup_name"
        
        if sudo cp -r "$INSTALL_DIR" "$backup_path"; then
            log_success "Backup created: $backup_path"
        else
            log_warn "Failed to create backup (continuing anyway)"
        fi
    fi
    
    # Stop services
    log_info "Stopping systemd services..."
    export XDG_RUNTIME_DIR="/run/user/$USER_ID"
    for service in canbusd.service open-mmi-dashboard.service; do
        sudo -u "$REAL_USER" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" systemctl --user disable --now "$service" >/dev/null 2>&1 || true
    done

    # Remove service file
    log_info "Removing systemd service..."
    rm -f \
        "$REAL_HOME/.config/systemd/user/canbusd.service" \
        "$REAL_HOME/.config/systemd/user/open-mmi-dashboard.service"
    sudo -u "$REAL_USER" \
        XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
        systemctl --user daemon-reload

    remove_desktop_entry
    remove_command_links
    
    # Remove application directory
    log_info "Removing application files..."
    sudo rm -rf "$INSTALL_DIR"
    
    # Remove udev rules
    if [ -f /etc/udev/rules.d/80-canbus.rules ]; then
        log_info "Removing udev rules..."
        sudo rm -f /etc/udev/rules.d/80-canbus.rules
        sudo udevadm control --reload-rules
        sudo udevadm trigger
    fi
    
    log_success "Uninstall complete"
    log_info "Note: User was not removed from 'video' and 'input' groups"
    log_info "Optional group cleanup:"
    log_info "  sudo gpasswd -d $REAL_USER video"
    log_info "  sudo gpasswd -d $REAL_USER input"
}

# =============================================================================
# STATUS
# =============================================================================

cmd_status() {
    log_info "Installation Status"
    echo ""
    
    if is_installed; then
        echo -e "  Status:         ${GREEN}✓ Installed${NC}"
        echo -e "  Install Dir:    $INSTALL_DIR"
        echo -e "  Version:        $(get_installed_version)"
        echo -e "  Service:        $(daemon_running && echo -e "${GREEN}✓ Running${NC}" || echo -e "${RED}✗ Stopped${NC}")"
        echo ""
        
        if daemon_running; then
            log_success "All systems operational"
        else
            log_warn "Daemon is not running"
            log_info "Start with: systemctl --user start canbusd"
        fi
    else
        echo -e "  Status:         ${RED}✗ Not Installed${NC}"
        log_info "Install with: sudo ./scripts/manage.sh install"
    fi
    
    echo ""
    echo "  User:           $REAL_USER"
    echo "  Groups:         $(groups $REAL_USER | cut -d: -f2)"
    echo "  Service Dir:    $REAL_HOME/.config/systemd/user"
    
    if [ -d "$BACKUP_DIR" ]; then
        echo ""
        echo "  Backups:"
        ls -1 "$BACKUP_DIR" 2>/dev/null | while read backup; do
            echo "    - $backup"
        done
    fi
}

# =============================================================================
# LOGS
# =============================================================================

cmd_logs() {
    log_info "Viewing daemon logs (Ctrl+C to exit)"
    sudo -u "$REAL_USER" \
        XDG_RUNTIME_DIR="/run/user/$USER_ID" \
        journalctl --user-unit=canbusd -f
}

# =============================================================================
# CONFIG
# =============================================================================

cmd_config() {
    local action="${1:-help}"

    case "$action" in
        apply-profile|set-profile)
            local vehicle="${2:-seat_1p}"
            local bindings="${3:-default}"

            apply_profile_provisioning "$vehicle" "$bindings"
            reload_profile_provisioning

            log_success "Profile applied: $vehicle"
            echo ""
            log_info "Normal setup now comes from the selected vehicle profile."
            log_info "Use 'sudo $0 config edit-can' only for advanced hardware overrides."
            ;;
        init)
            local vehicle="${2:-seat_1p}"
            local bindings="${3:-default}"

            log_info "Creating user config directory at $USER_CONFIG_DIR"
            mkdir -p "$USER_CONFIG_DIR/vehicles/$vehicle"
            mkdir -p "$USER_CONFIG_DIR/bindings"
            chown -R "$REAL_USER:$REAL_USER" "$USER_CONFIG_DIR"

            local source_vehicle="$REPO_ROOT/vehicles/$vehicle/config.json"
            local source_bindings="$REPO_ROOT/bindings/$bindings.json"

            if [ ! -f "$source_vehicle" ]; then
                log_error "Vehicle profile not found: $source_vehicle"
                return 1
            fi

            if [ ! -f "$source_bindings" ]; then
                log_error "Bindings file not found: $source_bindings"
                return 1
            fi

            copy_if_missing \
                "$source_vehicle" \
                "$USER_CONFIG_DIR/vehicles/$vehicle/config.json"

            copy_if_missing \
                "$source_bindings" \
                "$USER_CONFIG_DIR/bindings/$bindings.json"

            log_success "User config ready"
            echo ""
            echo "  Vehicle profile: $USER_CONFIG_DIR/vehicles/$vehicle/config.json"
            echo "  Bindings file:   $USER_CONFIG_DIR/bindings/$bindings.json"
            echo ""
            log_info "These files are local user overrides/custom config files."
            log_info "Normal profile setup uses: sudo $0 config apply-profile $vehicle $bindings"
            ;;
        edit-profile)
            local vehicle="${2:-${OPEN_MMI_VEHICLE:-seat_1p}}"
            local profile="$USER_CONFIG_DIR/vehicles/$vehicle/config.json"

            if [ ! -f "$profile" ]; then
                log_warn "User profile does not exist yet: $profile"
                log_info "Creating it from installed/repo profile..."
                cmd_config init "$vehicle" "${OPEN_MMI_BINDINGS:-default}"
            fi

            open_editor_as_user "$profile"
            ;;
        edit-bindings)
            local bindings="${2:-${OPEN_MMI_BINDINGS:-default}}"
            local file="$USER_CONFIG_DIR/bindings/$bindings.json"

            if [ ! -f "$file" ]; then
                log_warn "User bindings do not exist yet: $file"
                log_info "Creating it from installed/repo bindings..."
                cmd_config init "${OPEN_MMI_VEHICLE:-seat_1p}" "$bindings"
            fi

            open_editor_as_user "$file"
            ;;
        edit-service|edit)
            log_info "Editing systemd service override"
            if [ ! -f "$REAL_HOME/.config/systemd/user/canbusd.service" ]; then
                log_error "Service not installed yet"
                return 1
            fi

            mkdir -p "$REAL_HOME/.config/systemd/user/canbusd.service.d"
            chown -R "$REAL_USER:$REAL_USER" "$REAL_HOME/.config/systemd/user"

            export XDG_RUNTIME_DIR="/run/user/$USER_ID"
            sudo -u "$REAL_USER" \
                HOME="$REAL_HOME" \
                XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
                systemctl --user edit canbusd.service

            log_info "Reloading systemd..."
            sudo -u "$REAL_USER" \
                HOME="$REAL_HOME" \
                XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
                systemctl --user daemon-reload

            if daemon_running; then
                log_info "Restarting daemon..."
                sudo -u "$REAL_USER" \
                    HOME="$REAL_HOME" \
                    XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
                    systemctl --user restart canbusd.service
            fi
            ;;
        edit-can)
            log_info "Editing CAN runtime override"
            if [ ! -f "$REAL_HOME/.config/systemd/user/canbusd.service" ]; then
                log_error "Service not installed yet"
                return 1
            fi

            local override_dir="$REAL_HOME/.config/systemd/user/canbusd.service.d"
            local override_file="$override_dir/10-can-runtime.conf"

            mkdir -p "$override_dir"
            chown -R "$REAL_USER:$REAL_USER" "$REAL_HOME/.config/systemd/user"

            if [ ! -f "$override_file" ]; then
                cat > "$override_file" <<'EOF'
# open-mmi CAN runtime selection
#
# This selects which already-provisioned SocketCAN interface the daemon consumes.
# It does not configure bitrate and does not bring the interface up.
#
# Current known-working default:
#   comfort -> can0
#
# The normal profile-driven setup provisions can0 at 100000 for the Seat 1P
# reference profile.
# Keep udev/system setup responsible for hotplug/reboot survival.

[Service]
Environment="OPEN_MMI_CAN_BUS=comfort"
Environment="OPEN_MMI_CAN_INTERFACE=can0"
EOF
                chown "$REAL_USER:$REAL_USER" "$override_file"
            fi

            open_editor_as_user "$override_file"

            log_info "Reloading systemd..."
            export XDG_RUNTIME_DIR="/run/user/$USER_ID"
            sudo -u "$REAL_USER" \
                HOME="$REAL_HOME" \
                XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
                systemctl --user daemon-reload

            if daemon_running; then
                log_info "Restarting daemon..."
                sudo -u "$REAL_USER" \
                    HOME="$REAL_HOME" \
                    XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
                    systemctl --user restart canbusd.service
            fi
            ;;
        show)
            log_info "Current service configuration:"
            systemctl --user cat canbusd.service 2>/dev/null || cat "$REAL_HOME/.config/systemd/user/canbusd.service"
            ;;
        paths)
            log_info "Configuration paths"
            echo ""
            echo "  User config dir: $USER_CONFIG_DIR"
            echo "  User vehicles:   $USER_CONFIG_DIR/vehicles"
            echo "  User bindings:   $USER_CONFIG_DIR/bindings"
            echo "  Installed app:   $INSTALL_DIR"
            echo ""
            echo "  Lookup order:"
            echo "    1. Explicit env path overrides"
            echo "    2. User config directory"
            echo "    3. Installed app defaults"
            ;;
        help|--help|-h|*)
            cat <<EOF
Usage: $0 config <command> [args]

Commands:
  apply-profile [vehicle] [bindings]
      Select a vehicle profile and apply its runtime/provisioning defaults.
      This is the normal setup path.
      Default vehicle: seat_1p
      Default bindings: default

  init [vehicle] [bindings]
      Create safe user-owned config files only.
      This does not apply CAN runtime/provisioning defaults.
      $USER_CONFIG_DIR

  edit-profile [vehicle]
      Edit a user-owned vehicle profile.
      Default vehicle: seat_1p

  edit-bindings [bindings]
      Edit a user-owned bindings file.
      Default bindings: default

  edit-service
      Edit the systemd service override.
      Use this for OPEN_MMI_VEHICLE, OPEN_MMI_BINDINGS, log level, etc.

  edit-can
      Edit the CAN runtime override.
      Defaults to the known-working single bus setup:
      OPEN_MMI_CAN_BUS=comfort
      OPEN_MMI_CAN_INTERFACE=can0

      This selects which already-provisioned SocketCAN interface the daemon consumes.
      It does not configure bitrate or bring the interface up.

  show
      Show the effective systemd service config.

  paths
      Show where Open-MMI looks for config files.

Examples:
  sudo $0 config apply-profile seat_1p default
  sudo $0 config init seat_1p default
  sudo $0 config edit-profile seat_1p
  sudo $0 config edit-bindings default
  sudo $0 config edit-can
  sudo $0 config edit-service
EOF
            ;;
    esac
}

# =============================================================================
# HELP
# =============================================================================

show_help() {
    cat <<EOF
${BLUE}Open-MMI Installation Manager${NC}

${BLUE}Usage:${NC}
  sudo ./scripts/manage.sh <command> [options]

${BLUE}Commands:${NC}
  install      Install open-mmi from scratch
  update       Update to latest version (with automatic backup)
  uninstall    Remove open-mmi (with optional backup)
  
  status       Show installation and daemon status
  logs         View daemon logs in real-time
  config       Manage user config and service overrides
  
  help         Show this help message

${BLUE}Examples:${NC}
  sudo ./scripts/manage.sh install
  sudo ./scripts/manage.sh update
  sudo ./scripts/manage.sh status
  sudo ./scripts/manage.sh logs
  sudo ./scripts/manage.sh config apply-profile seat_1p default
  sudo ./scripts/manage.sh config init
  sudo ./scripts/manage.sh config edit-profile seat_1p
  sudo ./scripts/manage.sh config edit-service

${BLUE}Installation Details:${NC}
  Install directory: $INSTALL_DIR
  Service location:  ~/.config/systemd/user/canbusd.service
  Backups:          $BACKUP_DIR

${BLUE}Troubleshooting:${NC}
  View logs:        sudo ./scripts/manage.sh logs
  Check status:     sudo ./scripts/manage.sh status
  Apply profile:    sudo ./scripts/manage.sh config apply-profile seat_1p default
  Edit profile:     sudo ./scripts/manage.sh config edit-profile seat_1p
  sudo ./scripts/manage.sh config init
  sudo ./scripts/manage.sh config edit-profile seat_1p
  sudo ./scripts/manage.sh config edit-service

EOF
}

# =============================================================================
# MAIN
# =============================================================================

main() {
    local command="${1:-help}"
    
    case "$command" in
        install)
            check_root
            cmd_install
            ;;
        update)
            check_root
            cmd_update
            ;;
        uninstall)
            check_root
            cmd_uninstall
            ;;
        status)
            cmd_status
            ;;
        logs)
            cmd_logs
            ;;
        config)
            check_root
            cmd_config "${@:2}"
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            log_error "Unknown command: $command"
            show_help
            exit 1
            ;;
    esac
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
