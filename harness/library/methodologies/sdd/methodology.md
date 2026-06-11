# Methodology: Spec-Driven Development (SDD)

> STRUCTURE, not a tutorial. Defines the states an item moves through, the artifact
> each phase produces, and the HARD gate on each transition. Roles read it to know
> what they must produce and what blocks them — never as background on "what SDD is".
> Project-specific values (verify command, constitution, per-type gate profiles)
> live in the **project profile**; this file stays project-agnostic.

## Shape
Linear: one human-approval gate up front, then forward-only, with a reject loop out
of review.

## States
`pending → spec_ready → ⏸ HUMAN → in_progress → in_review → done`  (plus `blocked`)

## Phases — driver · reads · writes · exit gate

| State | Driver | Reads | Writes | Exit gate → next |
|---|---|---|---|---|
| pending | spec_author | feature_list, repo docs | `specs/<f>/{requirements,design,tasks}.md` (gaps marked `[NEEDS CLARIFICATION]`) | **spec_complete** → spec_ready, then HALT |
| spec_ready | human | the 3 spec files | — | **human_approved** (resolves every marker) → in_progress |
| in_progress | implementer | spec, source | code, tests/evidence, `progress/impl_<f>.md` | **impl_complete** (per type) → in_review |
| in_review | reviewer *(fresh context)* | spec, impl report, code, CHECKPOINTS | `progress/review_<f>.md` | **review_passed** (per type) → done · reject → in_progress |

**Who writes the status** (`records:` in `methodology.yaml`): the spec_author sets
`spec_ready` itself; every other transition is recorded by the **orchestrator**, which
transcribes the outcome — the human's approval, the implementer's `done ->` reference,
the reviewer's `APPROVED`/`CHANGES_REQUESTED` verdict — into `feature_list.json`. The
read-only roles (human, reviewer) never touch state, and the orchestrator never decides
an outcome itself; a transition with no writer would be an unspecified manual step.

## Gate classes
- **mechanical** — a command returns pass/fail; un-skippable. The command MUST exist
  (probe it). Evaluated as a **delta, not absolute**: if it is red both *before* and
  *after* the feature (stash the changes and re-run to check), the failure is
  pre-existing and does NOT block this feature — flag it for the human, don't gate on
  it. (Without this, unrelated drift in a repo blocks every future feature.)
- **human** — a person says "approved" / confirms an artifact. The deliberate halt(s).
- **judgment** — a role assesses; only as hard as the reviewer is independent (fresh context).

## Resilience
Subagents run synchronously and may stall. There is no resume: if a driver hangs,
the orchestrator **re-dispatches a fresh one**. This is cheap precisely because every
handoff is on disk — the new agent reads the spec/progress files and continues,
losing nothing. Drivers therefore run gates in the **foreground** and never spawn a
background task to wait on a gate (there is no async completion to wait for).

## Generic gates (the profile fills specifics)
- **spec_complete** (mechanical): the 3 spec files exist; requirements in EARS with
  stable `R<n>` ids; every `T<n>` cites ≥1 `R<n>`; every acceptance item maps to ≥1 `R<n>`;
  **coverage** — every `R<n>` is addressed in `design.md` and covered by ≥1 `T<n>` (no
  orphans); **coherence** — the three files agree, nothing in design/tasks exceeds the
  requirements and no requirement is silently dropped (this is the cross-artifact
  `/analyze` pass, encoded as a gate rather than a command); every material gap is
  surfaced as a `[NEEDS CLARIFICATION]` marker, not guessed.
- **human_approved** (human): **no `[NEEDS CLARIFICATION]` markers remain** (a stray one is
  a grep-able fail — the human answered each, editing the spec) **and** the human writes
  "approved" for the feature.
- **impl_complete** → `profile.gate_profiles[type].impl_complete`.
- **review_passed** → `profile.gate_profiles[type].review_passed`.
- **constitution** (always-on, from profile): checked at every gate.

## `[NEEDS CLARIFICATION]` — surface uncertainty, don't guess
Where the feature prompt is silent on something material, the spec_author writes
`[NEEDS CLARIFICATION: <specific question>]` inline rather than inventing a plausible
answer. Reasonable defaults may be taken and recorded, but anything that would change a
requirement is marked. Markers are the structured channel that hands uncertainty to the
human: they are allowed to reach `spec_ready`, and the **human_approved** gate is hard on
them — no marker may survive into `in_progress` (a stray `[NEEDS CLARIFICATION]` is a
grep-able fail). This is SDD's equivalent of spec-kit's `/clarify` pass — encoded between
turns, not as a command.

## EARS — requirements.md
One numbered `R<n>` each, one pattern: Ubiquitous `The system SHALL …`; Event
`WHEN … the system SHALL …`; State `WHILE … the system SHALL …`; Optional
`WHERE … the system SHALL …`; Unwanted `IF … THEN the system SHALL …`. One `SHALL`
per requirement; each verifiable by ≥1 concrete evidence (the *kind* depends on the
feature `type`); no soft verbs.

## tasks.md
Ordered `[ ] T<n> — <step>. Covers: R<a>, R<b>.` The implementer marks `[x]`; the
reviewer rejects any `[ ]` without a documented justification.
