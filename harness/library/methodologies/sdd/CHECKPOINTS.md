# CHECKPOINTS — definition of "correct final state"

> The reviewer walks every box, marks `[x]`/`[ ]`, and rejects if any applicable box is
> empty. Per-feature-type specifics come from `.harness/profile.yaml` `gate_profiles`.

## C1 — Harness state is coherent
- [ ] At most one feature in `in_progress`|`in_review` in feature_list.json.
- [ ] The worked feature's status matches reality.
- [ ] progress/current.md describes the active session (no stale content).

## C2 — Constitution honored (always; see profile.yaml `constitution`)
- [ ] Every constitution rule verified. Mechanical ones evaluated as a **delta**:
      red both before AND after the change ⇒ pre-existing ⇒ flag, don't block.

## C3 — Spec ↔ evidence traceability
- [ ] Every `R<n>` covered by ≥1 concrete test/evidence (kind depends on feature `type`).
- [ ] All tasks in tasks.md are `[x]` (or justified in progress/impl_<feature>.md).
- [ ] No `[NEEDS CLARIFICATION]` markers remain in the spec — they must be resolved at
      approval, never carried into implementation (a survivor means the human gate was skipped).

## C4 — Verification is real
- [ ] `verify.command` (profile) is green where applicable.
- [ ] No placeholders (`TODO`/`FIXME`/`pass`/`...`/`NotImplementedError`) in changed source.
- [ ] No human gate (e.g. visual inspection) self-approved by an agent.
