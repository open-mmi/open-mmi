# Prompt for the next chat

Copy the block below into a new chat. Attach the selected commit card, current operating brief, progress.json, HANDOFF_LATEST.md, relevant evidence and latest patch if uncommitted. The full master manifest/zip is available when a broader decision is needed.

~~~text
You are continuing Open MMI owner trust work. Read the attached OPERATING_BRIEF.md first, then CURRENT_STATE.md, progress.json, HANDOFF_LATEST.md and the selected commit card.

Repository: github.com/open-mmi/open-mmi.
DEV MACHINE checkout: ~/github/open-mmi.
TABLET checkout: ~/open-mmi; installed runtime: /opt/open-mmi.
Use python3, preferably .venv/bin/python3 for project tests.
Starting feature: owner-trust-controls-ui-v1, assessed baseline 6b0de79968a5cfb72773989db4c72989204e3cb6. Inspect actual state; do not assume the baseline is still HEAD.
C6 is complete. C7.4 exists. Do not reimplement either.
The TABLET is reported beta until a deliberate recorded qualification migration.

Task: implement exactly the selected card and required local verification. Produce a downloadable patch, metadata with actual base/preimage/patch digests, exact DEV MACHINE commands using ~/Downloads, and updated handoff records.
Do not commit, push, merge, publish, run sudo git, switch the tablet, install, reboot or mutate trust without the maintainer explicitly reaching that action.
Do not reapply an existing patch or discard uncommitted work.
Do not repeat already-valid baseline tests unless the change invalidates them.
Preserve root+TTY trust mutation, read-only browser trust UI, ACK-capable private CAN with dual DROP and a one-way gateway.

First report:
1. Actual machine/workspace role, branch/HEAD and dirty state.
2. Which prerequisites/evidence remain valid.
3. Exact card and acceptance criteria you will address.
4. Any concrete mismatch that changes this task.

If a required file is absent, search the current repo for its actual replacement. Proposed filenames in the card are proposals, not claims that they exist.
If blocked, deliver the current diff/patch and an exact handoff describing the blocker and next smallest action. Do not end with only "continue next time".
~~~

## Stop/resume contract

Before ending any implementation chat, update:

- Exact actual base/current commit and working-tree state.
- Card ID, code status, boundary status, last completed criterion and next incomplete criterion.
- Patch filename/revision/SHA-256, prerequisite patch IDs and changed-file pre/post hashes.
- Commands already run, actual results, preserved evidence and required tests not run.
- Files touched and decisions made; which decisions require maintainer review.
- DEV versus TABLET state separately, including installed metadata if observed.
- Known failure/recovery state, unresolved questions and next exact action.

The receiving agent starts from those records. It does not reconstruct progress from optimistic prose or rerun the entire project to orient itself.
