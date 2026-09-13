````
# Open-MMI Trust Architecture — Initial Deep Dive

## 1. Objective

The long-term Open-MMI trust promise should not be:

> Trust the maintainer.

It should be:

> Trust the boundary you reviewed, and require explicit acknowledgement before that boundary can be expanded.

A valid Open-MMI installation should therefore distinguish between:

**authenticity** — who produced the software;

**compliance** — what the software is permitted to do;

**owner authorization** — what boundary expansions this particular owner has accepted;

**continuity** — whether those guarantees survived every update since the owner's original trust anchor.

A signed Sheepdog97 commit establishes provenance.

It must not grant unlimited authority to redefine an existing owner's trust contract.

---

# 2. What the current codebase already gives us

The current Nightly is much better positioned for this than a normal application.

### Vehicle CAN

There is one central SocketCAN receive path in `canbusd/core.py`.

Production code currently contains no CAN `.send()` implementation.

The documented security policy explicitly says:

* passive CAN receive;
* vehicle CAN transmission/control is outside the current project scope;
* adding transmission requires separate design, warnings, allowlists, review and controlled testing.

This is already a philosophical boundary.

What it lacks is hard runtime enforcement.

Today:

> Open-MMI doesn't transmit CAN.

The future target is:

> Ordinary Open-MMI components cannot acquire CAN-transmit authority without an explicit trust-boundary change.

---

### Privileged configuration

`open-mmi-vehicle-config-coordinator.service` is an excellent precedent for future Trust Core design.

It already uses ideas we want:

* root-owned configuration;
* AF_UNIX-only control interface;
* caller cannot choose arbitrary privileged commands;
* revision-bound review;
* no-follow handling;
* restrictive systemd sandbox;
* explicit transaction state;
* fail-closed validation;
* narrow writable paths.

That architectural style should be reused rather than inventing an entirely different security model.

---

### Updates

The updater already has important trust-continuity primitives.

It records the installed commit, fixed repository metadata and channel policy.

A candidate has to prove forward Git ancestry.

The privileged installer re-validates the prepared candidate before deployment.

Staging and rollback are isolated.

Health failure can restore the previous installation.

This means the difficult future problem is not:

> How do we safely download and stage V10?

A lot of that already exists.

The missing question is:

> What is V10 allowed to change relative to V9?

---

### Explicit privacy boundaries already exist

Internet Radio is particularly important philosophically.

It already demonstrates:

* external network functionality is optional;
* acknowledgement is explicit;
* acknowledgement is versioned;
* materially changing the privacy notice invalidates the old acknowledgement.

Telemetry Guard therefore doesn't introduce the principle.

It generalises an existing Open-MMI principle into something enforced at a lower layer.

---

# 3. The most important architectural separation

We should NOT create one file called `trust.json` containing everything.

Three authorities must eventually exist.

## A. Release Trust Manifest

Owned by the release.

It says:

> This is what this software proposes to be allowed to do.

The candidate can declare capabilities.

It cannot authorize them.

---

## B. Accepted Owner Trust State

Owned by the currently installed trusted system.

Conceptually:

```text
/var/lib/open-mmi/trust/accepted-policy.json
```

Root-owned.

Not supplied by the candidate release.

It says:

> This is the boundary the owner has already accepted.

This is what V9 uses to judge V10.

---

## C. Trust Transition History

Append-only evidence recording authorized transitions.

Conceptually:

```text
V1 policy hash
      ↓
V2 transition
      ↓
V3 transition
      ↓
...
      ↓
current accepted state
```

This eventually makes V1→V10 continuity independently verifiable.

Keeping these separate is crucial.

Otherwise V10 could simply ship:

```text
owner_accepted_everything = true
```

and certify itself.

---

# 4. Trust Manifest v1

I would make the first Nightly trust feature a strict machine-readable capability document.

Conceptually:

```json
{
  "schema_version": 1,
  "manifest_id": "open-mmi.trust",
  "policy_generation": 1,

  "capabilities": {
    "vehicle.can.receive": {
      "policy": "allowed"
    },

    "vehicle.can.transmit": {
      "policy": "prohibited"
    },

    "telemetry.collection": {
      "policy": "prohibited-by-default",
      "activation": "local-owner-opt-in"
    },

    "vehicle.identity.remote-resolution": {
      "policy": "prohibited"
    },

    "network.egress": {
      "policy": "declared-purposes-only"
    },

    "vehicle-data.persistence": {
      "policy": "declared-purposes-only"
    }
  }
}
```

