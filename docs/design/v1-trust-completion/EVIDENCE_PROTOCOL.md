# Evidence, status and completion protocol

## Evidence is scoped

Every result must record:

- Evidence ID, command/test or manual procedure ID.
- Subject commit and source projection/artifact digest; working-tree results also record the actual patch/preimage identity.
- Machine role: DEV MACHINE, TABLET, isolated VM/bench, CI, assistant-workspace, or independent verifier host.
- Environment details that matter: Python path/version, kernel, systemd, iproute2/can-utils, architecture, relevant adapter/driver.
- Result: passed, failed, blocked, not_run, unverified, or not_applicable.
- Evidence level: source-reviewed, unit-tested, protocol-tested, installed-integration, systemd-verified, synthetic-CAN, vehicle-qualified, externally-verified, or maintainer-reported.
- Time/boot/namespace identity where runtime freshness matters.
- Command exit status, observed output summary, full log/report path or CI URL, and its SHA-256 when a local file is retained.
- Test counts and skipped cases; explain skipped/environment-blocked scope.
- Redaction note and open blockers.

Do not include raw VIN, credentials, tokens, signing secret keys or unrelated home-directory contents. Use synthetic fixtures. A sanitized excerpt is not the complete result unless the record says so.

## Status dimensions

Code status and boundary status are independent.

Code status values: planned, in_progress, patch_ready, applied, validated, committed, complete, blocked, superseded.

Boundary status values: pending, in_progress, awaiting_evidence, complete, blocked, superseded.

Gate/criterion values: not_run, passed, failed, blocked, unverified, not_applicable.

A code change can be tested/committed while its installed or vehicle boundary is awaiting evidence. "Ready for maintainer review" and "complete" are different states.

## Definition of code completion

For a card:

1. All specified behavior and negative cases are implemented or explicitly resolved through a reviewed card revision.
2. Relevant focused tests pass; required full/CI/package/browser gates are satisfied on that code subject.
3. No pre-existing unrelated work was discarded, included accidentally or claimed tested as part of this patch.
4. Patch identity/preimages and exact application commands are recorded.
5. The maintainer's signed commit and CI subject are recorded when those steps occur. A patch-ready agent must not invent the future commit.
6. Every acceptance criterion links to evidence and the reviewer records why it is satisfied.

For code-only completion while hardware is pending, keep code_status=committed or validated and boundary_status=awaiting_evidence. This pack reserves code_status=complete for a card whose acceptance and closure gates are satisfied; do not misread that as preventing development of an explicitly approved independent task.

## Definition of boundary completion

Every acceptance criterion is satisfied, required gates passed on applicable subjects, required review performed, and no unresolved contradiction or required evidence gap remains.

A checksum, JSON validator or green CI cannot certify truth of hardware observations or semantic security. The handoff validator checks structure and missing records, not whether an agent's claims are true.

## Evidence reuse and invalidation

Retain valid evidence. Explain reuse by scope:

- Pure handoff/evidence documentation changes do not automatically invalidate already-tested runtime bytes.
- Changed source, packages, effective units, dependency/toolchain versions, install metadata or runtime topology may invalidate affected tests.
- New boot/namespace identity invalidates a "currently live" observation even if unit tests remain valid.
- Changes to protected core, update order or recovery require the corresponding adversarial/recovery gates.
- A merge with identical runtime inventory may reuse some code evidence; nightly CI and required integration hardware checks still follow release policy.

Record reused_from and a concrete no-impact rationale. Never overwrite an older failed result with a later passed label; append the new result and retain the failure/fix relationship.

## Durable records and self-reference

progress.json is the task ledger. evidence-records.json is an append-only working evidence index. HANDOFF_LATEST.md is the human continuation note. Update and export these at the rolling checkpoints defined in [CHECKPOINTING.md](CHECKPOINTING.md), including failed or interrupted work; do not defer all handoff maintenance to the end of a chat. Commit cards and manifest.json define intent; change them only with a recorded reason.

Do not write a commit's own future SHA into a file inside that commit. Record:

- subject_code_commit: the code that was tested;
- recorded_commit: the later commit containing evidence, filled in by a subsequent handoff when known;
- tested_source_projection: a digest of code/test inputs excluding this handoff directory.

A documentation-only recording commit does not require pretending the runtime was retested under an impossible self-referencing SHA.

GitHub/committed repo records are durable once the maintainer signs and pushes. Until then, always deliver the latest patch and handoff snapshot for download; an assistant workspace alone is not durable continuity.

## Minimal evidence record

~~~json
{
  "id": "E-P01-001",
  "subject_commit": "REPLACE_WITH_ACTUAL_40_HEX_SHA",
  "source_projection_sha256": "sha256:REPLACE_WITH_ACTUAL_DIGEST",
  "machine_role": "dev",
  "level": "protocol-tested",
  "result": "passed",
  "command": ".venv/bin/python3 -m unittest tests.test_trust_status_coordinator tests.test_web_dashboard_trust_status",
  "exit_code": 0,
  "log_path_or_url": "REPLACE_WITH_RETAINED_LOG_OR_CI_URL",
  "log_sha256": "sha256:REPLACE_WITH_ACTUAL_LOG_DIGEST",
  "observed": "Record actual counts and behavior; do not copy planned expectations.",
  "invalidates": [],
  "reused_from": null,
  "limitations": []
}
~~~

This is a schema example, not an existing test result. Remove all placeholders before using it as completion evidence.
