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
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get real user (accounting for sudo)
REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)
USER_ID=$(id -u "$REAL_USER")

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

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
    cd "$REPO_ROOT"
    git describe --tags --always 2>/dev/null || echo "dev-$(git rev-parse --short HEAD 2>/dev/null || echo 'local')"
}

daemon_running() {
    export XDG_RUNTIME_DIR="/run/user/$USER_ID"
    sudo -u "$REAL_USER" \
        XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
        systemctl --user is-active canbusd > /dev/null 2>&1
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
        dbus-x11; then
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
    
    log_info "Installing Python dependencies..."
    if ! "$INSTALL_DIR/venv/bin/pip" install --upgrade pip; then
        log_error "Failed to upgrade pip"
        return 1
    fi
    
    if ! "$INSTALL_DIR/venv/bin/pip" install \
        python-can \
        evdev; then
        log_error "Failed to install Python dependencies"
        return 1
    fi
    
    # Copy application files
    log_info "Copying application files..."
    cp -r "$REPO_ROOT/canbusd" "$INSTALL_DIR/"
    cp -r "$REPO_ROOT/vehicles" "$INSTALL_DIR/"
    cp -r "$REPO_ROOT/bindings" "$INSTALL_DIR/"
    cp -r "$REPO_ROOT/actions" "$INSTALL_DIR/"
    cp "$REPO_ROOT/pyproject.toml" "$INSTALL_DIR/"
    
    # Store version
    get_current_version > "$VERSION_FILE"
    
    # Install systemd service
    log_info "Installing systemd user service..."
    mkdir -p "$REAL_HOME/.config/systemd/user"
    cp "$REPO_ROOT/systemd/user/canbusd.service" "$REAL_HOME/.config/systemd/user/canbusd.service"
    chown "$REAL_USER:$REAL_USER" "$REAL_HOME/.config/systemd/user/canbusd.service"
    
    export XDG_RUNTIME_DIR="/run/user/$USER_ID"
    sudo -u "$REAL_USER" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" systemctl --user daemon-reload
    sudo -u "$REAL_USER" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" systemctl --user enable canbusd
    
    # Install udev rules
    if [ -f "$REPO_ROOT/udev/80-canbus.rules" ]; then
        log_info "Installing udev rules..."
        sudo cp "$REPO_ROOT/udev/80-canbus.rules" /etc/udev/rules.d/
        sudo udevadm control --reload-rules
        sudo udevadm trigger
    fi
    
    # Set permissions
    log_info "Configuring user permissions..."
    sudo usermod -aG video,input "$REAL_USER"
    
    # Try to fix backlight immediately
    if [ -e /sys/class/backlight/intel_backlight/brightness ]; then
        sudo chgrp video /sys/class/backlight/intel_backlight/brightness || true
        sudo chmod 664 /sys/class/backlight/intel_backlight/brightness || true
    fi
    
    # Start daemon
    log_info "Starting daemon..."
    sudo -u "$REAL_USER" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" systemctl --user restart canbusd
    
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
        log_info "Run: sudo ./scripts/manage.sh install"
        return 1
    fi
    
    local old_version
    old_version=$(get_installed_version)
    local new_version
    new_version=$(get_current_version)

    log_info "Current version: $old_version"
    log_info "Installed version: $new_version"

    cd "$REPO_ROOT"

    # Check for local changes
if ! git diff --quiet || ! git diff --cached --quiet; then
    log_warn "Local changes detected in the repository:"
    
    # Show a concise summary of changes
    git status -s
    
    if confirm "Overwrite local changes and force update?"; then
        log_info "Overwriting local changes..."
        git fetch origin main
        git reset --hard origin/main
    else
        log_info "Update cancelled due to local changes"
        return 1
    fi
else
    git fetch origin main
    git merge origin/main || log_warn "Merge did not apply changes"
fi

    # Update installed files and Python dependencies
    log_info "Updating application files..."
    cp -r "$REPO_ROOT/canbusd" "$INSTALL_DIR/"
    cp -r "$REPO_ROOT/vehicles" "$INSTALL_DIR/"
    cp -r "$REPO_ROOT/bindings" "$INSTALL_DIR/"
    cp -r "$REPO_ROOT/actions" "$INSTALL_DIR/"
    cp "$REPO_ROOT/pyproject.toml" "$INSTALL_DIR/"

    get_current_version > "$VERSION_FILE"

    log_success "Update complete! New version: $(get_installed_version)"
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
    
    # Stop daemon
    log_info "Stopping systemd service..."
    export XDG_RUNTIME_DIR="/run/user/$USER_ID"
    sudo -u "$REAL_USER" \
        XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
        systemctl --user stop canbusd || true
    
    sudo -u "$REAL_USER" \
        XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
        systemctl --user disable canbusd || true
    
    # Remove service file
    log_info "Removing systemd service..."
    rm -f "$REAL_HOME/.config/systemd/user/canbusd.service"
    sudo -u "$REAL_USER" \
        XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
        systemctl --user daemon-reload
    
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
    log_info "To clean up, run: sudo usermod -G $(groups $REAL_USER | cut -d: -f2 | sed 's/ video//g; s/ input//g') $REAL_USER"
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
        edit)
            log_info "Editing systemd service configuration"
            if [ ! -f "$REAL_HOME/.config/systemd/user/canbusd.service" ]; then
                log_error "Service not installed yet"
                return 1
            fi
            
            export XDG_RUNTIME_DIR="/run/user/$USER_ID"
            sudo -u "$REAL_USER" \
                XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
                systemctl --user edit canbusd
            
            log_info "Reloading systemd..."
            sudo -u "$REAL_USER" \
                XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
                systemctl --user daemon-reload
            
            if daemon_running; then
                log_info "Restarting daemon..."
                sudo -u "$REAL_USER" \
                    XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
                    systemctl --user restart canbusd
            fi
            ;;
        show)
            log_info "Current service configuration:"
            cat "$REAL_HOME/.config/systemd/user/canbusd.service"
            ;;
        *)
            echo "Usage: $0 config {edit|show}"
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
  config       Manage service configuration
  
  help         Show this help message

${BLUE}Examples:${NC}
  sudo ./scripts/manage.sh install
  sudo ./scripts/manage.sh update
  sudo ./scripts/manage.sh status
  sudo ./scripts/manage.sh logs
  sudo ./scripts/manage.sh config edit

${BLUE}Installation Details:${NC}
  Install directory: $INSTALL_DIR
  Service location:  ~/.config/systemd/user/canbusd.service
  Backups:          $BACKUP_DIR

${BLUE}Troubleshooting:${NC}
  View logs:        sudo ./scripts/manage.sh logs
  Check status:     sudo ./scripts/manage.sh status
  Edit config:      sudo ./scripts/manage.sh config edit

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
            cmd_config "${2:-help}"
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

main "$@"