This is illustrative rather than the final schema.

The schema should be extremely strict:

* unknown fields rejected;
* unknown capability names rejected;
* bounded strings;
* stable canonical IDs;
* deterministic normalization;
* deterministic SHA-256 policy digest;
* schema version independent from policy generation.

A semantic change should never silently redefine an existing capability identifier.

The existing vehicle event/status/action registries already follow essentially this compatibility model.

---

# 5. Capability expansion needs a precise definition

The updater eventually needs to mechanically determine:

```text
OLD → NEW
```

and answer:

```text
equivalent?
narrower?
expanded?
```

Examples:

```text
CAN TX:
prohibited → prohibited
= equivalent

CAN TX:
allowed → prohibited
= narrower

CAN TX:
prohibited → allowed
= expansion
```

Likewise:

```text
telemetry:
none
→ local explicit opt-in
= expansion

telemetry:
local opt-in
→ default-on
= major expansion

network:
updates only
→ updates + telemetry endpoint
= expansion
```

A narrower policy should normally install without special permission.

An expansion should stop.

That gives us a monotonic trust model:

> Software may voluntarily surrender authority. It may not silently acquire authority.

---

# 6. Enforcement strength must also be part of the boundary

This is something I think we should include from the beginning.

Suppose V5 says:

```text
CAN TX prohibited
```

and enforces that using hardware/controller listen-only mode.

V6 still says:

```text
CAN TX prohibited
```

but removes the listen-only enforcement and merely promises not to call `send()`.

The declared capability hasn't changed.

But the trust boundary absolutely has.

Therefore Open-MMI needs to distinguish:

```text
POLICY
what is allowed

CONTROL
how that policy is enforced
```

Eventually a manifest might describe an assurance tier for individual controls.

For example:

```text
vehicle.can.transmit

policy:
    prohibited

controls:
    source contract
    CI contract
    process isolation
    SocketCAN listen-only
```

Removing an established enforcement layer should be treated as a trust-boundary expansion.

That protects against the subtler Trojan horse:

> “We haven't technically changed the privacy policy; we've just removed everything that enforced it.”

---

# 7. Existing networking needs to become explicit

The current project legitimately uses external networking.

That is not incompatible with the philosophy.

The problem is **undeclared networking**.

Current legitimate purposes include:

```text
update checking
Jellyfin
Internet Radio
```

Those should eventually become canonical capability/purpose IDs.

Something conceptually like:

```text
network.update-check
network.media.jellyfin
network.media.internet-radio
```

A future:

```text
network.telemetry.analytics
```

would therefore be glaringly obvious in a manifest diff.

### One pre-anchor cleanup I recommend

The current dashboard loads:

```text
Bootstrap 5.3.8
Bootstrap Icons
```

from `cdn.jsdelivr.net`.

That means simply rendering the ordinary Open-MMI dashboard can currently create an external request independently of Jellyfin, Radio or update checks.

Before establishing the first formal trust generation, I would vendor those assets locally.

Not because the CDN is inherently malicious.

Because:

> normal UI rendering should not require undeclared Internet access.

That is precisely the type of accidental boundary the future system is intended to make impossible.

---

# 8. Telemetry Guard becomes the first consumer of Trust Manifest

Only after the generic capability vocabulary exists would I implement Telemetry Guard.

The model becomes:

```text
Trust Manifest
      ↓
telemetry.collection policy
      ↓
Telemetry Guard
      ↓
collector registration
      ↓
local owner authorization
      ↓
collection
```

Rather than:

```text
some telemetry code
      ↓
remember to ask permission
```

Telemetry must be blocked **before collection**, not merely before upload.

That's important.

A component recording RPM, location-correlated state, button usage or behavioural information locally for later analytics is already collecting telemetry even if it hasn't uploaded anything.

---

# 9. Operational state is not telemetry

The trust specification needs to make this distinction explicitly.

Open-MMI must be able to process:

* RPM;
* temperatures;
* doors;
* lights;
* media state;
* CAN presence;
* trip counters;
* service reminders;

to perform requested local functionality.

That is ordinary operational processing.

Telemetry is collection for another purpose such as:

* analytics;
* profiling;
* fleet statistics;
* product metrics;
* usage measurement;
* diagnostic reporting;
* remote submission;
* long-term behavioural analysis.

