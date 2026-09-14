# Rolling checkpoints and recovery after a chat cutoff

A chat may stop before an agent can send a final handoff. Maintain recoverable state during the work. The user must be able to move to another chat using a checkpoint already saved outside the closing session.

This is a work protocol, not an automatic chat-limit hook. Agents cannot guarantee a final turn or reliable notice of a context limit. A cutoff can lose changes or reasoning that were never saved; make the unfinished interval small.

## Agent checkpoint schedule

1. At session start, reconcile the selected card, exact signed base, supplied DEV snapshot and any existing patches. Save checkpoint K0000 before implementation edits. It may contain no new code.
2. After each coherent edit/test batch, update HANDOFF_LATEST.md, the relevant progress.json fields and evidence-records.json, then publish the next checkpoint. Do this even when tests fail or work is incomplete.
3. Before a long test, a large source/context read, a major approach change, or a deliberately authorized target operation, checkpoint first. Record the pending command/action and its evidence destination. Checkpoint the actual outcome afterward when available.
4. Avoid more than two edit/test cycles or roughly 15 minutes of active work between published checkpoints. At that point, checkpoint as the next action before starting another work batch. This is an operating target, not a guarantee that a long-running action cannot be interrupted.
5. Finish a card with its normal reviewed patch/evidence delivery. Prefer a new chat for the next card; a large card can span multiple chats through its checkpoints.

Do not wait for the user to request a handoff, for a low-context warning, or for the final response. A checkpoint is part of normal implementation, not a separate permission request. Existing authorization rules still govern commits, pushes, installations and trust mutation.

## Records to keep current

At every checkpoint, record:

- Stable checkpoint ID, for example P01-K0001; previous checkpoint ID; selected card and criteria in progress.
- Exact base commit, observed branch, machine/workspace role, source identity and last confirmed DEV state. Keep home paths portable with ~.
- Completed work, unfinished work and the next smallest concrete action. Separate implementation state from boundary/qualification state.
- Changed tracked files, new untracked source files and deletions. A plain git diff can omit new files; include them explicitly in recovery material.
- Tests actually run with retained results, failed/skipped/blocked cases, and valid evidence reused. Record a test still in progress as pending/unknown, never as passed.
- Decisions and reasons, alternatives rejected, unresolved questions and any required owner review.
- Which patches were only generated, saved, downloaded, applied, committed or pushed. Use only observed/reported states; these events are different.
- For a target operation, the latest observed installed identity and outcome, separately from DEV source state.

Keep the human continuation note short enough to read first. Attach or retain larger logs and refer to their evidence IDs. A new agent should inspect the selected card and relevant progress/dependency/gate records before loading the entire manifest or unrelated source.

Use the existing progress status values. Do not invent code_status=checkpointed or mark a boundary complete merely because a recovery bundle exists.

## What a recoverable checkpoint contains

Deliver one versioned bundle, for example open-mmi-P01-K0001-ACTUALBASE12.zip, using the real card, sequence and base. The name is a template until the agent supplies actual values.

| Item | Required content |
| --- | --- |
| checkpoint.json | Checkpoint/card IDs; exact base; machine roles; last confirmed DEV state; patch filenames/digests; file pre/post hashes/types/modes; validation state; pending actions; next step |
| HANDOFF_LATEST.md | The current compact continuation note, including decisions and unfinished criteria |
| progress.json and evidence-records.json | Current records, preserving failed and blocked evidence |
| Selected card and operating instructions | Current card, OPERATING_BRIEF.md, RESUME_PROMPT.md and this protocol, or an exact accessible repository version containing them |
| Recovery patch | All task changes since the declared signed base, including new files and deletions, sufficient to reconstruct the checkpoint in an isolated checkout |
| Evidence | Relevant logs/reports, or durable accessible URLs plus digests where appropriate |
| Application patch, when appropriate | A separately identified incremental patch for the last confirmed DEV preimages, with exact application/test commands |

If no implementation changes exist yet, explicitly record that and set the recovery patch to null. An analysis-only checkpoint still saves decisions and the next step. Do not manufacture code changes or claim tests ran.

An unfinished recovery patch may contain failing or incomplete implementation. Mark it as in progress and not ready for DEV application. It preserves work for the next agent; it is not permission to install or declare the card complete.

