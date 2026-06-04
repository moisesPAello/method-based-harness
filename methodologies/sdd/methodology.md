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
| pending | spec_author | feature_list, repo docs | `specs/<f>/{requirements,design,tasks}.md` | **spec_complete** → spec_ready, then HALT |
| spec_ready | human | the 3 spec files | — | **human_approved** → in_progress |
| in_progress | implementer | spec, source | code, tests/evidence, `progress/impl_<f>.md` | **impl_complete** (per type) → in_review |
| in_review | reviewer *(fresh context)* | spec, impl report, code, CHECKPOINTS | `progress/review_<f>.md` | **review_passed** (per type) → done · reject → in_progress |

## Gate classes
- **mechanical** — a command returns pass/fail; un-skippable. The command MUST exist (probe it).
- **human** — a person says "approved" / confirms an artifact. The deliberate halt(s).
- **judgment** — a role assesses; only as hard as the reviewer is independent (fresh context).

## Generic gates (the profile fills specifics)
- **spec_complete** (mechanical): the 3 spec files exist; requirements in EARS with
  stable `R<n>` ids; every `T<n>` cites ≥1 `R<n>`; every acceptance item maps to ≥1 `R<n>`.
- **human_approved** (human): the human writes "approved" for the feature.
- **impl_complete** → `profile.gate_profiles[type].impl_complete`.
- **review_passed** → `profile.gate_profiles[type].review_passed`.
- **constitution** (always-on, from profile): checked at every gate.

## EARS — requirements.md
One numbered `R<n>` each, one pattern: Ubiquitous `The system SHALL …`; Event
`WHEN … the system SHALL …`; State `WHILE … the system SHALL …`; Optional
`WHERE … the system SHALL …`; Unwanted `IF … THEN the system SHALL …`. One `SHALL`
per requirement; each verifiable by ≥1 concrete evidence (the *kind* depends on the
feature `type`); no soft verbs.

## tasks.md
Ordered `[ ] T<n> — <step>. Covers: R<a>, R<b>.` The implementer marks `[x]`; the
reviewer rejects any `[ ]` without a documented justification.

---
*Proven: this declaration drove `banregio_promote` end-to-end on sella-cruce
(2026-06-04). See `../../docs/findings.md`.*
