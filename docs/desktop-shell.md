# Desktop shell

The desktop shell provides one entry point for the Open MMI web dashboard and terminal status UI.

## Commands

```bash
open-mmi-launcher
open-mmi-launcher web
open-mmi-launcher tui
open-mmi-launcher --choose --remember
open-mmi-launcher --choose --ask-remember
open-mmi-launcher --enable-autostart
open-mmi-launcher --disable-autostart
open-mmi-launcher --status
open-mmi-config launcher status
open-mmi-config jellyfin status
```

`--choose` opens a Zenity or Yad selector when a graphical session is available. It falls back to the terminal chooser when run interactively without a graphical chooser. `--remember` persists the selected default interface. `--ask-remember` keeps selection and persistence separate by asking whether the chosen interface should become the default.

## Installed commands

Install and update build Open MMI from the deployed source tree into `/opt/open-mmi/venv`. The installer verifies all packaged console wrappers and exposes them through managed links in `/usr/local/bin`:

```text
open-mmi-canbusd
open-mmi-config
open-mmi-dashboard
open-mmi-launcher
open-mmi-status
```

The installer refuses to replace unrelated files or symlinks with those names. Uninstall removes a command link only when it still points to the matching Open MMI wrapper. The desktop entry uses `/usr/local/bin/open-mmi-launcher`, so application-menu, desktop, and terminal launches all exercise the same installed command.

The default configuration path is:

```text
~/.config/open-mmi/launcher.json
```

Example:

```json
{
  "default_ui": "web",
  "web_url": "http://127.0.0.1:8765",
  "browser_mode": "kiosk",
  "browser_command": "auto",
  "startup_timeout_seconds": 12,
  "health_poll_interval_seconds": 0.25
}
```

`browser_command` may also be a command string or an argument array. The placeholders `{url}`, `{profile_dir}`, and `{window_class}` are replaced without invoking a shell.

`--enable-autostart` and `--disable-autostart` create or remove the graphical-session entry at `~/.config/autostart/open-mmi.desktop`. At login it runs the remembered interface through `/usr/local/bin/open-mmi-launcher`; the launcher starts the dashboard service on demand and waits for health before opening the browser. The older `--enable-startup` and `--disable-startup` spellings remain compatibility aliases for application autostart, not service enablement.


## Dashboard and CLI settings

The installed dashboard exposes the same launcher configuration under **Settings → System**:

- choose the default Web or TUI interface;
- open Open MMI automatically after graphical login;
- inspect dashboard health state.

Equivalent CLI commands are:

```bash
open-mmi-config launcher status
open-mmi-config launcher default web
open-mmi-config launcher default tui
open-mmi-config launcher autostart enable
open-mmi-config launcher autostart disable
open-mmi-config dashboard status
open-mmi-config dashboard start
open-mmi-config dashboard stop
open-mmi-config dashboard restart
open-mmi-config dashboard enable
open-mmi-config dashboard disable
```

The default-interface choice is stored in `~/.config/open-mmi/launcher.json`; application autostart is represented by `~/.config/autostart/open-mmi.desktop`. Dashboard service enablement is intentionally CLI-only. The configuration API is accepted only from a loopback, same-origin browser request.

## Jellyfin configuration

Jellyfin can be configured from **Settings → Media → Jellyfin setup** or with:

```bash
open-mmi-config jellyfin setup
open-mmi-config jellyfin test
open-mmi-config jellyfin status
open-mmi-config jellyfin clear
```

The interactive setup hides passwords and tokens. Existing environment-based
development setups can be imported without putting a secret in a command argument:

```bash
OPEN_MMI_JELLYFIN_URL='https://jellyfin.example:8096' OPEN_MMI_JELLYFIN_TOKEN='...' OPEN_MMI_JELLYFIN_USER_ID='...' open-mmi-config jellyfin import-env
```

Persistent values are written to:

```text
~/.config/open-mmi/dashboard.env
```

The directory is mode `0700`, the file is mode `0600`, and the dashboard service
loads it with `EnvironmentFile=-%h/.config/open-mmi/dashboard.env`. The browser
receives only redacted state such as `token_configured` or
`password_configured`; it never receives the stored secret. Restart the dashboard
after saving or clearing credentials so the service process loads the new values.

## Desktop launcher installation

`sudo ./scripts/manage.sh install` and `update` install the repository desktop entry in both locations:

```text
~/.local/share/applications/open-mmi.desktop
$(xdg-user-dir DESKTOP)/Open MMI.desktop
```

They also install an independent recovery entry in the application menu:

```text
~/.local/share/applications/open-mmi-chooser.desktop
```

They also install the existing repository icon theme beneath:

```text
~/.local/share/icons/hicolor/
```

The application-menu entry is installed read-only, while the desktop shortcut is executable and marked trusted with `gio` when available. Icon and desktop caches are refreshed when the relevant desktop utilities are available. `uninstall` removes both desktop entries and only the Open MMI icon files installed from the repository.

