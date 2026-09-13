Yes — the original goal was much broader than “add trust UI” or “fix CAN.” The goal was to build an **end-to-end owner-controlled trust architecture for Open MMI**, then expose it safely in the product.

The governing invariant we settled on was:

> **Trust the boundary you reviewed, and require explicit acknowledgement before that boundary can be expanded.**

Everything else was supposed to support that.

Here is the original target architecture and where we are against it.

| Original goalWhat it meantWhere we are                 |                                                                                                                               |                                                      |
| ------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| **1. Declare what a release intends to do**            | A release carries a Trust Manifest describing network, telemetry, CAN, persistence, identity-resolution etc.                  | **Done**                                             |
| **2. Separate declaration from authority**             | Candidate manifest says what the candidate wants. It must never be allowed to authorize itself.                               | **Done**                                             |
| **3. Maintain an owner-accepted boundary**             | Root-owned Accepted Owner Trust State represents what the owner has already approved.                                         | **Done**                                             |
| **4. Maintain trust lineage**                          | Append-only transition history records how the accepted boundary evolved.                                                     | **Done**                                             |
| **5. Make trust transitions monotonic by default**     | Equal/narrower candidate → proceed. Expanded boundary → stop and require explicit owner acknowledgement.                      | **Done at architecture/update-gate level**           |
| **6. Protect continuity across updates**               | Old trusted code verifies integrity/provenance and compares candidate declarations **before candidate privileged execution**. | **Done — C6**                                        |
| **7. Establish independent release provenance**        | Updates must be tied to a pinned signer/root, not merely a GitHub “Verified” badge.                                           | **Done — C6**                                        |
| **8. Establish runtime file integrity**                | Privileged deployed files are bound to the accepted release tree.                                                             | **Done — C6**                                        |
| **9. Enforce declared restrictions in the OS**         | Trust must not just be JSON claims; network/CAN/etc. need real OS-level boundaries.                                           | **Mostly done; CAN redesign pending hardware proof** |
| **10. Keep Inspector as evidence, not authority**      | Inspector reports whether deployed/runtime state satisfies the manifest. It cannot grant trust.                               | **Done**                                             |
| **11. Give owner visibility in the UI**                | Dashboard can show authoritative trust state and explain what needs attention.                                                | **Partially complete — C7**                          |
| **12. Keep trust mutations out of the browser**        | UI can explain/status-guide; acceptance/acknowledgement remains root + TTY with explicit phrases.                             | **Done architecturally**                             |
| **13. Support explicit expansion workflow**            | When a prepared update expands trust, show exactly what changed and tell owner how to acknowledge it from the trusted side.   | **Implemented — C7.4**                               |
| **14. Make first-time trust setup understandable**     | Owner can tell what is unestablished, establish integrity/provenance/state/lineage in the correct sequence, and see progress. | **Still incomplete — main remaining C7 work**        |
| **15. Prove all of this on the actual tablet/vehicle** | Install/update/reinstall/reboot/runtime behavior must match the model.                                                        | **Partially proven; must requalify after CAN fix**   |
| **16. Integrate through nightly and release**          | Feature → CI → hardware → nightly → CI → hardware → release.                                                                  | **Not yet**                                          |

### What C6 actually accomplished

C6 was the heavy security-foundation phase.

We built the chain roughly as:

```text
accepted owner trust state
        +
trust transition lineage
        +
release provenance
        +
release integrity
        +
candidate manifest comparison
        ↓
old trusted update gate
        ↓
candidate may proceed
```

The crucial property is that an update cannot simply arrive saying:

```text
"I need more permissions, therefore I am trusted for more permissions."
```

Instead:

```text
candidate requested boundary
        ↓
compare with previously accepted boundary

same/narrower ────────────► allowed

expansion
    │
    ▼
STOP
owner acknowledgement required
    │
    ▼
accepted boundary updated
    │
    ▼
candidate may proceed
```

That foundation is **complete enough that we formally called C6 complete**.

### What C7 was supposed to add

C7 is the owner-facing layer over that machinery.

It was never meant to turn the browser into a security authority.

The intended model is:

```text
ROOT-OWNED TRUST DATA
        │
        ▼
Trust Inspector
        │
        ▼
read-only trust status coordinator
        │
        ▼
AF_UNIX socket
        │
        ▼
Dashboard
```

while mutation stays:

```text
owner
  │
  ▼
local terminal
  │
  ▼
sudo + TTY + explicit confirmation
  │
  ▼
trust-state / lineage / integrity / provenance /
transition commands
```

We deliberately rejected a generic browser POST endpoint for accepting trust.