Build patch bytes first, then write their hashes into the bundle's separate checkpoint.json. Do not embed a patch's own checksum into a file that the same patch modifies. Keep the full-bundle checksum in the delivery message or a separate receipt to avoid the same self-reference problem.

Include only relevant project material. Do not bundle credentials, private keys, raw vehicle identity or unrelated home-directory files.

## Saved means recoverable outside this chat

A progress paragraph or a file that exists only in a temporary assistant workspace is not a durable checkpoint.

- If the agent works directly in the actual DEV checkout, source edits and handoff files on that machine survive the chat. Record what remains uncommitted; do not silently equate it with the GitHub branch.
- If the agent works in a separate assistant workspace, save the recovery bundle through the environment's supported persistent artifact mechanism and provide a working download link. Otherwise provide the bundle for the maintainer to download to ~/Downloads and keep its status as awaiting download until that is confirmed.
- Do not label a persistent save successful before its result is known. If persistence fails, preserve the last verified checkpoint and report the exact failure and unsaved interval.
- Do not continue another substantial implementation batch while the only checkpoint is trapped in a transient workspace. Resolve the export/save problem first, or leave a clear blocked checkpoint.

The maintainer should retain the newest bundle and at least one previous known-good bundle. A saved/downloaded checkpoint needs no Git commit merely to exist. It also does not authorize an agent to create a checkpoint branch, push, or publish files.

The next chat needs the bundle attached or otherwise made explicitly accessible. Do not assume a new agent can see another chat's private files or remembered conversation.

## Cumulative recovery versus incremental application

Each recovery bundle must be self-contained relative to its declared signed base. Prefer one cumulative recovery patch. If a patch chain is unavoidable, include every uncommitted prerequisite with its exact order and digests; do not refer to a missing prior chat attachment.

A newer cumulative recovery patch replaces the older recovery snapshot. It is not automatically an additional patch to apply over an earlier applied checkpoint.

| Actual DEV state | Correct next action |
| --- | --- |
| Still at the declared base/preimages | A reviewed applicable patch may be checked and applied once |
| Earlier checkpoint already applied | Use an incremental patch built against those confirmed postimages, or reconstruct the newer checkpoint in an isolated workspace for comparison |
| Latest expected postimages already present | Record it as applied; do not apply it again |
| Partial/overlapping or newer local work | Preserve it, compare exact files and regenerate an appropriate incremental patch |
| Earlier application outcome unknown | Inspect actual files/status before deciding; do not assume download meant application |

Never reset, clean, reverse-apply or discard DEV changes simply to make a cumulative patch fit. PATCH_WORKFLOW.md still governs every application.

## If the chat is cut off

The maintainer does not need a final message from the old agent:

1. Open a new chat and supply the most recent saved recovery bundle plus RESUME_PROMPT.md, identifying the selected card/checkpoint.
2. Supply a fresh DEV capture using the existing read-only command below. It records identity/status, not the contents of uncommitted changes; retain those through the bundle or actual DEV checkout.
3. The new agent verifies the bundle, restores the exact declared base plus recovery material in its own isolated workspace when necessary, and reconciles actual DEV changes without discarding them.
4. Continue the next unfinished criterion. Reuse valid recorded tests. Treat unfinished tests or unobserved commands as unknown; inspect retained logs/process/target state before deciding what must be rerun.
5. If the interruption happened during a TABLET operation, inspect current runtime state first. Never repeat an install, reboot or trust mutation just because the previous chat ended.

DEV MACHINE:

~~~bash
cd ~/github/open-mmi
python3 docs/design/v1-trust-completion/helpers/capture_state.py \
    --repo . \
    --machine dev \
    > "$HOME/Downloads/open-mmi-resume-state.json"
~~~

Attach that JSON alongside the checkpoint. Preserve ~/github/open-mmi for DEV and ~/open-mmi for TABLET. Assistant recovery workspaces are not substitute user-machine paths.

If no interim bundle was ever saved, recover from the latest accessible signed commit, downloaded patches and actual DEV files. Be explicit that agent-only work after that point may be lost; do not invent a reconstructed test result or decision.
