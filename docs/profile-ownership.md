# Profile and bindings ownership

OpenMMI has two kinds of user-visible configuration:

1. vehicle profiles
2. bindings

Both have repo/default versions and optional user override versions.

The rule is:

    Repo defaults are used by default.
    User overrides are sacred but opt-in only.

## Repo/default vehicle profiles

Vehicle profiles describe maintained CAN/status/action mappings for a vehicle platform.

Installed location:

    /opt/open-mmi/vehicles/<vehicle>/config.json

Development checkout location:

    vehicles/<vehicle>/config.json

Vehicle profiles are part of the OpenMMI repository. Normal users should receive profile improvements when OpenMMI updates.

Therefore, normal runtime should load the installed vehicle profile by default.

## Repo/default bindings

Default bindings describe the maintained default action/button mapping.

Installed location:

    /opt/open-mmi/bindings/<bindings>.json

Development checkout location:

    bindings/<bindings>.json

Default bindings are part of the OpenMMI repository. Normal users should receive default binding improvements when OpenMMI updates.

Therefore, normal runtime should load installed bindings by default.

## Maintained production resolution

When both an installed Open MMI tree and a development checkout exist, normal setup
and runtime selection use the maintained files under `/opt/open-mmi`.

This keeps the active vehicle profile and bindings aligned with the installed Open MMI
version. A checkout is a fallback before installation and may be preferred only through
an explicit development mode.

The presence of a checkout must not silently redirect a managed installation to mutable
source files.

## User vehicle profile overrides

A user vehicle profile override may exist at:

    ~/.config/open-mmi/vehicles/<vehicle>/config.json

This file is user-owned. It must never be overwritten by update, install, or apply-profile.

However, it is not used by default. It should only be active when explicitly selected.

Example explicit selection:

    OPEN_MMI_VEHICLE_CONFIG=/home/open-mmi/.config/open-mmi/vehicles/seat_1p/config.json

## User binding overrides

A user binding override may exist at:

    ~/.config/open-mmi/bindings/<bindings>.json

This file is user-owned. It must never be overwritten by update, install, or apply-profile.

However, it is not used by default. It should only be active when explicitly selected.

Example explicit selection:

    OPEN_MMI_BINDINGS_FILE=/home/open-mmi/.config/open-mmi/bindings/default.json

## Intended runtime precedence

Vehicle profile:

    1. OPEN_MMI_VEHICLE_CONFIG, if explicitly set
    2. /opt/open-mmi/vehicles/<vehicle>/config.json

Bindings:

    1. OPEN_MMI_BINDINGS_FILE, if explicitly set
    2. /opt/open-mmi/bindings/<bindings>.json

## Why user overrides are opt-in

If OpenMMI automatically prefers files in ~/.config/open-mmi, stale user-space copies can silently shadow updated repo defaults.

That creates confusing behaviour:

    OpenMMI update changes /opt/open-mmi/vehicles/seat_1p/config.json
    canbusd still loads ~/.config/open-mmi/vehicles/seat_1p/config.json
    new signals do not appear

The same problem can happen with bindings:

    OpenMMI update improves /opt/open-mmi/bindings/default.json
    runtime still loads ~/.config/open-mmi/bindings/default.json
    user never receives the improved default mapping

So user files must be protected, but not silently preferred.

## Sacred file rule

These files are sacred:

    ~/.config/open-mmi/vehicles/<vehicle>/config.json
    ~/.config/open-mmi/bindings/<bindings>.json

OpenMMI must not overwrite, refresh, migrate, or delete them automatically.

If a user wants to update a custom override, that must be an explicit user action.

## Normal setup

Normal setup should:

    use installed maintained vehicle profile
    use installed maintained bindings
    not create user override files
    not select user override files

## Override workflow

Create custom binding override:

    copy /opt/open-mmi/bindings/<bindings>.json
    to   ~/.config/open-mmi/bindings/<bindings>.json

    set:
    OPEN_MMI_BINDINGS_FILE=~/.config/open-mmi/bindings/<bindings>.json

Create custom vehicle profile override:

    copy /opt/open-mmi/vehicles/<vehicle>/config.json
    to   ~/.config/open-mmi/vehicles/<vehicle>/config.json

    set:
    OPEN_MMI_VEHICLE_CONFIG=~/.config/open-mmi/vehicles/<vehicle>/config.json

## Runtime logging

At daemon startup, canbusd should log the active files:

    Loaded config from: <path>
    Loaded bindings from: <path>

If user override files exist but are not selected, canbusd may warn:

    User vehicle profile override exists but is not active: ~/.config/open-mmi/vehicles/<vehicle>/config.json
    Set OPEN_MMI_VEHICLE_CONFIG to use it.

    User bindings override exists but is not active: ~/.config/open-mmi/bindings/<bindings>.json
    Set OPEN_MMI_BINDINGS_FILE to use it.

## Migration behaviour

Existing user override files must not be deleted or overwritten.

Safe migration path:

1. stop silently preferring user files
2. keep user files untouched
3. log clear active source paths
4. document how to opt into user overrides explicitly

## Summary

Installed maintained vehicle profiles are used by default.

Installed maintained bindings are used by default.

User vehicle profiles are sacred opt-in overrides.

User bindings are sacred opt-in overrides.
