# Open MMI web dashboard demo mode

This is a deliberately small dashboard pass. It only replaces:

```text
ui/web_dashboard/server.py
```

It does not change the HTML, CSS, JavaScript, gauges, layout, or styling.

## Apply

From a clean checkout of `beta/factory-web-dashboard`:

```bash
cd ~/open-mmi
git fetch origin
git checkout beta/factory-web-dashboard
git reset --hard origin/beta/factory-web-dashboard
git clean -fd
unzip -o ~/Downloads/open-mmi-demo-mode.zip
```

## Run with changing demo values

```bash
python3 ui/web_dashboard/server.py --demo
```

Open:

```text
http://127.0.0.1:8765/
```

The existing frontend polls `/api/status` every 500 ms, so speed, RPM, blower, voltage, coolant, range, odometer, lights, and other values should visibly change.

## Scenarios

```bash
python3 ui/web_dashboard/server.py --demo --demo-scenario drive
python3 ui/web_dashboard/server.py --demo --demo-scenario traffic
python3 ui/web_dashboard/server.py --demo --demo-scenario doors-open
python3 ui/web_dashboard/server.py --demo --demo-scenario reverse
python3 ui/web_dashboard/server.py --demo --demo-scenario warnings
python3 ui/web_dashboard/server.py --demo --demo-scenario stale
```

Available scenarios:

- `drive`: smooth changing road-speed style values.
- `traffic`: stop/start values with occasional indicators.
- `doors-open`: stationary, handbrake on, doors/boot states changing.
- `reverse`: low-speed reverse state.
- `warnings`: hot coolant, low voltage, hazards, bulb-out, door-open, handbrake.
- `stale`: changing JSON values but an intentionally old `updated_at`, for testing stale health handling.

## Check before commit

```bash
python3 -m py_compile ui/web_dashboard/server.py
python3 ui/web_dashboard/server.py --demo --port 9876
curl http://127.0.0.1:9876/api/status | python3 -m json.tool | head -40
```

Then in another terminal:

```bash
git diff -- ui/web_dashboard/server.py
```
