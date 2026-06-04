# Findings — learning log

## 2026-06-04 — SDD spike ran end-to-end on sella-cruce

A hand-authored SDD pack was installed into the real `sella-cruce` repo (branch
`harness/sdd-banregio`) and run from a separate Claude Code session on a Claude Pro
subscription, against a real feature: **`banregio_promote`** (promote an existing but
undocumented bank parser to supported status; feature `type: parser`).

It drove `pending → spec_ready → [human approved] → in_progress → in_review`,
producing the spec (3 EARS files, 23 requirements), an implementation report, and a
review verdict — all on disk, with one-line references between agents.

### Verified real, not prose

Each load-bearing claim was independently checked on disk:

- the export CSV exists (22 rows, correct schema);
- the cargos/abonos annotated-PDF directories exist (today's timestamps);
- the test rename is a real `git mv` (`A test_area_banregio.py` / `D test_banregio.py`);
- the constitution greps reproduce exactly (`datetime.now`=0, `import fitz`=0, `float(`=0);
- the reviewer's hardest claim — docs-sync red on a *clean* tree — reproduced by
  stashing all changes and re-running: genuinely pre-existing `web.md` drift.

### What it validated

- **type → gate-profile**: the parser spec demanded CSV / annotated-PDF / smoke-exit
  / grep evidence, explicitly *not* pytest. The spec_author understood the type.
- **on-disk handoff (anti-telephone)**: products on disk, one-line references back.
- **the second human gate held**: the reviewer *refused* to self-approve the visual
  gate (legible/non-overlapping seals), surfaced the exact PDF paths, and parked the
  feature at `in_review`. The most novel gate, and it bit.
- **independent skeptical reviewer**: re-ran every mechanical gate itself; caught a
  Spanish `"TODOS"` vs `TODO` false-positive in the placeholder grep; did
  stash-forensics on docs-sync.
- **hard gate + honest adjudication**: docs-sync caught a real red; the reviewer
  neither faked a pass nor fixed out-of-scope — it flagged it for a human.

## Findings to fold into the schema

1. **Capture `interpreter:` at init.** The repo's docs claimed a Windows venv;
   reality was "no python on PATH." The agent adapted (`.venv/bin/python`) but
   *rediscovered* it. The profile needs an `interpreter:` field set at init so gate
   commands are deterministic, not re-derived each session.

2. **Hooks enforce the constitution; drivers enforce type-gates.** The `PostToolUse`
   pytest hook fired on parser edits, but pytest doesn't collect parser tests — pure
   noise. Static host hooks can't be feature-type-aware. Rule: hooks =
   type-independent constitution (e.g. docs-sync on `Stop`); type-specific gates are
   run by the implementer/reviewer.

3. **`init` should baseline-audit the constitution.** docs-sync was red *before* the
   feature. The reviewer had to forensically prove "not my fault." If init snapshots
   known-red gates, the reviewer diffs against the baseline instead of re-deriving it
   every feature.

4. **Spec quality = acceptance quality.** The acceptance criteria missed a doc
   location (`parsers.md`, still "7 active parsers"); the spec faithfully inherited
   the gap — but the reviewer caught it as a non-blocking follow-up. The harness is
   only as good as its acceptance, and it degrades gracefully when the acceptance is
   thin.

## Open (on the feature, by design)

- the human visual gate (a person eyeballs the annotated PDFs);
- the pre-existing `web.md` docs-parity drift (a "which copy is canonical" decision).

## 2026-06-04 — Operator performance review (run 1). Grade: B / works-with-caveats

The run produced a correct outcome but needed human/leader improvisation three times;
a less attentive operator could have shipped a false green or stalled. New/sharpened
findings beyond the four above:

5. **Reviewer hung on a background wait for a gate that doesn't exist.** The first
   reviewer spawned a *background task* "waiting for pytest summary" — but a parser
   feature has no pytest. It never wrote its review file; ~16 min / 57k tokens wasted,
   required a full re-dispatch.
   → Fix: reviewer runs gates in the **foreground**, never backgrounds a wait; the
   parser gate profile must say "foreground scripts, not pytest." (Applied to
   `roles/reviewer.role.yaml` + `examples/sella-cruce/profile.yaml`.)

6. **The leader cannot recover a stalled subagent.** Its toolset has no
   `SendMessage`; when the reviewer hung, the only option was re-dispatch (discarding
   the hung run's work). Resume was implied but not possible.
   → Fix: the leader does **not** promise resume — on a stall it **re-dispatches
   fresh**, which is cheap precisely because handoff is on disk (the new agent reads
   state and continues, losing nothing). (Applied to `roles/leader.role.yaml`.)

7. **Delta-based mechanical gates** (sharpens finding #3). docs-parity was RED before
   the feature; treated as absolute pass/fail it would block *every* future feature in
   this repo. The reviewer's manual stash-and-rerun (red-before ∧ red-after ⇒
   pre-existing ⇒ not this feature's fault) should be the **harness's automated
   behavior**, not human improvisation.
   → Fix: mechanical gates are evaluated as a **delta**. (Applied to
   `methodologies/sdd/methodology.md` gate classes + the profile's docs-parity entry.)

8. **Parity ≠ truth.** `docs-sync` passes when both doc copies are identically *wrong*
   (`parsers.md` still says "7 active parsers"; it's now 8). The check validates
   consistency, not correctness — a reminder that a green mechanical gate bounds, but
   does not guarantee, correctness.

Run metrics: 1 spec_author (~40k tok), 1 implementer (~56k tok, 52 tools), 2 reviewers
(1 hung, 1 clean), 2 human gates (spec approval, visual). 1 false start, 0 incorrect
outcomes shipped. Highest-leverage fix: **#7 delta gates** — without it this repo's
harness is blocked by unrelated drift on every feature.