The boundary should therefore be purpose-based.

Otherwise we'd accidentally create the absurd outcome where reading RPM to draw the tachometer requires telemetry consent.

---

# 10. Vehicle-data persistence deserves its own boundary

The current project already intentionally stores some vehicle-derived state.

Examples include local trip and service-reminder data.

That should remain possible.

But persistent data should have a declared purpose.

Conceptually:

```text
persistence.trip-meter
persistence.service-reminder
persistence.runtime-status
```

A future:

```text
persistence.analytics-driving-profile
```

would then be a new trust capability.

Again the philosophy isn't:

> Open-MMI never stores anything.

It's:

> Open-MMI does not silently change why it stores information.

---

# 11. CAN receive-only needs stronger enforcement later

Right now the CAN promise is primarily enforced by implementation:

```text
Bus.recv()
```

exists and production `.send()` doesn't.

That's a good baseline but not the final trust guarantee.

The eventual layers should become approximately:

```text
vehicle CAN
    ↓
receive-only interface/controller where supported
    ↓
small CAN ingestion process
    ↓
canonical event/status boundary
    ↓
rest of Open-MMI
```

The CAN-reading process should eventually be much more isolated than it currently is.

Today `canbusd` also dispatches local Linux actions.

Long term I would split:

```text
CAN receiver / decoder
        ↓
local event IPC
        ↓
action worker
```

Then the process holding the CAN socket does not need broad desktop/action capabilities.

Where the adapter/driver supports SocketCAN listen-only mode, that can add another enforcement layer.

If someone later wants active CAN transmission, they shouldn't add:

```python
bus.send(...)
```

to the existing daemon.

They should have to introduce an explicit new capability and architecture.

That makes the diff noisy.

---

# 12. Network egress eventually needs architectural funnels

The dashboard currently owns several network-capable integrations.

Eventually I'd prefer:

```text
Open-MMI local core
      │
      ├── update broker
      ├── Jellyfin broker
      ├── Radio broker
      └── future explicitly authorized brokers
```

The normal core should not need unrestricted Internet authority.

Then Telemetry Guard gains much stronger meaning.

Instead of:

> telemetry code promises not to open a socket

we get:

> telemetry code literally doesn't possess an undeclared external-network pathway.

That is the type of design that creates the “wow, they can't quietly do that” response you're aiming for.

---

# 13. The updater is where trust continuity ultimately lives

This is the biggest future change.

Currently the privileged installer eventually runs:

```text
<staged candidate>/scripts/manage.sh _deploy-prepared
```

as root.

That means the candidate contributes privileged deployment logic.

For normal development updates that's reasonable.

For trust continuity it eventually has to change.

The mature model needs to be:

```text
OLD TRUSTED VERSION
        │
        ├── authenticates candidate
        ├── reads candidate manifest as DATA
        ├── compares accepted old boundary
        ├── checks candidate structure
        ├── calculates trust delta
        │
        ├── unchanged/narrower
        │       ↓
        │    install
        │
        └── expanded
                ↓
              STOP
                ↓
       OLD SOFTWARE asks owner
```

Candidate code should not execute merely to prove that the candidate is safe to execute.

That is fundamental.

---

# 14. A small Trust Core should eventually own that process

Rather than putting this authority in the dashboard, I'd eventually extract a very small root-owned component.

Conceptually:

```text
/usr/lib/open-mmi-trust/
    verifier
    manifest parser
    transition comparator
    deployment engine

/etc/open-mmi/trust/
    system trust configuration

/var/lib/open-mmi/trust/
    accepted owner policy
    lineage
    acknowledgements
```

Properties:

```text
no arbitrary caller commands
no arbitrary paths
no arbitrary repository URLs
no general browser control
minimal dependencies
minimal network authority
small enough to audit
```

The existing vehicle-config coordinator is already a strong architectural template.

---

# 15. The Trust Core itself is a protected capability

This is critical.

Imagine V12 proposes:

```text
trustcore/*
```

changes.

It must not get a free pass merely because the update is officially signed.

Changing the component responsible for deciding whether updates are trustworthy is itself an important trust event.

Eventually we may permit compatible Trust Core upgrades automatically where the old core can mechanically verify that the new implementation preserves the contract.

But major verifier-policy changes should be unusually conspicuous.

---

