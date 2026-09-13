# Open MMI trust completion — resumable implementation pack

Assessed feature: owner-trust-controls-ui-v1 at 6b0de79968a5cfb72773989db4c72989204e3cb6.

This is a detailed execution manifest for one maintainer working with interchangeable coding agents. It contains **25 proposed commit boundaries**, acceptance criteria, exact existing source read sets, negative tests, qualification gates, patch rules and durable continuation records. It does not implement those runtime changes.

**Plan IDs are P01–P25. Historical milestones remain C6/C7.** P06 is not C6, and completing a code patch is not hardware qualification.

## Choose the next bounded task

| Scope | Cards | Meaning |
| --- | --- | --- |
| Immediate owner UI milestone | P01–P07 | Complete C7 status, guidance and setup; close the independent CAN evidence gap |
| Separate confinement boundaries | P08–P09 | Remote identity and effective network/persistence behavior |
| Stronger future update continuity | P10–P16 | Protected trust core, old-owned deployment and durable recovery |
| Independent verification | P17–P19 | External anchors/owner witnesses, compliance and fresh challenge |
| Supply chain and release | P20–P25 | Locked inputs, metadata, adversarial integration and qualified promotion |

The count is an estimate, not a target to manufacture commits. Preserve the boundaries if evidence allows a card to be skipped or implementation requires a reviewed split. The bootstrap plan patch is additional documentation and is not P01.

The next target action is **G0 qualification planning for the existing CAN-isolation commit**. The TABLET remains beta until the maintainer deliberately changes that. Independently, P01 can be prepared on DEV.

## Minimum next-chat packet

Give the next agent:

1. [OPERATING_BRIEF.md](OPERATING_BRIEF.md).
2. [CURRENT_STATE.md](CURRENT_STATE.md), [progress.json](progress.json) and [HANDOFF_LATEST.md](HANDOFF_LATEST.md).
3. One selected card from [INDEX.md](INDEX.md).
4. Relevant evidence IDs/logs and the latest unapplied/uncommitted patches with metadata.
5. The task text in [RESUME_PROMPT.md](RESUME_PROMPT.md).

The agent reads the card's existing source paths, implements that boundary, tests it, and returns a patch plus updated records. The master document and original attachments are reference material; they need not be reread for every small implementation.

## Authoritative records

| File | Purpose | Edit rule |
| --- | --- | --- |
| manifest.json | Card scope, source paths, criteria, dependencies, gate checks and test groups | Canonical; record why scope changes |
| commits/*.md and INDEX.md | Readable cards/index | Generated from manifest; use the renderer |
| progress.json | Code/boundary/criterion/gate state | Update with actual progress; preserve IDs |
| evidence-records.json | Retained evidence index | Append new records; preserve failed/blocked history |
| HANDOFF_LATEST.md | Human stop/resume context | Update at every pause |
| GATES.md and GATE_CHECKLIST.md | Procedures and canonical required gate IDs | Keep procedures aligned with manifest |
| TEST_MATRIX.md | Existing executable test groups and future required outcomes | Record new exact commands once tools exist |
| PATCH_WORKFLOW.md | Patch metadata, application, duplicate/conflict and signing rules | Apply for every delivery |
| GOAL_COVERAGE.md | Original goal mapping and explicit limits | Do not quietly remove a required claim |
| source-notes/ | Unchanged historical source attachments | Historical reference, not current execution authority |

Read-only helper commands on DEV:

~~~bash
cd ~/github/open-mmi
python3 docs/design/v1-trust-completion/helpers/check_handoff.py
python3 docs/design/v1-trust-completion/helpers/render_manifest.py --check
python3 -m unittest discover -s docs/design/v1-trust-completion/helpers -p 'test_*.py'
python3 docs/design/v1-trust-completion/helpers/capture_state.py --repo . --machine dev
~~~

The last command prints JSON; copy it into the evidence retained for the next handoff. It reads Git/source identity and does not run tests, deploy, change Git or inspect installed TABLET state. Its source projection excludes this handoff directory to avoid self-referential evidence hashes. It is not runtime attestation.

After intentionally changing the canonical manifest:

~~~bash
cd ~/github/open-mmi
python3 docs/design/v1-trust-completion/helpers/render_manifest.py
python3 docs/design/v1-trust-completion/helpers/check_handoff.py
~~~

The renderer writes only generated handoff cards/index/checklist. The checker validates record structure and rejects missing closure evidence; it cannot authenticate a human observation or prove security semantics.

The optional --repo argument on check_handoff.py checks whether the current-source read paths exist. Use it against the pinned baseline during initial review. After a deliberate source move, revise the manifest paths with the reason; do not delete a gate to silence an error.

## Updating the ledger

- Select active_card and record the actual base commit when beginning.
- Use code_status=patch_ready/applied/validated/committed as those steps actually happen.
- Keep boundary_status=awaiting_evidence when source is ready but runtime/vehicle evidence is pending.
- Attach criterion evidence by stable ID, such as P01-A01 -> E-P01-001.
- A completed boundary requires actual subject_code_commit, tested_source_projection, all criteria, required gate checks and a named accepted review.
- Do not invent a future signed SHA. Record the code subject first; a later recording commit can contain its result.
- Gates have a separate subject_commit and per-check status/evidence. Evidence must match the required machine, level and subject.
- Reusing unchanged evidence requires reuse_approved_for, reuse_rationale and reuse_reviewed_by, plus the original retained record. Prefer a new referencing record rather than rewriting the original.
- A blocked/not_run/unverified result cannot be counted as passed. The baseline report is retained without pretending G0 or G1 happened.

## Delivery and stop rule

Follow PATCH_WORKFLOW.md. Return the actual patch, metadata, exact commands using ~/Downloads, verification summary and next smallest unfinished criterion. Preserve the maintainer's unrelated work.

Do not run privileged Git, commit, push, merge, deploy, reboot, switch beta or mutate trust merely because this plan mentions a future step. The maintainer makes those concrete decisions. Already-authorized bounded source preparation and testing should continue without repeated permission prompts.
