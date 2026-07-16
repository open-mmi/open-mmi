# Desktop shell

The desktop shell provides one entry point for the Open MMI web dashboard and terminal status UI.

## Commands

```bash
open-mmi-launcher
open-mmi-launcher web
open-mmi-launcher tui
open-mmi-launcher --choose --remember
open-mmi-launcher --enable-startup
open-mmi-launcher --disable-startup
open-mmi-launcher --status
open-mmi-launcher --stop
open-mmi-config launcher status
open-mmi-config jellyfin status
```

`--choose` opens a Zenity or Yad selector when a graphical session is available. It falls back to the terminal chooser when run interactively without a graphical chooser. `--remember` persists the selected default interface.

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
  "health_poll_interval_seconds": 0.25,
  "start_at_login": true
}
```

`browser_command` may also be a command string or an argument array. The placeholders `{url}`, `{profile_dir}`, and `{window_class}` are replaced without invoking a shell.

`--enable-startup` and `--disable-startup` update `start_at_login` and the enabled state of `open-mmi-dashboard.service`. Install and update operations preserve that preference. The CAN daemon remains enabled independently.


## Dashboard and CLI settings

The installed dashboard exposes the same launcher configuration under **Settings → System**:

- choose the default Web or TUI interface;
- enable or disable dashboard startup at login;
- inspect dashboard service and health state;
- restart the dashboard through a fixed, allowlisted service action.

Equivalent CLI commands are:

```bash
open-mmi-config launcher status
open-mmi-config launcher default web
open-mmi-config launcher default tui
open-mmi-config launcher startup enable
open-mmi-config launcher startup disable
open-mmi-config dashboard restart
```

Both interfaces update `~/.config/open-mmi/launcher.json` and the actual
`open-mmi-dashboard.service` enablement state. The configuration API is accepted
only from a loopback, same-origin browser request.

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

They also install the existing repository icon theme beneath:

```text
~/.local/share/icons/hicolor/
```

The application-menu entry is installed read-only, while the desktop shortcut is executable and marked trusted with `gio` when available. Icon and desktop caches are refreshed when the relevant desktop utilities are available. `uninstall` removes both desktop entries and only the Open MMI icon files installed from the repository.

The desktop entry launches the remembered default interface. Its desktop actions provide explicit shortcuts for:

- choosing and remembering an interface;
- selecting the web dashboard;
- selecting the terminal UI.

The full desktop-entry and icon lifecycle is covered in CI without requiring a graphical desktop session.

## Dashboard service

```bash
systemctl --user status open-mmi-dashboard.service
systemctl --user restart open-mmi-dashboard.service
journalctl --user -u open-mmi-dashboard.service
```

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

`open-mmi-launcher --stop` continues to stop the dashboard service only. It does not kill browser processes.

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

`open-mmi-launcher --status` reports configured and actual startup state, dashboard service health, and the recorded browser instance, including whether its PID still matches the owned profile and URL.

## Tests and CI

Launcher behaviour is covered by `tests/test_launcher.py`, including:

- graphical and terminal interface selection;
- persisted default UI and startup preferences;
- service enable/disable commands;
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
