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
```

`--choose` opens a Zenity or Yad selector when a graphical session is available. It falls back to the terminal chooser when run interactively without a graphical chooser. `--remember` persists the selected default interface.

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

Desktop integration tests install and remove the real repository desktop entry and icon tree inside temporary directories. The repository's GitHub Actions Python matrix runs all of these tests through the existing `unittest discover` step. No desktop session or real browser is required in CI because process, chooser, browser, and filesystem boundaries are injected in the tests.
