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
UPDATE_POLICY_FILE="/etc/open-mmi/update-policy.json"
UPDATE_COORDINATOR_GROUP="open-mmi-update"
UPDATE_COORDINATOR_UNIT="open-mmi-update-coordinator.service"
UPDATE_INSTALLER_UNIT="open-mmi-update-installer.service"
UPDATE_COORDINATOR_STATE_DIR="/var/lib/open-mmi"
UPDATE_COORDINATOR_RUNTIME_DIR="/run/open-mmi"

# Color output
RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
BLUE=$'\033[0;34m'
NC=$'\033[0m' # No Color

# Get real user (accounting for sudo)
REAL_USER="${OPEN_MMI_REAL_USER:-${SUDO_USER:-${USER:-root}}}"
REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)
USER_ID=$(id -u "$REAL_USER")
USER_CONFIG_DIR="$REAL_HOME/.config/open-mmi"
LOGIN_AUTOSTART_ENTRY="$REAL_HOME/.config/autostart/open-mmi.desktop"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESKTOP_ENTRY_SOURCE="$REPO_ROOT/packaging/linux-desktop/open-mmi-status.desktop"
CHOOSER_ENTRY_SOURCE="$REPO_ROOT/packaging/linux-desktop/open-mmi-chooser.desktop"
DESKTOP_ICON_SOURCE="$REPO_ROOT/packaging/linux-desktop/icons"
APPLICATIONS_DIR="$REAL_HOME/.local/share/applications"
APPLICATION_ENTRY="$APPLICATIONS_DIR/open-mmi.desktop"
CHOOSER_APPLICATION_ENTRY="$APPLICATIONS_DIR/open-mmi-chooser.desktop"
ICON_THEME_DIR="$REAL_HOME/.local/share/icons"
DESKTOP_ENTRY_NAME="Open MMI.desktop"
COMMAND_LINK_DIR="${OPEN_MMI_COMMAND_LINK_DIR:-/usr/local/bin}"
OPEN_MMI_COMMANDS=(
    open-mmi-canbusd
    open-mmi-config
    open-mmi-dashboard
    open-mmi-launcher
    open-mmi-status
    open-mmi-update-coordinator
    open-mmi-update-installer
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

get_repo_commit() {
    sudo -u "$REAL_USER" git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || true
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

write_update_source_metadata() {
    local branch upstream commit version repository destination
    branch="${1:-${OPEN_MMI_MANAGED_BRANCH:-$(get_repo_branch)}}"
    upstream="${2:-${OPEN_MMI_MANAGED_UPSTREAM:-$(get_repo_upstream)}}"
    commit="${3:-${OPEN_MMI_PREPARED_COMMIT:-$(get_repo_commit)}}"
    version="${4:-${OPEN_MMI_PREPARED_VERSION:-$(get_current_version)}}"
    repository="${5:-${OPEN_MMI_MANAGED_REPOSITORY:-$REPO_ROOT}}"
    destination="$INSTALL_DIR/.update-source.json"

    if [[ ! "$commit" =~ ^[0-9a-fA-F]{40}$ ]]; then
        log_warn "Could not record managed update source metadata"
        return 0
    fi

    python3 - "$destination" "$repository" "$branch" "$upstream" "$commit" "$version" "$UPDATE_POLICY_FILE" <<'PY_UPDATE_SOURCE'
import json
import os
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

metadata_path = Path(sys.argv[1])
policy_path = Path(sys.argv[7])
approved_channels = {"stable", "beta", "nightly"}


def timestamp():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def atomic_json(path, payload, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            json.dump(payload, temporary, indent=2, sort_keys=True)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.chmod(temporary_name, mode)
        os.replace(temporary_name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        if temporary_name:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
        raise


production_policy = policy_path == Path("/etc/open-mmi/update-policy.json")
if policy_path.is_symlink():
    raise RuntimeError("update policy must not be a symlink")
if production_policy and policy_path.parent.is_symlink():
    raise RuntimeError("update policy directory must not be a symlink")
if production_policy and policy_path.parent.exists():
    parent_metadata = policy_path.parent.lstat()
    if not stat.S_ISDIR(parent_metadata.st_mode) or parent_metadata.st_uid != 0:
        raise RuntimeError("production update policy directory must be root owned")
    if parent_metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise RuntimeError("production update policy directory must not be group/world writable")
if policy_path.exists():
    metadata = policy_path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError("update policy must be a regular file")
    if metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise RuntimeError("update policy must not be group/world writable")
    if policy_path == Path("/etc/open-mmi/update-policy.json") and metadata.st_uid != 0:
        raise RuntimeError("production update policy must be root owned")
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    if not isinstance(policy, dict) or set(policy) - {"schema_version", "channel", "updated_at"}:
        raise RuntimeError("update policy contains unsupported fields")
    if policy.get("schema_version") != 1:
        raise RuntimeError("update policy is invalid")
    if policy.get("channel") == "development":
        policy["channel"] = "nightly"
        policy["updated_at"] = timestamp()
        atomic_json(policy_path, policy, 0o644)
    elif policy.get("channel") not in approved_channels:
        raise RuntimeError("update policy is invalid")
else:
    policy = {
        "schema_version": 1,
        "channel": "nightly",
        "updated_at": timestamp(),
    }
    if production_policy:
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(policy_path.parent, 0o755)
    atomic_json(policy_path, policy, 0o644)

payload = {
    "schema_version": 1,
    "channel": policy["channel"],
    "repository_path": str(Path(sys.argv[2]).resolve()),
    "branch": sys.argv[3],
    "upstream": sys.argv[4],
    "installed_commit": sys.argv[5].lower(),
    "installed_version": sys.argv[6],
}
atomic_json(metadata_path, payload, 0o644)
PY_UPDATE_SOURCE
    log_success "Recorded managed update source and channel policy"
}

write_checkout_update_source_metadata() {
    local branch upstream commit version
    branch=$(get_repo_branch)
    upstream=$(get_repo_upstream)
    commit=$(get_repo_commit)
    version=$(get_current_version)

    # Interactive install/update operations must describe the checkout being
    # deployed, even if prepared-installer variables remain in the caller's
    # environment. Prepared deployments call the lower-level writer directly.
    write_update_source_metadata "$branch" "$upstream" "$commit" "$version" "$REPO_ROOT"
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
    if [ ! -f "$CHOOSER_ENTRY_SOURCE" ]; then
        log_error "Interface chooser entry source not found: $CHOOSER_ENTRY_SOURCE"
        return 1
    fi

    log_info "Installing desktop launcher and icons..."
    install_desktop_icons
    install -d -m 0755 -o "$REAL_USER" -g "$REAL_USER" "$APPLICATIONS_DIR" "$desktop_dir"
    install -m 0644 -o "$REAL_USER" -g "$REAL_USER" "$DESKTOP_ENTRY_SOURCE" "$APPLICATION_ENTRY"
    install -m 0644 -o "$REAL_USER" -g "$REAL_USER" "$CHOOSER_ENTRY_SOURCE" "$CHOOSER_APPLICATION_ENTRY"
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
    rm -f "$APPLICATION_ENTRY" "$CHOOSER_APPLICATION_ENTRY" "$desktop_dir/$DESKTOP_ENTRY_NAME"
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
    local package_source="${1:-$INSTALL_DIR}"

    if [ ! -x "$python" ]; then
        log_error "Deployment Python is missing or not executable: $python"
        return 1
    fi

    log_info "Installing Open MMI package and console commands..."
    local pip_arguments=(install --upgrade --force-reinstall)
    if [[ "$package_source" == *.whl ]]; then
        pip_arguments+=(--no-deps)
    fi
    if ! ( umask 0022; env -u PYTHONPATH "$python" -m pip "${pip_arguments[@]}" "$package_source" ); then
        log_error "Failed to install Open MMI package"
        return 1
    fi

    verify_console_commands
    env -u PYTHONPATH "$python" -I -c 'import canbusd.core, ui.config_cli, ui.web_dashboard.server'
    if [[ $EUID -eq 0 && "$REAL_USER" != root ]]; then
        sudo -u "$REAL_USER" env -u PYTHONPATH "$python" -I \
            -c 'import canbusd.core, ui.config_cli, ui.web_dashboard.server'
    fi
}

configure_maintained_catalogue_permissions() {
    local catalogue_root

    for catalogue_root in "$INSTALL_DIR/vehicles" "$INSTALL_DIR/bindings"; do
        [ -d "$catalogue_root" ] || continue

        # Prepared updates run with UMask=0027 and preserve staged modes.  The
        # maintained catalogue is non-secret installed product data and must be
        # readable by the unprivileged dashboard and canbusd services.
        find "$catalogue_root" -type d \
            -exec chown root:root {} + \
            -exec chmod 0755 {} +
        find "$catalogue_root" -type f \
            -exec chown root:root {} + \
            -exec chmod 0644 {} +
    done
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

migrate_legacy_dashboard_startup() {
    local config_file="$USER_CONFIG_DIR/launcher.json"

    if [ ! -f "$config_file" ]; then
        return 0
    fi

    if sudo -u "$REAL_USER" env HOME="$REAL_HOME" python3 - "$config_file" <<'PY_CONFIG'
import json
import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    raise SystemExit(1)

if not isinstance(payload, dict) or "start_at_login" not in payload:
    raise SystemExit(1)

payload.pop("start_at_login", None)
temporary = path.with_suffix(path.suffix + ".tmp")
temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
os.chmod(temporary, 0o600)
temporary.replace(path)
PY_CONFIG
    then
        log_info "Migrating legacy dashboard-service startup preference..."
        export XDG_RUNTIME_DIR="/run/user/$USER_ID"
        sudo -u "$REAL_USER" env HOME="$REAL_HOME" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" systemctl --user disable open-mmi-dashboard.service >/dev/null 2>&1 || true
    fi
}

configure_install_service_defaults() {
    export XDG_RUNTIME_DIR="/run/user/$USER_ID"
    sudo -u "$REAL_USER" env HOME="$REAL_HOME" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" systemctl --user enable canbusd.service
    sudo -u "$REAL_USER" env HOME="$REAL_HOME" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" systemctl --user disable open-mmi-dashboard.service >/dev/null 2>&1 || true
    migrate_legacy_dashboard_startup
}

configure_update_service_defaults() {
    export XDG_RUNTIME_DIR="/run/user/$USER_ID"
    sudo -u "$REAL_USER" env HOME="$REAL_HOME" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" systemctl --user enable canbusd.service
    migrate_legacy_dashboard_startup
}

install_update_coordinator() {
    local authorization_added=false
    if ! getent group "$UPDATE_COORDINATOR_GROUP" >/dev/null 2>&1; then
        groupadd --system "$UPDATE_COORDINATOR_GROUP"
    fi
    if ! id -nG "$REAL_USER" | tr ' ' '\n' | grep -Fqx "$UPDATE_COORDINATOR_GROUP"; then
        usermod -aG "$UPDATE_COORDINATOR_GROUP" "$REAL_USER"
        authorization_added=true
    fi
    install -d -m 0755 -o root -g root /etc/systemd/system
    install -m 0644 -o root -g root \
        "$REPO_ROOT/systemd/system/$UPDATE_COORDINATOR_UNIT" \
        "/etc/systemd/system/$UPDATE_COORDINATOR_UNIT"
    install -m 0644 -o root -g root \
        "$REPO_ROOT/systemd/system/$UPDATE_INSTALLER_UNIT" \
        "/etc/systemd/system/$UPDATE_INSTALLER_UNIT"
    install -d -m 0755 -o root -g root "$UPDATE_COORDINATOR_STATE_DIR"
    systemctl daemon-reload
    systemctl enable "$UPDATE_COORDINATOR_UNIT"
    if [ "${OPEN_MMI_PREPARED_DEPLOYMENT:-0}" != 1 ]; then
        systemctl restart "$UPDATE_COORDINATOR_UNIT"
    fi
    if [ "$authorization_added" = true ]; then
        log_warn "Log out and back in before using update actions without sudo."
    fi
}

remove_login_autostart() {
    if [ -f "$LOGIN_AUTOSTART_ENTRY" ] && grep -Fqx "Exec=/usr/local/bin/open-mmi-launcher" "$LOGIN_AUTOSTART_ENTRY"; then
        rm -f "$LOGIN_AUTOSTART_ENTRY"
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

    configure_maintained_catalogue_permissions

    if ! install_open_mmi_package; then
        return 1
    fi
    if ! install_command_links; then
        return 1
    fi
    install_update_coordinator
    
    # Store version and the managed source descriptor used by read-only checks.
    get_current_version > "$VERSION_FILE"
    write_checkout_update_source_metadata
    
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
    configure_install_service_defaults
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

    configure_maintained_catalogue_permissions

    if ! install_open_mmi_package; then
        return 1
    fi
    if ! install_command_links; then
        return 1
    fi
    install_update_coordinator

    local user_systemd_dir="$REAL_HOME/.config/systemd/user"
    sudo install -d -m 0755 -o "$REAL_USER" -g "$REAL_USER" "$user_systemd_dir"
    sudo install -m 0644 -o "$REAL_USER" -g "$REAL_USER" "$REPO_ROOT/systemd/user/canbusd.service" "$user_systemd_dir/canbusd.service"
    sudo install -m 0644 -o "$REAL_USER" -g "$REAL_USER" "$REPO_ROOT/systemd/user/open-mmi-dashboard.service" "$user_systemd_dir/open-mmi-dashboard.service"
    install_desktop_entry

    export XDG_RUNTIME_DIR="/run/user/$USER_ID"

    sudo -u "$REAL_USER" env HOME="$REAL_HOME" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" systemctl --user daemon-reload
    configure_update_service_defaults

    # Version and managed source metadata writes need root because /opt is root-owned.
    sudo bash -c "echo '$new_version' > '$VERSION_FILE'"
    write_checkout_update_source_metadata

    # Restart services
    sudo -u "$REAL_USER" env HOME="$REAL_HOME" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" systemctl --user restart canbusd.service open-mmi-dashboard.service

    log_success "Update complete → $new_version"

    log_info "Fixing repository ownership..."
    sudo chown -R "$REAL_USER:$REAL_USER" "$REPO_ROOT"
}

# Fixed internal entry point used only by the root-owned one-shot update
# installer. All values are derived by that service from trusted state.
cmd_deploy_prepared() {
    local stage="${OPEN_MMI_PREPARED_STAGE:-}"
    local transaction="${OPEN_MMI_PREPARED_TRANSACTION:-}"
    local commit="${OPEN_MMI_PREPARED_COMMIT:-}"
    local previous_commit="${OPEN_MMI_PREVIOUS_COMMIT:-}"
    local version="${OPEN_MMI_PREPARED_VERSION:-}"
    local rollback_root="/var/lib/open-mmi/rollback/$transaction"
    local deployment_stage="backup"
    local candidate_wheel_dir="$rollback_root/candidate-wheel"
    local candidate_wheel
    local -a candidate_wheels=()
    local resolved_stage

    [[ $EUID -eq 0 ]] || { log_error "Prepared deployment requires root"; return 1; }
    [[ "$transaction" =~ ^prepare-[0-9a-f]{32}$ ]] || { log_error "Invalid prepared transaction"; return 1; }
    [[ "$commit" =~ ^[0-9a-fA-F]{40}$ ]] || { log_error "Invalid prepared commit"; return 1; }
    [[ "$previous_commit" =~ ^[0-9a-fA-F]{40}$ ]] || { log_error "Invalid previous commit"; return 1; }
    [[ -n "$version" && -n "${OPEN_MMI_MANAGED_REPOSITORY:-}" && -n "${OPEN_MMI_MANAGED_BRANCH:-}" && -n "${OPEN_MMI_MANAGED_UPSTREAM:-}" ]] || {
        log_error "Prepared deployment metadata is incomplete"; return 1;
    }
    resolved_stage=$(realpath -e -- "$stage") || { log_error "Prepared stage is unavailable"; return 1; }
    [[ "$resolved_stage" == "/var/lib/open-mmi/staging/$transaction" ]] || {
        log_error "Prepared stage is outside managed staging"; return 1;
    }
    [[ ! -L "$resolved_stage" && $(stat -c '%u' "$resolved_stage") -eq 0 ]] || {
        log_error "Prepared stage is untrusted"; return 1;
    }
    [[ $(git -c safe.directory="$resolved_stage" -C "$resolved_stage" rev-parse HEAD) == "$commit" ]] || {
        log_error "Prepared commit identity changed"; return 1;
    }

    install -d -m 0700 -o root -g root "$rollback_root"
    if [ -e "$INSTALL_DIR" ]; then
        cp -a -- "$INSTALL_DIR" "$rollback_root/installation"
        env -u PYTHONPATH "$rollback_root/installation/venv/bin/python" -I -c 'import ui.config_cli'
    fi
    install -d -m 0700 -o root -g root "$rollback_root/system-units" "$rollback_root/user-units"
    for unit in "$UPDATE_COORDINATOR_UNIT" "$UPDATE_INSTALLER_UNIT"; do
        if [ -e "/etc/systemd/system/$unit" ]; then
            cp -a -- "/etc/systemd/system/$unit" "$rollback_root/system-units/$unit"
        else
            : > "$rollback_root/system-units/$unit.absent"
        fi
    done
    for unit in canbusd.service open-mmi-dashboard.service; do
        if [ -e "$REAL_HOME/.config/systemd/user/$unit" ]; then
            cp -a -- "$REAL_HOME/.config/systemd/user/$unit" "$rollback_root/user-units/$unit"
        else
            : > "$rollback_root/user-units/$unit.absent"
        fi
    done

    rollback_prepared_deployment() {
        trap - ERR
        log_error "Prepared deployment failed at stage: $deployment_stage"
        log_error "Restoring previous installation"
        if [ -d "$rollback_root/installation" ]; then
            local failed_install="$INSTALL_DIR.failed-$transaction"
            local restored_install="$INSTALL_DIR.restore-$transaction"
            rm -rf -- "$failed_install" "$restored_install"
            cp -a -- "$rollback_root/installation" "$restored_install"
            mv -- "$INSTALL_DIR" "$failed_install"
            mv -- "$restored_install" "$INSTALL_DIR"
            if env -u PYTHONPATH "$INSTALL_DIR/venv/bin/python" -I -c 'import ui.config_cli' >/dev/null 2>&1; then
                log_success "Prepared rollback verified"
                rm -rf -- "$failed_install"
            else
                log_error "Previous Python installation could not be verified after restoration"
            fi
        fi
        if [ -d "${OPEN_MMI_MANAGED_REPOSITORY:-}/.git" ]; then
            sudo -u "$REAL_USER" git -C "$OPEN_MMI_MANAGED_REPOSITORY" reset --hard "$previous_commit" >/dev/null 2>&1 || true
        fi
        for unit in "$UPDATE_COORDINATOR_UNIT" "$UPDATE_INSTALLER_UNIT"; do
            if [ -e "$rollback_root/system-units/$unit" ]; then
                cp -a -- "$rollback_root/system-units/$unit" "/etc/systemd/system/$unit"
            elif [ -e "$rollback_root/system-units/$unit.absent" ]; then
                rm -f -- "/etc/systemd/system/$unit"
            fi
        done
        for unit in canbusd.service open-mmi-dashboard.service; do
            if [ -e "$rollback_root/user-units/$unit" ]; then
                cp -a -- "$rollback_root/user-units/$unit" "$REAL_HOME/.config/systemd/user/$unit"
                chown "$REAL_USER:$REAL_USER" "$REAL_HOME/.config/systemd/user/$unit"
            elif [ -e "$rollback_root/user-units/$unit.absent" ]; then
                rm -f -- "$REAL_HOME/.config/systemd/user/$unit"
            fi
        done
        systemctl daemon-reload >/dev/null 2>&1 || true
        export XDG_RUNTIME_DIR="/run/user/$USER_ID"
        sudo -u "$REAL_USER" env HOME="$REAL_HOME" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
            systemctl --user daemon-reload >/dev/null 2>&1 || true
        sudo -u "$REAL_USER" env HOME="$REAL_HOME" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
            systemctl --user restart canbusd.service open-mmi-dashboard.service >/dev/null 2>&1 || true
    }
    trap rollback_prepared_deployment ERR

    deployment_stage="package-build"
    install -d -m 0700 -o root -g root "$candidate_wheel_dir"
    env -u PYTHONPATH "$INSTALL_DIR/venv/bin/python" -m pip wheel --no-deps \
        --wheel-dir "$candidate_wheel_dir" "$resolved_stage"
    mapfile -t candidate_wheels < <(find "$candidate_wheel_dir" -maxdepth 1 -type f -name 'open_mmi-*.whl' -print)
    [[ ${#candidate_wheels[@]} -eq 1 ]]
    candidate_wheel="${candidate_wheels[0]}"
    env -u PYTHONPATH "$INSTALL_DIR/venv/bin/python" -I \
        "$resolved_stage/tools/verify_wheel.py" "$candidate_wheel"

    deployment_stage="repository-head"
    [[ $(sudo -u "$REAL_USER" git -C "$OPEN_MMI_MANAGED_REPOSITORY" rev-parse HEAD) == "$previous_commit" ]]
    deployment_stage="repository-clean"
    sudo -u "$REAL_USER" git -C "$OPEN_MMI_MANAGED_REPOSITORY" diff --quiet
    sudo -u "$REAL_USER" git -C "$OPEN_MMI_MANAGED_REPOSITORY" diff --cached --quiet
    deployment_stage="repository-fetch"
    sudo -u "$REAL_USER" git -C "$OPEN_MMI_MANAGED_REPOSITORY" fetch -- "${OPEN_MMI_MANAGED_UPSTREAM%%/*}"
    deployment_stage="repository-merge"
    sudo -u "$REAL_USER" git -C "$OPEN_MMI_MANAGED_REPOSITORY" merge --ff-only "$commit"

    deployment_stage="files"
    log_info "Deploying prepared candidate $version..."
    find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 \
        \( -name venv -o -name .version -o -name .update-source.json \) -prune \
        -o -exec rm -rf -- {} +
    for item in canbusd vehicles bindings actions ui scripts packaging systemd; do
        [ ! -e "$resolved_stage/$item" ] || cp -a -- "$resolved_stage/$item" "$INSTALL_DIR/"
    done
    for item in pyproject.toml README.md LICENSE; do
        cp -a -- "$resolved_stage/$item" "$INSTALL_DIR/"
    done

    configure_maintained_catalogue_permissions

    REPO_ROOT="$resolved_stage"
    DESKTOP_ENTRY_SOURCE="$REPO_ROOT/packaging/linux-desktop/open-mmi-status.desktop"
    CHOOSER_ENTRY_SOURCE="$REPO_ROOT/packaging/linux-desktop/open-mmi-chooser.desktop"
    DESKTOP_ICON_SOURCE="$REPO_ROOT/packaging/linux-desktop/icons"
    deployment_stage="package"
    install_open_mmi_package "$candidate_wheel"
    install_command_links
    deployment_stage="system-services"
    install_update_coordinator

    deployment_stage="user-services"
    local user_systemd_dir="$REAL_HOME/.config/systemd/user"
    install -d -m 0755 -o "$REAL_USER" -g "$REAL_USER" "$user_systemd_dir"
    install -m 0644 -o "$REAL_USER" -g "$REAL_USER" "$REPO_ROOT/systemd/user/canbusd.service" "$user_systemd_dir/canbusd.service"
    install -m 0644 -o "$REAL_USER" -g "$REAL_USER" "$REPO_ROOT/systemd/user/open-mmi-dashboard.service" "$user_systemd_dir/open-mmi-dashboard.service"
    install_desktop_entry

    printf '%s\n' "$version" > "$VERSION_FILE"
    write_update_source_metadata
    export XDG_RUNTIME_DIR="/run/user/$USER_ID"
    sudo -u "$REAL_USER" env HOME="$REAL_HOME" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" systemctl --user daemon-reload
    configure_update_service_defaults
    sudo -u "$REAL_USER" env HOME="$REAL_HOME" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
        systemctl --user restart canbusd.service open-mmi-dashboard.service

    deployment_stage="service-health"
    sudo -u "$REAL_USER" env HOME="$REAL_HOME" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
        systemctl --user is-active --quiet canbusd.service open-mmi-dashboard.service
    deployment_stage="api-health"
    local api_ready=false
    for _attempt in {1..15}; do
        if curl --fail --silent --max-time 2 http://127.0.0.1:8765/api/health >/dev/null; then
            api_ready=true
            break
        fi
        sleep 1
    done
    [[ "$api_ready" == true ]]
    deployment_stage="version-health"
    local version_ready=false
    for _attempt in {1..15}; do
        if curl --fail --silent --max-time 2 http://127.0.0.1:8765/api/version | \
            python3 -c 'import json,sys; expected=sys.argv[1]; payload=json.load(sys.stdin); raise SystemExit(0 if payload.get("build_id") == expected else 1)' "$version"; then
            version_ready=true
            break
        fi
        sleep 1
    done
    [[ "$version_ready" == true ]]
    trap - ERR
    log_success "Prepared update complete → $version"
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
    systemctl disable --now "$UPDATE_COORDINATOR_UNIT" >/dev/null 2>&1 || true
    systemctl stop "$UPDATE_INSTALLER_UNIT" >/dev/null 2>&1 || true
    rm -f "/etc/systemd/system/$UPDATE_COORDINATOR_UNIT" "/etc/systemd/system/$UPDATE_INSTALLER_UNIT"
    systemctl daemon-reload
    rm -rf "$UPDATE_COORDINATOR_RUNTIME_DIR" "$UPDATE_COORDINATOR_STATE_DIR"

    # Remove service file
    log_info "Removing systemd service..."
    rm -f \
        "$REAL_HOME/.config/systemd/user/canbusd.service" \
        "$REAL_HOME/.config/systemd/user/open-mmi-dashboard.service"
    sudo -u "$REAL_USER" \
        XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
        systemctl --user daemon-reload

    remove_desktop_entry
    remove_login_autostart
    remove_command_links
    
    # Remove application directory and root-owned update policy.
    log_info "Removing application files..."
    sudo rm -rf "$INSTALL_DIR"
    sudo rm -f "$UPDATE_POLICY_FILE"
    sudo rmdir "$(dirname "$UPDATE_POLICY_FILE")" >/dev/null 2>&1 || true
    
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

            local source_vehicle="$INSTALL_DIR/vehicles/$vehicle/config.json"
            local source_bindings="$INSTALL_DIR/bindings/$bindings.json"

            if [ ! -f "$source_vehicle" ]; then
                source_vehicle="$REPO_ROOT/vehicles/$vehicle/config.json"
            fi

            if [ ! -f "$source_bindings" ]; then
                source_bindings="$REPO_ROOT/bindings/$bindings.json"
            fi

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
            echo "    2. Installed app defaults"
            echo ""
            echo "  User config files are used only when explicitly selected."
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
        _deploy-prepared)
            check_root
            cmd_deploy_prepared
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
