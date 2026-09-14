# Patch-first delivery and application

## What an implementing agent must deliver

For each coherent card/revision:

1. One downloadable patch, named open-mmi-P01-short-topic-ACTUALBASE12-r1.patch using the actual card/base/revision.
2. A matching metadata JSON with exact patch SHA-256, base commit, branch, prerequisite patch IDs/revisions, source projection, all changed paths and per-file pre/post SHA-256/type/mode (null means absent).
3. Updated progress.json, evidence-records.json and HANDOFF_LATEST.md included in the patch where practical, plus a standalone copy of the continuation note for the next chat.
4. Exact DEV MACHINE application/test commands referencing the downloaded filename in ~/Downloads.
5. Tests actually run and their environment, failures/skips, required tests not run, and a short rationale for the boundary criteria.
6. A suggested signed commit subject and exact file list, clearly separated from the apply/test phase. Do not commit/push automatically.

The patch must include newly created files and deletions, not merely tracked-file edits. Agent-side generation may use a temporary index or before/after snapshot inside the assistant's isolated checkout. Do not stage the maintainer's unrelated DEV work or create a commit solely to generate a patch.

Validate application on a disposable copy of the exact supplied base plus any prerequisite patch preimages. Compare resulting postimages and run git diff --check. Do not rely on a patch applying to the agent's already-edited tree.

## Deliver recovery material while work is in progress

Follow [CHECKPOINTING.md](CHECKPOINTING.md) from the first edit onward. Export unfinished source, handoff records and evidence during normal work so a sudden chat cutoff does not require a final response.

A recovery bundle contains a cumulative patch against its declared signed base, or every required uncommitted patch in a complete ordered chain. Include new files and deletions. Mark unfinished code and pending tests accurately; a checkpoint is not a completed card or a new Git commit.

Provide a separate incremental application patch only when its preimages match the last confirmed DEV state. A newer cumulative snapshot must not be applied blindly over an older applied snapshot. Inspect actual files first if application is uncertain.

Keep patch checksums in metadata outside the files modified by that patch. Store the full-bundle checksum in the delivery receipt rather than inside the bundle itself. Confirm that a saved artifact is accessible outside the temporary session before calling the checkpoint durable.

## DEV MACHINE: inspect actual state first

~~~bash
cd ~/github/open-mmi
git status --short
git branch --show-current
git rev-parse HEAD
git diff --check
~~~

The agent must supply the exact expected base/branch and explain any prerequisite uncommitted patch stack. Do not assume a clean state from a prompt symbol. No automatic git reset, git clean, stash, checkout, ownership repair or sudo git.

If the base differs, do not reset to make it match. Inspect current diffs, compare the actual changed-file preimages and regenerate/rebase the patch deliberately. Preserve unrelated local work. Future commit hashes in the plan are intentionally unspecified.

## DEV MACHINE: inspect and check the downloaded patch

The following is an example for P01. An agent must replace the filename and all metadata values with the actual delivered artifact before giving copy/paste instructions.

~~~bash
cd ~/github/open-mmi
patch_file="$HOME/Downloads/open-mmi-P01-status-coordinator-ACTUALBASE12-r1.patch"
sha256sum "$patch_file"
git apply --stat "$patch_file"
git apply --summary "$patch_file"
git apply --check "$patch_file"
~~~

Compare the printed SHA-256 with the independently delivered expected value and metadata before applying. Filename similarity is not identity.

Decision table:

| Observation | Action |
| --- | --- |
| Forward check passes; expected preimages/base match | Apply once, then verify postimages |
| Reverse check passes and all expected postimages match | Patch is already present; do not reapply |
| Some postimages match and others do not | Partial or overlapping work; inspect and request a correctly based revision |
| Neither forward nor reverse check passes | Base/context conflict; inspect, preserve work, regenerate |
| Unrelated local changes exist | Keep them; isolate the patch scope and state exactly what was tested |

For diagnosis only:

~~~bash
cd ~/github/open-mmi
git apply --reverse --check "$patch_file"
~~~

This is a check, not an instruction to undo the patch. Never automatically run git apply --reverse, --reject, --unsafe-paths or --3way to force a result.

## DEV MACHINE: apply only after successful review/check

~~~bash
cd ~/github/open-mmi
if git apply --check "$patch_file"; then
    git apply "$patch_file" && git diff --check
else
    printf '%s\n' 'Patch did not pass the check. Preserve the current tree and inspect the mismatch.'
fi
git status --short
git diff --stat
~~~

The conditional block prevents application after a failed forward check. It does not replace the preceding base/preimage/duplicate review.

Run the exact card's tests using python3/.venv/bin/python3, retain results, and compare changed-file postimages to metadata. A clean diff check is not a unit/integration test.

A failed test leads to a scoped revision patch based on the actual current tree. Do not send the entire earlier patch again unless clearly labeled as a replacement for an unapplied artifact.

## DEV MACHINE: signing is a separate maintainer step

Only when the maintainer explicitly reaches commit:

~~~text
cd ~/github/open-mmi
git diff --check
git diff -- <the exact reviewed changed paths>
git add -- <the exact reviewed changed paths>
git diff --cached --check
git diff --cached --stat
git commit -S -m "<the reviewed card subject>"
git rev-parse HEAD
git log -1 --format='%H %G? %s'
~~~

These are templates, not runnable placeholders. The agent must provide the real paths/subject. Do not use blanket git add -A or include unrelated work. Use no sudo.

Push, PR creation and merge are subsequent explicit maintainer actions. After they occur, record the real commit and exact CI URL. GPG success depends on the maintainer's configured key; never disable signing to bypass a failure.

## TABLET: source transfer and deployment are different actions

After a signed/pushed source change and explicit qualification decision, the maintainer can choose how the TABLET's ~/open-mmi obtains the exact commit through the documented branch workflow. Do not apply DEV-machine paths on TABLET.

Do not run git as root. Privileged installation/trust commands are separate, narrowly scoped administrator actions from the correct TABLET checkout/installed tools. Applying a patch on DEV does not install it on TABLET.

The TABLET stays beta until deliberately moved. A legacy beta-to-feature deployment is new-baseline migration. A future managed update uses the established gate; no forced bypass or invented continuity claim.

## Bootstrap patch supplied with this pack

The actual bootstrap patch is open-mmi-trust-handoff-6b0de79968a5-r1.patch. It adds only docs/design/v1-trust-completion/, including planning records and read-only helper tests. It does not fix P01 or implement any production card.

The master download and ZIP DOWNLOADS_README.md contain its exact SHA-256 and ready-to-run DEV commands. This file deliberately does not embed its own containing patch hash, avoiding a circular checksum.

## Ongoing and final delivery checkpoints

Keep this delivery current throughout work under CHECKPOINTING.md; an abrupt cutoff may prevent any final response.

Never leave only prose such as "done" or "continue next time". Return the patch, actual base/digests, exact apply commands, verification summary, updated ledger and the next smallest unfinished criterion. If only analysis/design was completed, mark it accordingly and retain the reviewed decisions instead of manufacturing a runtime patch.
