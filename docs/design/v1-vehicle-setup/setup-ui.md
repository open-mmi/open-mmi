# Vehicle setup UI

## Placement

Add **Vehicle setup** as a dedicated Settings category. Do not append the complete flow
to the existing System page.

The category owns local runtime configuration. It does not expose CAN transmit or
vehicle-control actions.

## Current contained slice

The contained implementation remains intentionally read-only. It displays the active
configuration, maintained/custom catalogue, selected bus and detected-adapter state.
Changing the profile or bindings selector creates an in-memory draft and shows
`Changes not applied`; it does not persist, provision hardware or restart the CAN
service. **Review current setup** or **Review changes** submits the allowlisted draft
to the fixed preview route and renders its normalized changes, warnings, interface
health and proposed effects inline. **Apply setup** remains disabled until the
privileged apply contract is implemented and qualified.

## Main panel

The collapsed overview contains:

```text
Vehicle setup                                      single CAN input

Vehicle profile    Seat 1P                         Maintained  [Change]
Bindings           Default                         Maintained  [Change]
Active CAN bus     Comfort                         profile default
CAN adapter        can0                            connected
Expected bitrate   100 kbit/s
Runtime            active configuration loaded

[Review changes]          [Advanced]
```

The action area includes its own inline status region. Success, warning and failure
messages must not appear only in a top-of-page banner or hover tooltip.

## Language

User-facing terms:

| Internal term | UI term |
| --- | --- |
| repo/default | Maintained |
| user override | Custom |
| SocketCAN interface | CAN adapter, with interface name in detail |
| source path override | Custom selection |
| daemon | CAN service, except in technical details |
| default_bus | Active CAN bus / profile default |

Full paths, revisions and generated files belong under **Technical details**.

## Profile selection

Profiles are grouped by source:

```text
Maintained
  (•) Seat 1P              VAG PQ35 · Comfort CAN · 100 kbit/s

Custom
  ( ) My Seat              Based on Seat 1P · locally modified
  (!) Capture experiment   Invalid JSON · not available to activate

[Use selected] [Create custom copy] [Cancel]
```

Choosing an entry changes only the draft selection. It does not restart the daemon.

## Bindings selection

Bindings show compatibility against the draft profile:

```text
Maintained
  (•) Default              12 of 12 events bound

Custom
  ( ) My controls          11 of 12 events bound · 1 warning
```

Missing bindings are warnings when the profile can otherwise run. Malformed actions or
unsafe action references are activation errors.

## CAN input selection

The first release displays one active logical bus. If a profile declares several buses,
the UI states:

> This Open MMI version can listen to one CAN bus at a time. Choose the active bus for
> this setup.

Interface choices distinguish state:

```text
Use profile default (can0)          recommended
can0                               present · up · receiving
can1                               present · down
vcan0                              virtual · development/replay
Previously selected can2           not currently detected
```

Advanced manual entry accepts only a valid Linux interface name. It does not accept a
command or provisioning script.

## Draft and active state

The panel must distinguish:

- **Active**: loaded by `canbusd`;
- **Draft**: currently selected in the form;
- **Saved custom file**: exists on disk; and
- **Applied descriptor**: coordinator source of truth.

When draft differs from active, show `Changes not applied` beside the action area.

Changing a custom file after activation shows `Custom file changed since activation`.
It is not silently reloaded unless a separately designed live-reload policy explicitly
permits it.

## Review screen

The read-only review screen is implemented. It is produced only from the backend
preview response; the browser does not invent filesystem paths, commands, services or
revisions. Changing either selector or refreshing active status invalidates the prior
review. A preview response that does not explicitly report `read_only: true`,
`apply_available: false` and `state: ready` is rejected by the browser.

Review shows only changed values first, followed by an expandable complete plan:

```text
Apply vehicle setup

Profile      Seat 1P · Maintained  ->  My Seat · Custom
Bindings     Default · Maintained  ->  Default · Maintained
CAN adapter  can0                  ->  can1
Provisioning can0 / 100 kbit/s     ->  can1 / 100 kbit/s

The CAN service will restart. Open MMI will not transmit CAN messages.

[Back to selection] [Apply setup — disabled]
```

The current slice stops here. It does not expose the proposed apply route and does not
write the canonical descriptor, systemd drop-in or udev rules.

## Progress and results

Progress stages shown in place:

```text
Validating setup…
Writing configuration…
Reloading adapter provisioning…
Restarting CAN service…
Verifying active configuration…
```

Success:

```text
Setup applied
Seat 1P / Default is active on comfort via can0.
```

Success with no adapter:

```text
Setup applied
The configuration is active. can0 is not currently detected.
```

Restored failure:

```text
Setup could not be activated
The previous configuration was restored and verified.
[Technical details]
```

## Custom-copy screen

The user chooses:

- template;
- custom display name;
- generated or edited identifier; and
- whether to open the new draft immediately.

Creation does not activate the file. Existing identifiers are never overwritten.

## Editor screen

Initial sections:

```text
Overview | CAN buses | Bindings | Advanced JSON | Validation
```

Profile and bindings remain separate documents even when edited in one workflow.

Primary actions:

```text
[Save draft] [Discard unsaved changes] [Review and activate]
```

`Review and activate` is disabled while validation contains errors.

## Tablet and accessibility requirements

- The 800×480 layout must keep the title, current selection and primary action visible
  without horizontal scrolling.
- Selection targets meet the existing touch target size.
- Modal or overlay content has an internal scroll boundary.
- Focus is restored after polling and re-rendering.
- Status is announced through an inline `aria-live` region.
- Colour is never the only distinction between maintained, custom, warning and error.
- Dropdowns and dialogs are keyboard-operable.
- Destructive replacement is absent; there is no generic overwrite action.

## Future onboarding

A first-run wizard may later reuse the same catalogue, preview and apply APIs. The first
implementation should remain a Settings feature so backend behaviour can qualify without
making startup depend on an unfinished wizard.