The desktop entry launches the remembered default interface. Its desktop actions provide explicit shortcuts for:

- choosing an interface and confirming whether to remember it;
- selecting the web dashboard;
- selecting the terminal UI.

The separate **Open MMI Interface Chooser** application always opens the chooser and ignores the remembered default. It remains available when the Terminal UI is configured as the normal Open MMI interface.

When a graphical TUI window closes or fails, the launcher opens the chooser. Selecting the Web Dashboard starts the service and managed browser; selecting the TUI starts another guarded terminal session. If the graphical chooser is cancelled or unavailable, the launcher opens the Web Dashboard for the current session rather than leaving a touchscreen-only user stranded.

The full desktop-entry and icon lifecycle is covered in CI without requiring a graphical desktop session.

## Dashboard service

The dashboard service is an advanced implementation control and is not exposed as a normal web preference. Fresh installs leave it disabled at login; the launcher starts it whenever the dashboard is opened. Use the CLI when a permanently running local API is required:

```bash
open-mmi-config dashboard status
open-mmi-config dashboard start
open-mmi-config dashboard stop
open-mmi-config dashboard restart
open-mmi-config dashboard enable
open-mmi-config dashboard disable
journalctl --user -u open-mmi-dashboard.service
```

Upgrades remove the legacy `start_at_login` launcher key and disable the dashboard service once. They do not silently turn that old service preference into a visible browser autostart.

The launcher checks the configured URL's `/api/health` endpoint. If the endpoint is unavailable, it starts the service, or restarts it when systemd reports that the service is already active. Browser launch happens only after a bounded health check succeeds.

## Single browser instance

For Chromium, Chrome, and Firefox, Open MMI creates a dedicated browser profile under:

```text
$XDG_STATE_HOME/open-mmi/browser-profile/
```

When `XDG_STATE_HOME` is unset, the fallback is:

```text
~/.local/state/open-mmi/browser-profile/
```

The launcher records the owned process in:

```text
$XDG_RUNTIME_DIR/open-mmi/browser.json
```

When `XDG_RUNTIME_DIR` is unset, the fallback is:

```text
~/.local/state/open-mmi/runtime/browser.json
```

A lock in the same runtime directory serialises simultaneous desktop clicks.

On each web launch the launcher:

1. Checks whether the recorded Open MMI browser process still owns the dedicated profile and dashboard URL.
2. Reuses that process instead of starting another window.
3. Attempts to focus the existing window with `wmctrl` or `xdotool` when either utility is available.
4. Removes stale state and starts a replacement after a browser crash.
5. Scans `/proc` for the dedicated profile before launching, allowing recovery when the state file was lost or the browser changed its supervising PID.
6. Refuses to launch over an active Open MMI profile using a different URL or display mode.

Normal browser profiles and unrelated browser sessions are not reused, stopped, or modified.

A custom browser wrapper is supported, but the wrapper should `exec` the browser directly and retain the dashboard URL in its command line. The strongest lost-state recovery applies to the built-in Chromium/Chrome and Firefox integrations because they use a dedicated profile marker.

`open-mmi-launcher --stop` remains as a compatibility command for stopping the dashboard service; normal service management is documented through `open-mmi-config dashboard`. It does not kill browser processes.

## Shared dashboard clock

The web dashboard header contains one persistent local-time clock shared by every page. The browser uses the tablet's local timezone; no backend time endpoint is required.

Clock preferences are stored with the existing dashboard settings under:

```text
openmmi.dashboard.settings.v1
```

The Display settings panel provides:

- clock visibility;
- 24-hour or 12-hour format;
- optional local date.

The clock updates at the next minute boundary rather than polling every second. Page navigation reuses the same header element, so changing pages does not recreate the clock or start additional timers.

## Status output

`open-mmi-launcher --status` reports application autostart, dashboard service state and health, and the recorded browser instance, including whether its PID still matches the owned profile and URL.

## Tests and CI

Launcher behaviour is covered by `tests/test_launcher.py`, including:

- graphical and terminal interface selection;
- persisted default UI and graphical autostart preferences;
- advanced dashboard service controls;
- first launch and state recording;
- repeated-click reuse;
- best-effort focusing without a shell;
- stale-state replacement after a crash;
- `/proc` recovery after state loss;
- changed-setting conflict handling;
- isolation from unrelated browser processes;
- managed Chromium and Firefox command construction.
- shared clock formatting, persistence, minute-boundary scheduling, and page-navigation stability.

Desktop integration tests install and remove the real repository desktop entry and icon tree inside temporary directories. Command lifecycle tests simulate package installation, verify all console wrappers, create and remove managed command links, refuse unrelated command conflicts atomically, and preserve unrelated files during uninstall. The repository's GitHub Actions Python matrix runs all of these tests through the existing `unittest discover` step. No desktop session or real browser is required in CI because process, chooser, browser, package, and filesystem boundaries are injected in the tests.