# 16. CI should start enforcing trust invariants long before the full Trust Core exists

We can get useful protection early.

Trust-generation CI should eventually contain checks such as:

```text
trust manifest validates

stable capability IDs were not semantically rewritten

normal dashboard HTML contains no undeclared remote script/style dependency

production CAN code contains no transmit path

new outbound networking appears only behind declared network-purpose modules

Trust Manifest is included in packaged artifacts

trust-sensitive systemd units satisfy required sandbox contracts

Telemetry collectors cannot be registered without a declared scope

material trust-policy changes produce a visible trust-delta test failure
```

This doesn't replace runtime enforcement.

But it makes accidental erosion much harder.

And it makes intentional erosion much louder in code review.

---

# 17. Official provenance and Open-MMI compliance must remain separate

This is important for SIs.

An official Open-MMI release can prove:

```text
official artifact
+
Open-MMI compliant
```

An SI distribution should potentially be able to prove:

```text
not byte-for-byte official
+
Open-MMI trust compliant
```

An official future Open-MMI release that weakens required boundaries should theoretically be able to produce:

```text
official artifact
+
trust boundary changed
```

The Trust Checker should not simply ask:

> Is this an official hash?

Otherwise good SIs can't participate.

It should ask:

> What trust profile does this installation demonstrably satisfy?

This is how the Open-MMI reputation becomes empowering rather than exclusionary.

---

# 18. The CAN Trust Test fits later, not first

Once local Trust Inspection is meaningful, the CAN challenge mechanism becomes relatively straightforward.

Conceptually:

```text
external tester
      ↓
fresh challenge
      ↓
safe defined CAN transport
      ↓
Open-MMI receive path
      ↓
Trust Inspection mode
      ↓
screen displays challenge + result
```

The trigger must:

* grant no capability;
* change no trust state;
* authorize no update;
* enable no telemetry;
* transmit nothing from Open-MMI onto CAN.

It merely requests inspection.

The tester transmits.

Open-MMI receives.

---

# 19. Static PASS screens are not enough

An SI controlling the OS could eventually patch:

```text
result = PASS
```

Therefore Trust Test should ultimately include a fresh nonce/challenge.

Example:

```text
OPEN-MMI TRUST INSPECTION

Challenge:
A91F-4C22

Policy generation:
7

Trust lineage:
VERIFIED

CAN TX:
PROHIBITED

Telemetry:
DEFAULT DENY

Undeclared networking:
NONE

Evidence:
3F9A...7C11
```

The evidence must incorporate the supplied challenge.

That makes yesterday's screenshot useless as proof of today's state.

---

# 20. No response should mean UNVERIFIED

Your proposed field rule is sound with one wording qualification.

If an independent tester sends a valid Trust Test challenge and nothing occurs:

```text
DO NOT ASSUME OPEN-MMI COMPLIANCE
```

I would label it:

```text
UNVERIFIED / presumed non-compliant
```

rather than mathematically “failed.”

A gateway, wiring fault, adapter problem or unsupported vehicle route could also prevent delivery.

But critically:

> absence of evidence does not inherit Open-MMI's reputation.

The SI has to demonstrate compliance.

---

# 21. Fresh installation and update continuity are different problems

Your V1→V10 scenario requires two kinds of trust.

### Existing installation

V1 can protect:

```text
V1 → V2 → ... → V10
```

because each existing version judges its successor.

### Wiped installation

After the machine is erased, V1 no longer exists locally.

Therefore V10 needs independently verifiable lineage evidence.

Eventually:

```text
V1 trust-root digest
      ↓
authorized transition
      ↓
authorized transition
      ↓
...
      ↓
V10 artifact
```

That chain can be verified externally before installing V10.

This is where the future separate Trust Checker repository becomes valuable.

---

# 22. The external Trust Checker should not define the policy

I'd eventually create a second repository containing:

```text
Open-MMI Trust specification
reference verifier
test vectors
known schema versions
release trust-chain verification
optional bootable verifier
```

But Open-MMI itself should remain capable of enforcing its accepted state.

The external project verifies Open-MMI.

It does not replace the embedded guard.

That covers locked bootloaders while still allowing independent review.

---

# 23. Hardware attestation is useful but optional

A TPM or measured-boot environment could later make SI tampering significantly harder to disguise.

But Open-MMI should not require TPM hardware for the philosophy to work.

Assurance can have levels.

