# Configuration contract

## Source classes

Browser and API language uses `maintained` and `custom`.

`maintained` resolves only from installed Open MMI content:

```text
/opt/open-mmi/vehicles/<id>/config.json
/opt/open-mmi/bindings/<id>.json
```

`custom` resolves only from the configured service user's Open MMI directory:

```text
~/.config/open-mmi/vehicles/<id>/config.json
~/.config/open-mmi/bindings/<id>.json
```

The API never accepts an absolute or relative filesystem path. A caller supplies a
source class and identifier. The backend resolves the path beneath its fixed root.

## Identifier rules

Identifiers are opaque catalogue keys rather than display names. Initial identifiers
should satisfy:

```text
^[a-z0-9][a-z0-9_-]{0,63}$
```

The backend must reject separators, dot components, control characters, Unicode
lookalikes and identifiers which resolve through symlinks.

Display names may initially be derived from maintained identifiers. Optional metadata
can later provide richer names without changing selection identity.

## Catalogue behaviour

Catalogue discovery must:

- use `/opt/open-mmi` for maintained production entries;
- use the known service user's config root for custom entries;
- use explicit development roots only when development mode is configured;
- sort entries deterministically;
- return the source class and identifier, not a caller-reusable path;
- report malformed custom entries rather than hiding them;
- expose profile buses and summary counts only after safe parsing;
- calculate a content revision used for optimistic concurrency; and
- never create, repair, migrate or activate a file during a GET operation.

Suggested profile catalogue entry:

```json
{
  "source": "maintained",
  "id": "seat_1p",
  "display_name": "Seat 1P",
  "valid": true,
  "revision": "sha256:…",
  "default_bus": "comfort",
  "buses": [
    {
      "name": "comfort",
      "interface": "can0",
      "bitrate": 100000,
      "provisioning": "udev"
    }
  ],
  "event_count": 12,
  "status_rule_count": 29
}
```

Suggested bindings catalogue entry:

```json
{
  "source": "maintained",
  "id": "default",
  "display_name": "Default",
  "valid": true,
  "revision": "sha256:…",
  "binding_count": 12
}
```

## Canonical selection

The proposed canonical descriptor is:

```text
/etc/open-mmi/vehicle-configuration.json
```

It is root-owned, atomically written and readable by status tooling. It contains no
secret and no caller-provided path.

Schema version 1:

```json
{
  "schema_version": 1,
  "vehicle": {
    "source": "maintained",
    "id": "seat_1p",
    "revision": "sha256:…"
  },
  "bindings": {
    "source": "maintained",
    "id": "default",
    "revision": "sha256:…"
  },
  "runtime": {
    "mode": "single",
    "active_bus": "comfort",
    "buses": {
      "comfort": {
        "interface": "can0"
      }
    }
  },
  "applied_at": "2026-07-19T12:00:00+00:00"
}
```

The stored content revisions describe what was applied. Status can report when a custom
file has changed since activation without silently reapplying it.

The configured service user and config root come from trusted installation metadata,
not from this descriptor or the browser request.

## Derived configuration

The coordinator derives:

```text
~/.config/systemd/user/canbusd.service.d/10-can-runtime.conf
/etc/udev/rules.d/80-canbus.rules
```

The user service drop-in continues to expose compatibility environment variables:

```text
OPEN_MMI_VEHICLE
OPEN_MMI_BINDINGS
OPEN_MMI_VEHICLE_CONFIG
OPEN_MMI_BINDINGS_FILE
OPEN_MMI_CAN_BUS
OPEN_MMI_CAN_INTERFACE
```

For a maintained selection, explicit paths resolve to installed content. For a custom
selection, they resolve beneath the fixed user config root.

The canonical descriptor, not these derived variables, is the source of truth for the
setup UI.

## Read-only status API

The foundation slice exposes this fixed, loopback-only route:

```text
GET /api/system/vehicle-setup
```

Current response shape:

```json
{
  "api_version": 1,
  "read_only": true,
  "runtime_mode": "single",
  "catalogue": {
    "profiles": [],
    "bindings": [],
    "issues": []
  },
  "active": {
    "state": "ready",
    "errors": [],
    "vehicle": {"source": "maintained", "id": "seat_1p"},
    "bindings": {"source": "maintained", "id": "default"},
    "active_bus": "comfort",
    "interface": "can0",
    "interface_present": true,
    "configuration_revision": "sha256:…",
    "loaded": null
  },
  "interfaces": [],
  "compatibility": {
    "emitted_and_bound": [],
    "emitted_unbound": [],
    "bound_unemitted": [],
    "duplicate_emitted": []
  }
}
```

This first endpoint performs no mutation, accepts no query-selected path or source and
does not imply that activation is available. Coordinator capability and transaction
state are added only with the separately qualified apply boundary.

Interface entries distinguish configuration from live health:

```json
{
  "name": "can0",
  "kind": "socketcan",
  "present": true,
  "up": true,
  "configured_bitrate": 100000,
  "last_frame_age_seconds": 0.15
}
```

No recent frames is not the same as a missing interface, and neither means that profile
activation failed.

## Preview API

Proposed fixed route:

```text
POST /api/system/vehicle-setup/preview
```

Payload:

```json
{
  "vehicle": {"source": "maintained", "id": "seat_1p"},
  "bindings": {"source": "maintained", "id": "default"},
  "runtime": {
    "active_bus": "comfort",
    "buses": {"comfort": {"interface": "can0"}}
  }
}
```

Preview is read-only. It returns a normalized plan, compatibility results, warnings and
the current configuration revision required by apply.

## Apply API

Proposed fixed route:

```text
POST /api/system/vehicle-setup/apply
```

Payload includes the normalized source identities, assignments, the revision observed
during preview and explicit confirmation:

```json
{
  "vehicle": {"source": "maintained", "id": "seat_1p"},
  "bindings": {"source": "maintained", "id": "default"},
  "runtime": {
    "active_bus": "comfort",
    "buses": {"comfort": {"interface": "can0"}}
  },
  "expected_configuration_revision": "sha256:…",
  "confirm": true
}
```

The dashboard normalizes this request and sends a fixed coordinator action. The
coordinator independently resolves and revalidates all inputs before mutation.

## Custom-file routes

Custom operations remain fixed routes rather than path-shaped routes:

```text
POST /api/system/vehicle-custom/create
POST /api/system/vehicle-custom/load
POST /api/system/vehicle-custom/save
```

Each payload names `kind`, `id`, `template_source` and `template_id` where applicable.
Only `profile` and `bindings` are accepted kinds.

Draft content requires a separate bounded request limit large enough for existing
profiles. Existing small configuration routes should retain their current lower limit.