### Where C7 specifically stands

There are four useful pieces to think about:

**C7.1 — authoritative read-only status**

A lot of this is already built. We have the dedicated trust-status coordinator/service, fixed read-only socket action, Inspector contracts, dashboard plumbing and lifecycle work.

It was hardware-qualified once before the CAN regression was uncovered.

So this is **substantially implemented**, but the current feature tree needs another tablet qualification because the CAN enforcement architecture changed underneath it.

**C7.2 — owner-facing guidance**

We have pieces of this, including CLI/action guidance and prepared-transition guidance.

But we have not yet finished the polished “this is your trust state, this is why, this is exactly what you need to do next” owner experience.

So: **partially done**.

**C7.3 — trust setup progression**

This is the biggest unfinished owner-facing part.

For a fresh/legacy installation we want the UI to coherently distinguish things such as:

```text
Integrity
    not established / established

Release provenance
    not established / signer pinned

Trust state
    no accepted baseline / accepted

Lineage
    needs bootstrap / healthy

Prepared update
    no expansion / expansion awaiting acknowledgement
```

and guide the owner through those states without pretending the browser can perform privileged acceptance.

That progression/onboarding still needs finishing.

**C7.4 — prepared trust expansion**

This part is already integrated.

A prepared candidate that expands the boundary can be surfaced to the owner, with guidance for the trusted-side acknowledgement procedure.

So C7.4 is the most mature piece of C7.

---

### Why CAN suddenly consumed so much time

CAN wasn't the original goal. It exposed a flaw in one of our **enforcement assumptions**.

The manifest says:

```text
vehicle.can.receive  = allowed
vehicle.can.transmit = prohibited / os-enforced
```

We initially implemented that by putting physical CAN into `listen-only`.

Vehicle testing proved that was too simplistic: on this infotainment network, Open MMI apparently needs the controller to participate in the CAN link-layer ACK mechanism. In listen-only mode it doesn't ACK, the sender retransmits heavily, and useful traffic effectively collapses.

Your controlled A/B proved it:

```text
listen-only ON
7352 frames / 10 sec
1 unique ID
0x65F absent

listen-only OFF
2237 frames / 10 sec
27 unique IDs
0x65F present
TX remained zero
```

That forced us to refine what “transmit prohibited” means:

```text
prohibited:
    host must not originate CAN data frames

NOT prohibited:
    controller participating in CAN link-layer ACK
```

The new `6b0de79` design therefore isolates physical CAN instead:

```text
HOST NETNS

canbusd
   │
   ▼
openmmi-rx
   │
   ├── egress DROP
   │
   ▼
receive-only proxy

================ namespace boundary ================

private peer
   ▲
   │
one-way CAN gateway
   │
physical can0
   │
   ├── normal mode / ACK-capable
   └── egress DROP
   │
vehicle
```

So we retain the original security claim **without breaking CAN ACK semantics**.

That isn't a side feature—it repairs one of the enforcement foundations underneath the trust architecture.

### Where we are today

A useful overall progress picture is:

```text
Trust model / invariants               ██████████  essentially done
Manifest + accepted state + lineage    ██████████  done
Integrity + provenance                 ██████████  done
Update transition gate                 ██████████  done
Prepared expansion handling            ██████████  done
Inspector/evidence model               ██████████  done
OS enforcement                         █████████░  CAN needs hardware re-proof
Read-only trust UI plumbing            ████████░░  substantially there
Owner guidance                         ██████░░░░  partial
First-time/setup progression           ████░░░░░░  significant work remains
Final integration/hardware/release     ███░░░░░░░  still ahead
```

And the current branch has just reached an important point:

```text
owner-trust-controls-ui-v1

1706d76  previous validated feature HEAD
    │
    ▼
6b0de79  fix: isolate physical CAN receive path

162 focused tests PASS
1072 full tests PASS, 1 skipped
systemd-analyze verify PASS
signed commit
CI GREEN
```

The **next immediate gate is real tablet/vehicle qualification of** **`6b0de79`**.

If that passes, we stop treating CAN as an active architectural problem and return to the actual original objective: **finish C7.1–C7.3 so an owner can understand and safely operate the trust system we've already built.**

There is also one genuinely separate enforcement issue still on the books: **`vehicle.identity.remote-resolution = prohibited`** **needs its own enforcement closure.** Trust acceptance does not magically solve that.

So in one sentence: **we have built most of the security architecture we originally set out to build; we are now at the point where we need to prove the repaired CAN enforcement boundary on hardware, finish the owner-facing trust/setup experience, close the remaining enforcement gap, and then integrate/qualify the whole thing for release.**