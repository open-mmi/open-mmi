# Update security and permissions

| Field | Value |
| --- | --- |
| Branch | `v1-update-management` |
| Status | Accepted security boundary; execution details pending |
| Owners | Dashboard API, future privileged coordinator, installer |

## Threat boundary

The dashboard is local-only, but local browser content and API requests still must not become a general command interface. Same-origin and loopback restrictions are necessary but not sufficient for privileged update execution.

## Prohibited browser inputs

The browser must never supply:

- executable names or shell fragments;
- `sudo` arguments;
- repository URLs;
- filesystem paths;
- remote names;
- branches, tags, refs, or commit expressions;
- service names;
- package-manager arguments;
- rollback archive names;
- environment-variable names or values.

## First-slice enforcement

The manual check endpoint accepts only an empty confirmation object. All Git inputs come from managed install metadata and pass strict validation before argument-list execution. No shell is involved. This descriptor is adequate for unprivileged read-only inspection; it is not sufficient authority for a future privileged installer.

Git runs with credential prompting disabled and bounded timeouts. Raw stderr and remote URLs are not returned to the UI.

## Future privileged component

A privileged component must use root-owned source/channel policy or independently trusted release manifests and should expose only fixed operations and validated identifiers, for example:

- status
- prepare approved candidate
- install prepared candidate
- report transaction status
- rollback recorded transaction

Authorization should be explicit and auditable. The dashboard process should remain unprivileged.

## Additional controls

- single active transaction lock;
- atomic state and metadata writes;
- strict ownership and file modes;
- path containment checks for staging/rollback files;
- bounded logs with secret redaction;
- signed manifest or release policy for stable/beta channels;
- explicit downgrade policy;
- no success state before health validation;
- no automatic update solely because a check found a different commit.
