# Vehicle profiles

open-mmi separates generic runtime logic from vehicle-specific CAN knowledge.

The backend should understand how to load profiles, decode configured rules, publish state, and survive interface reconnects. It should not contain hard-coded assumptions for a specific vehicle platform.

Vehicle-specific information belongs in `vehicles/<profile>/config.json`.

## Reference profile

The maintainer-tested reference vehicle is currently:

- Seat Leon 1P
- VAG PQ35 platform
- Comfort CAN at 100000 bitrate
- SocketCAN interface currently provisioned as `can0`

This does not mean open-mmi is a finished Seat/VW infotainment product. The project is currently alpha/backend software with an experimentally tested reference profile.

## What belongs in a vehicle profile

Vehicle profiles may define:

- CAN IDs used by that vehicle
- byte positions
- masks
- scaling rules
- status meanings
- display labels
- known quirks
- unknown or rapidly changing bytes observed during testing

Examples include:

- handbrake status
- lamp status
- steering angle
- indicator state
- washer fluid warning
- pad wear warning

## What does not belong in core logic

Core logic must not hard-code:

- Seat-specific CAN IDs
- VAG-specific byte meanings
- comfort CAN assumptions
- fixed interface names such as `can0`
- fixed bitrates such as `100000`
- dashboard labels that only make sense for one vehicle

The core should stay vehicle-independent.

## Status rules

Status rules describe how raw CAN data becomes useful state.

Current supported rule styles include boolean rules, masked boolean rules, and signed or scaled values.

### Boolean rules

A boolean rule checks whether a byte or value represents an on/off state.

### Masked boolean rules

A masked boolean rule checks whether a specific bit is set within a byte.

Example use case:

```text
handbrake active when mask 0x20 is set
```

This allows one byte to contain several independent status flags.

### Signed or scaled values

Some values are not simple on/off states. Steering angle is an example where the profile may need to describe direction, magnitude, scaling, or byte layout.

These rules should remain profile-driven where possible.

## Unknown bytes

Unknown bytes should be documented rather than guessed.

Use comments, notes, or roadmap documentation to record:

- bytes that change rapidly regardless of state
- bytes that appear stable
- states tested on a real vehicle
- values captured from replay logs
- values that need more samples

Avoid turning guesses into core behaviour.

## Adding a new profile

A new vehicle profile should start small.

Recommended process:

1. Copy an existing profile only if the platform is genuinely related.
2. Record the vehicle, platform, model year, and tested CAN bus.
3. Add one signal at a time.
4. Test against replay data where possible.
5. Test on a real vehicle only when safe.
6. Keep uncertain mappings clearly marked.
7. Do not modify core logic unless the rule type is genuinely reusable.

## Safety and expectations

Vehicle profiles are experimental.

A profile may be incomplete, wrong, or specific to a trim, module coding, model year, or retrofit state. open-mmi should not be treated as safety-critical software.