For example:

```text
Open-MMI Trust compliance:
PASS

Software integrity:
verified

Boot integrity:
not hardware-attested
```

versus:

```text
Open-MMI Trust compliance:
PASS

Software integrity:
verified

Boot integrity:
TPM/measured
```

Being honest about assurance strength is better than pretending every platform can provide the same proof.

---

# 24. Supply-chain reproducibility eventually matters

The current Python dependencies use version ranges:

```text
python-can>=4.3,<5
evdev>=1.6,<2
```

CI uses moving GitHub Action major references.

Fresh installation also installs/upgrades dependencies through package repositories.

That's entirely normal for the current project.

It is not enough for the ultimate:

> I independently reviewed V1 and can re-establish confidence in V10.

Before making that promise, Open-MMI releases should eventually carry things such as:

```text
artifact digest
dependency locks/hashes
SBOM
pinned build actions
signed release metadata
known builder provenance
```

Potentially reproducible-build evidence too.

That is a later supply-chain phase, not something Telemetry Guard needs to wait for.

---

# 25. Recommended implementation sequence

I would now sequence Nightly like this:

1. **Trust preflight**

   * vendor Bootstrap/Icons locally;
   * close obvious undeclared runtime network dependencies;
   * clean up relevant trust/privacy documentation inconsistencies.

2. **Trust Manifest v1**

   * strict JSON schema;
   * canonical capability vocabulary;
   * deterministic manifest digest;
   * parser/validator;
   * packaging support;
   * CI contracts;
   * documentation clearly states this is the beginning of trust architecture, not yet full update continuity.

3. **Telemetry Guard**

   * default deny;
   * local VIN-bound authorization;
   * no remote VIN service;
   * collection-scope declaration;
   * scope change invalidates authorization;
   * raw VIN not duplicated unnecessarily;
   * telemetry blocked before collection.

4. **Trust Inspector v1**

   * inspect manifest;
   * inspect telemetry state;
   * inspect current CAN implementation state;
   * inspect declared network capabilities;
   * produce human-readable local evidence.

5. **Capability enforcement**

   * improve CAN receive-only isolation;
   * funnel external network egress;
   * protect persistent vehicle-data purposes;
   * strengthen process sandboxing.

6. **Trust-aware updater**

   * candidate manifest treated purely as data;
   * compare old accepted state against candidate;
   * block boundary expansions;
   * acknowledgement performed by old trusted code;
   * record transitions;
   * stop executing candidate-provided privileged installer logic before acceptance.

7. **Trust Inspection transport**

   * CAN challenge;
   * visible challenge nonce;
   * fail/unverified semantics;
   * no Open-MMI CAN transmission.

8. **Independent verification**

   * separate verifier repository;
   * release lineage;
   * SI compliance mode;
   * official provenance mode;
   * optional bootable verifier.

9. **Hardware-backed evidence**

   * TPM/measured boot where available;
   * never mandatory for baseline Open-MMI functionality.

10. **Trust-continuity release**

    * only at this point make the strong public promise that an owner can establish a trust anchor in an earlier release and mechanically verify continuity into later generations.

---

# 26. What I would NOT do

I would not make Telemetry Guard the root architecture.

I would not let every subsystem invent its own consent storage.

I would not let candidate releases define owner authorization.

I would not equate a Git signature with permission.

I would not call a release compliant simply because its own UI says PASS.

I would not design SI compliance around official file hashes alone.

I would not make Open-MMI transmit a response onto the vehicle CAN bus merely for Trust Test.

I would not try to prevent root-owning SIs from modifying their own systems.

Instead:

> modification is allowed; silently inheriting Open-MMI's trust reputation after violating the contract is not.

---

# 27. The key invariant

Everything ultimately reduces to one rule:

> **An already trusted Open-MMI installation may automatically accept software that preserves or narrows its established trust boundary. Expansion requires an owner-visible transition authorized by the already-trusted side of that boundary.**

And the corresponding SI rule is:

> **An installation receives Open-MMI's trust reputation only to the extent that it can demonstrate compliance with the Open-MMI trust contract.**

That is technically viable with the current architecture.

It is also much stronger than simply adding a privacy policy or certification badge.

The current codebase already contains several of the right engineering instincts. The work ahead is mostly about turning those isolated patterns into a universal contract that even future Open-MMI itself has to obey.

````

 what do you think based on current nightly