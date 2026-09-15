# Open MMI Independent Trust Checker v1

`open_mmi_trust_check.py` is a standalone, read-only verifier for an installed
Open MMI system. It deliberately does **not** import or execute the installed
Open MMI Python package and does not consume Trust Inspector output.

The checker independently implements the v1 JSON canonicalization, digest,
lineage, inventory and manifest vocabulary rules. It uses the checker's own
`/usr/bin/git` and `/usr/bin/gpg` only to inspect Git objects and verify the
integrity-bound commit against the pinned public key.

## External anchor

A full check requires the owner to supply the expected OpenPGP **primary
fingerprint** from an independent source:

```sh
./open_mmi_trust_check.py \
  --expected-signer-fingerprint <FULL_PRIMARY_FINGERPRINT>
```

For a target filesystem mounted from rescue/live media:

```sh
./open_mmi_trust_check.py \
  --target-root /mnt/open-mmi-root \
  --expected-signer-fingerprint <FULL_PRIMARY_FINGERPRINT>
```

If the managed Git repository is not available at the path recorded by the
target's `.update-source.json`, pass a separately mounted repository explicitly:

```sh
./open_mmi_trust_check.py \
  --target-root /mnt/open-mmi-root \
  --repository /mnt/open-mmi-repository \
  --expected-signer-fingerprint <FULL_PRIMARY_FINGERPRINT>
```

Optional independent anchors can bind the checker executable itself and the
current transition-lineage head:

```sh
./open_mmi_trust_check.py \
  --expected-signer-fingerprint <FULL_PRIMARY_FINGERPRINT> \
  --expected-checker-sha256 sha256:<64-lowercase-hex> \
  --expected-lineage-head sha256:<64-lowercase-hex>
```

Use `--json` for machine-readable evidence.

## What v1 verifies

The checker independently validates:

- Trust Manifest v1 vocabulary and canonical digest;
- root-owned accepted owner trust state;
- the transition-lineage hash chain and current accepted-state anchor;
- installed release integrity-state canonicalization and recording anchors;
- the integrity inventory against the exact signed Git commit tree;
- active `/opt/open-mmi` source and site-packages bytes;
- the privileged Python interpreter ownership path;
- deployed privileged system/user unit bytes;
- externally measurable network, persistence and remote-identity systemd
  contracts understood by checker v1;
- the pinned OpenPGP public key against the externally supplied primary
  fingerprint; and
- the integrity-bound Git commit's offline signature.

Unknown future capability contracts are `UNVERIFIED`, not automatically trusted.
Missing evidence is also `UNVERIFIED`; malformed, contradictory or weakened
evidence is `FAIL`.

## Deliberate limit

This commit does not claim an independent physical CAN observation. The separate
CAN trust test owns challenge generation and challenge-bound passive-CAN evidence.
The Open MMI runtime must not gain CAN transmit authority in order to satisfy this
checker.

## Independent CAN topology and challenge checker

`open_mmi_can_trust_test.py` reports
`open-mmi-independent-can-trust-test-v2`. Its `production` dimension is a
read-only independent measurement of the private ACK-capable CAN receive
topology. It does not require `LISTEN-ONLY` and it never repairs or creates an
interface, namespace, qdisc, filter or CAN gateway.

The production collector uses only these fixed system executables:

- `/usr/bin/systemctl`
- `/usr/bin/nsenter`
- `/usr/bin/readlink`
- `/sbin/ip`
- `/sbin/tc`
- `/usr/bin/cangw`

Each executable is checked as a root-owned executable whose resolved file is
not group- or world-writable. A missing tool, insufficient privilege, missing
namespace or incomplete driver evidence yields `UNVERIFIED`.

The production check resolves only
`open-mmi-can-namespace.service`, records its `MainPID` and network namespace
identity, enters that namespace read-only, then rechecks both PID and namespace
identity after collection. It inspects:

- host `openmmi-rx` and absence of the physical `canN` on the host;
- private `canN` and `openmmi-rxp`, including the reciprocal vxcan peer indexes;
- `tc -json ... show` evidence for both exact egress DROP barriers;
- `cangw -L` for exactly one `canN -> openmmi-rxp` route and positive
  passive receive counters;
- physical controller mode and link state; and
- kernel parent-bus/device identity plus the fixed
  `/sys/bus/<bus>/devices/<device>/driver` symlink target.

On can-utils versions where a successful `cangw -L` returns its netlink
`sendto()` byte count instead of zero, the checker handles that quirk only for
the exact read-only list command. Stderr, malformed output, extra/reverse
routes, or missing live receive counters still fail closed or remain
`UNVERIFIED` as appropriate.

Real iproute2 may omit the active `ctrlmode` field when the kernel controller
mode flag word is zero. That absence is accepted only when a structurally valid
`ctrlmode_supported` list is present and explicitly advertises `LISTEN-ONLY`.
An active `LISTEN-ONLY` flag remains a production failure.

Driver evidence is derived from the physical link's validated `parentbus` and
`parentdev`. Missing, inaccessible or malformed controller/driver identity is
`UNVERIFIED`; the checker does not assume that every CAN controller name must
equal its kernel driver basename.

Run the production measurement with privilege sufficient to inspect the fixed
network namespace:

```sh
sudo ./independent_checker/open_mmi_can_trust_test.py \
  --mode production \
  --production-interface can0 \
  --json
```

The `challenge` dimension remains separate. It uses an explicitly isolated
`vcanN` selected by the checker operator and exercises Open MMI receive
behavior as a black box. Any CAN transmission in that challenge is
checker-owned and must never target the live vehicle interface.
