#!/usr/bin/env bash
set -Eeuo pipefail

DESKTOP_FILE="open-mmi-status.desktop"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

SRC_DIR="$REPO_ROOT/packaging/linux-desktop"
DESKTOP_SRC="$SRC_DIR/$DESKTOP_FILE"
ICONS_SRC="$SRC_DIR/icons"

APP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons"

DESKTOP_DST="$APP_DIR/$DESKTOP_FILE"

log() {
  printf '[open-mmi-desktop] %s\n' "$*"
}

die() {
  printf '[open-mmi-desktop] ERROR: %s\n' "$*" >&2
  exit 1
}

install_desktop() {
  [[ -f "$DESKTOP_SRC" ]] || die "Missing desktop file: $DESKTOP_SRC"
  [[ -d "$ICONS_SRC" ]] || die "Missing icons directory: $ICONS_SRC"

  if command -v desktop-file-validate >/dev/null 2>&1; then
    desktop-file-validate "$DESKTOP_SRC"
  fi

  log "Installing desktop launcher"

  mkdir -p "$APP_DIR"
  cp -f "$DESKTOP_SRC" "$DESKTOP_DST"

  mkdir -p "$ICON_DIR"

  # hicolor is a shared theme, so merge Open MMI icons into it.
  mkdir -p "$ICON_DIR/hicolor"
  cp -a "$ICONS_SRC/hicolor/." "$ICON_DIR/hicolor/"

  # These are Open MMI-specific themes, so copying the whole folder is fine.
  rm -rf "$ICON_DIR/open-mmi-dark" "$ICON_DIR/open-mmi-light"
  cp -a "$ICONS_SRC/open-mmi-dark" "$ICON_DIR/"
  cp -a "$ICONS_SRC/open-mmi-light" "$ICON_DIR/"

  refresh_caches

  log "Installed: $DESKTOP_DST"
  log "Installed icons under: $ICON_DIR"
}

remove_desktop() {
  log "Removing desktop launcher"

  rm -f "$DESKTOP_DST"

  # Do not delete ~/.local/share/icons/hicolor itself; it is shared.
  rm -f "$ICON_DIR/hicolor/16x16/apps/open-mmi.png"
  rm -f "$ICON_DIR/hicolor/24x24/apps/open-mmi.png"
  rm -f "$ICON_DIR/hicolor/32x32/apps/open-mmi.png"
  rm -f "$ICON_DIR/hicolor/48x48/apps/open-mmi.png"
  rm -f "$ICON_DIR/hicolor/64x64/apps/open-mmi.png"
  rm -f "$ICON_DIR/hicolor/128x128/apps/open-mmi.png"
  rm -f "$ICON_DIR/hicolor/256x256/apps/open-mmi.png"
  rm -f "$ICON_DIR/hicolor/512x512/apps/open-mmi.png"
  rm -f "$ICON_DIR/hicolor/scalable/apps/open-mmi.svg"

  # These themes belong only to Open MMI.
  rm -rf "$ICON_DIR/open-mmi-dark"
  rm -rf "$ICON_DIR/open-mmi-light"

  refresh_caches

  log "Removed desktop launcher and Open MMI icons"
}

refresh_caches() {
  if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
  fi

  if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    for theme in hicolor open-mmi-dark open-mmi-light; do
      if [[ -f "$ICON_DIR/$theme/index.theme" ]]; then
        gtk-update-icon-cache -q -t -f "$ICON_DIR/$theme" >/dev/null 2>&1 || true
      fi
    done
  fi
}

case "${1:-}" in
  install)
    install_desktop
    ;;
  remove|uninstall)
    remove_desktop
    ;;
  reinstall)
    remove_desktop
    install_desktop
    ;;
  *)
    echo "Usage: $0 install|remove|reinstall"
    exit 1
    ;;
esac