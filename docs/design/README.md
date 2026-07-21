# Design documents

Design documents describe proposed behaviour before implementation. They are grouped by the branch or milestone that owns the work so that an unmerged proposal is not mistaken for current product behaviour.

## Layout

```text
docs/design/<branch-or-milestone>/
```

Each design folder should include an index that records:

- the source branch;
- the intended merge target;
- the review status;
- the scope and non-goals;
- the implementation order;
- the qualification gates.

Individual documents should state whether they are proposed, accepted, implemented, superseded, or abandoned.

## After merge

Branch-specific design documents remain in the repository as a historical record. When a branch is merged:

1. update its design index from `Proposed` or `Accepted` to `Implemented`;
2. record the merge commit or release tag;
3. copy stable user-facing behaviour into the appropriate permanent documentation;
4. mark any deferred or changed decisions explicitly;
5. do not rewrite the original design to imply that every proposal shipped unchanged.

Current user and operator instructions belong in normal product documents such as `README.md`, `docs/getting-started.md`, `docs/vehicle-setup.md`, or `docs/manual-administration.md`. Design documents explain why a change was planned and how it was intended to work.

## Current design sets

- [`v1-vehicle-setup`](v1-vehicle-setup/README.md) — implementation complete; final tablet acceptance and release sign-off pending.
- [`v1-runtime-hardening`](v1-runtime-hardening/README.md) — implementation complete; merge qualification recorded in its close-out documents.
- [`v1-update-management`](v1-update-management/README.md) — implementation complete; confirmed manual nightly flow shipped and [device qualification](v1-update-management/qualification.md) continues as a close-out record.
