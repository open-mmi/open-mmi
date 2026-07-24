# Automatic suspend from CAN silence

Open MMI can optionally suspend the host after the active physical SocketCAN bus
has remained completely silent for a configured interval. This is implemented by
the standalone `open-mmi-powerd` system service. It is not a canonical vehicle
action and it does not run through the event-to-action dispatcher.

The policy is vehicle-independent: it follows the interface selected by Vehicle
Setup and contains no CAN IDs, manufacturer names, or payload matching. Each
vehicle integration still needs to qualify that its selected bus becomes quiet
when the vehicle sleeps and becomes active when the vehicle wakes.

The feature is disabled by default. Enable the tested 60-second policy with:

```bash
sudo ./scripts/manage.sh power enable 60
```

Inspect or disable it with:

```bash
sudo ./scripts/manage.sh power status
sudo ./scripts/manage.sh power disable
```

## Suspend decision

Before requesting suspend, `open-mmi-powerd` requires all of the following:

- the loaded Open MMI runtime reports a ready physical `canN` interface;
- at least one CAN frame has been observed since service start or the previous
  resume;
- that interface still exists, is administratively up, and is not BUS-OFF,
  stopped, disconnected, or unknown;
- the USB adapter and its host PCI wake ancestry expose enabled wake controls;
- no Open MMI update, vehicle-configuration, or lifecycle transaction holds its
  lock;
- the configured CAN-silence and post-resume guard intervals have elapsed.

A missing adapter, failed interface, BUS-OFF controller, invalid runtime status,
untrusted transaction lock, or unverified wake path fails closed and is not
interpreted as vehicle sleep.

`systemctl suspend` returns after resume. The daemon then closes and reopens its
CAN observation socket and requires fresh CAN traffic before another suspend can
occur. This prevents immediate suspend loops after resume or after a failed
suspend request.

## Vehicle qualification

A vehicle profile does not contain a special wake frame. Qualification confirms
that its selected physical bus:

1. becomes fully quiet when the vehicle has shut down;
2. does not remain silent for the configured interval during normal active use;
3. reliably produces valid traffic when the vehicle wakes; and
4. uses a CAN adapter and host USB path capable of remote wake.

Vehicles whose selected bus continues periodic background traffic will simply
remain awake. Vehicles whose active bus can legitimately remain silent for long
periods should leave this policy disabled or use a longer qualified interval.

## Policy file

The root-owned policy is stored at `/etc/open-mmi/power-policy.json`:

```json
{
  "schema_version": 1,
  "enabled": true,
  "trigger": "can_bus_silence",
  "silence_seconds": 60,
  "require_remote_wake": true,
  "resume_guard_seconds": 30
}
```

The policy is installation configuration, not vehicle-specific CAN knowledge.
Future trigger types can be added without changing the meaning of
`can_bus_silence`.
