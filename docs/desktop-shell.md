# Desktop shell

The desktop shell provides one entry point for the Open MMI web dashboard and
terminal status UI.

## Commands

```bash
open-mmi-launcher
open-mmi-launcher web
open-mmi-launcher tui
open-mmi-launcher --choose --remember
open-mmi-launcher --status
open-mmi-launcher --stop
```

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

`browser_command` may also be a command string or an argument array. A `{url}`
placeholder is replaced without invoking a shell.

## Dashboard service

```bash
systemctl --user status open-mmi-dashboard.service
systemctl --user restart open-mmi-dashboard.service
journalctl --user -u open-mmi-dashboard.service
```

The launcher checks the configured URL's `/api/health` endpoint. If the endpoint
is unavailable, it starts the service, or restarts it when systemd reports that
the service is already active. Browser launch happens only after a bounded
health-check succeeds.
