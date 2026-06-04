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
