# Update security and permissions

| Field | Value |
| --- | --- |
| Branch | `v1-update-management` |
| Status | Status-only privileged boundary implemented; execution authorization pending |
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

The manual check endpoint accepts only an empty confirmation object. All Git inputs come from managed install metadata and pass strict validation before argument-list execution. No shell is involved. This descriptor is adequate for unprivileged read-only inspection; it is not sufficient authority for a future privileged installer. Channel selection is stored separately in root-owned `/etc/open-mmi/update-policy.json` and can be changed only through the administrative CLI.

Git runs with credential prompting disabled and bounded timeouts. Raw stderr and remote URLs are not returned to the UI. Stable and beta accept only fixed semantic tag forms from the hard-coded official repository identity; development remains bound to the installer-recorded branch.

## Future privileged component

A privileged component must use root-owned source/channel policy or independently trusted release manifests and should expose only fixed operations and validated identifiers, for example:

- status
- prepare approved candidate
- install prepared candidate
- report transaction status
- rollback recorded transaction

Authorization should be explicit and auditable. The dashboard process should remain unprivileged.

The initial coordinator slice implements only `status`. It has no generic
dispatch table and rejects every execution action and every extra request
field. Its root-owned state is safe for unprivileged inspection but cannot be
used to inject commands or execution parameters.

## Additional controls

- single active transaction lock;
- atomic state and metadata writes;
- strict ownership and file modes;
- path containment checks for staging/rollback files;
- bounded logs with secret redaction;
- signed manifest or release authenticity verification before stable/beta installation;
- explicit downgrade policy;
- no success state before health validation;
- no automatic update solely because a check found a different commit.


## Implemented policy-file controls

- fixed schema and fixed channel enum only;
- root ownership required at the production path;
- group/world-writable files rejected;
- symlinks and non-regular files rejected;
- unknown fields rejected, including repository/ref injection attempts;
- atomic replacement with file and directory `fsync`;
- invalid policy fails closed rather than defaulting;
- uninstall removes the root-owned policy.
