# Dashboard demo mode

Demo mode generates changing synthetic vehicle state so the Web dashboard can be
developed, reviewed, or demonstrated without a car.

From the repository root:

```bash
python3 ui/web_dashboard/server.py --demo --demo-scenario traffic
```

Open:

```text
http://127.0.0.1:8765/
```

## Scenarios

```bash
python3 ui/web_dashboard/server.py --demo --demo-scenario drive
python3 ui/web_dashboard/server.py --demo --demo-scenario traffic
python3 ui/web_dashboard/server.py --demo --demo-scenario doors-open
python3 ui/web_dashboard/server.py --demo --demo-scenario reverse
python3 ui/web_dashboard/server.py --demo --demo-scenario warnings
python3 ui/web_dashboard/server.py --demo --demo-scenario stale
```

- `drive` — smooth changing road-speed style values;
- `traffic` — stop/start values with indicators;
- `doors-open` — stationary vehicle with changing door/boot state;
- `reverse` — low-speed reverse state;
- `warnings` — coolant, voltage, hazard, bulb, door, and handbrake warnings;
- `stale` — changing values with intentionally old snapshot time.

Inspect the generated status payload:

```bash
curl http://127.0.0.1:8765/api/status | python3 -m json.tool
```

Demo data is synthetic. It is not qualification evidence and does not claim
support for another vehicle.
