# Future simultaneous multi-CAN runtime

## Current boundary

V1 setup management configures one active named bus and one SocketCAN interface. A
profile may describe multiple buses and rules may name a bus, but the daemon opens only
the selected bus.

The setup UI must state this directly. It must not show several assignments as active
until the runtime supports them.

## Why multiple daemon instances are rejected

Running one `canbusd` process per adapter would create competing ownership of:

- decoded status publication;
- status reset and persistence;
- presence timeouts;
- action execution ordering;
- configuration reload; and
- health reporting.

Simultaneous buses should therefore remain one process with one ordered state owner.

## Target runtime

The future runtime contains:

- a resolved configuration for every enabled logical bus;
- one independent receiver lifecycle per interface;
- a bus-aware rule index;
- one serialized decoder/state aggregator;
- one bounded ordered action queue; and
- per-bus machine-readable health.

Every received unit enters the decoder as:

```text
logical bus name
interface identity
CAN frame
monotonic receive timestamp
```

Rule identity becomes `(bus, CAN id, rule identity)`. Presence identity becomes
`(bus, CAN id)`. This prevents identical CAN identifiers on different vehicle networks
from colliding.

## Receiver lifecycle

Each bus independently:

1. waits for its configured interface;
2. opens the SocketCAN bus;
3. receives with a bounded timeout;
4. publishes health and last-frame freshness;
5. closes on interface loss or receive failure;
6. backs off independently; and
7. reconnects without stopping other buses.

One failed adapter must not suspend decoding from another adapter.

## State aggregation

Workers must not write the persisted dashboard snapshot independently. They submit
decoded updates to one ordered state owner.

The state model records provenance for diagnostics while keeping current canonical UI
paths stable:

```json
{
  "runtime": {
    "buses": {
      "comfort": {
        "interface": "can-comfort",
        "state": "receiving",
        "last_frame_age_seconds": 0.03
      },
      "powertrain": {
        "interface": "can-powertrain",
        "state": "waiting"
      }
    }
  }
}
```

Decoded values continue to use documented output paths. Conflicting profile paths across
buses are validation errors unless an explicit aggregation rule is later designed.

## Interface identity

Kernel names such as `can0` and `can1` may change with USB discovery order. Before real
multi-adapter qualification, collect read-only identity where available:

- udev path;
- USB serial;
- driver;
- parent device; and
- current network interface name.

The preferred long-term result is a stable interface name or trusted adapter identity,
for example `can-comfort` and `can-powertrain`. Linux interface length limits and
hardware without stable serial numbers must be handled explicitly.

The browser never submits a udev match expression. A future assignment helper selects
from coordinator-discovered opaque adapter identities and the coordinator generates
bounded rules.

## Multi-CAN UI

When runtime support exists, the single active-bus row becomes:

```text
Logical bus       Expected bitrate    Assigned adapter      Runtime
Comfort           100 kbit/s          CANable A             receiving
Powertrain        500 kbit/s          CANable B             receiving
```

Validation prevents accidental duplicate assignment unless a future transport explicitly
supports multiplexing.

## Qualification prerequisites

Before hardware qualification:

- dual-`vcan` tests prove same-ID isolation;
- independent disconnect/reconnect tests pass;
- presence expiry is independent per bus;
- status updates are serialized without lost fields;
- action order is deterministic;
- one failed worker does not restart healthy workers; and
- configuration reload swaps the complete bus set atomically.

Real qualification then covers USB reorder, reboot, hotplug and two adapters at different
bitrates on safe receive-only connections.
