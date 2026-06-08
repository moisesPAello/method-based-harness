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

## 2026-06-08 — Run 2: first end-to-end on CLI-generated output (issue #6). Grade: B− / works, shipped one roster-breaking bug

First validation of the **`harness init`-generated** pack as the operator experience (run 1
was a hand-authored spike). A real bugfix — **`ocr_footer_detection`** (issue #78: tolerate
OCR noise in footer/marker detection) — was driven `pending → spec_ready → [human approved]
→ in_progress → in_review → done` in a fresh Claude Code session on the sella-cruce repo,
using only the generated `.claude/agents/*` + `.claude/settings.json` + `.harness/` (manifest
`tool_version: 0.0.1`). Full session export and report under `docs/` in this repo.

### What held (the folded-in fixes, on generated agents)

- **reviewer ran gates foreground** (finding #5 fix held) — independently re-ran
  `pytest -q -m "not visual"`, confirmed before 45 → after 59 passed, no hung background wait.
- **the human-approval pause was obvious and resumable** — leader halted at `spec_ready` with
  an explicit approve prompt; on approval it bumped status and dispatched the implementer.
- **on-disk handoff held** — spec / impl-report / review-verdict all on disk, one-line refs.
- **scoped change discipline held** — one file (`+27/−2`), regex path left byte-for-byte
  unchanged, conservative threshold per the "empty > invented data" constitution.

### New findings

9. **A multi-line `description:` silently drops an agent from the generated roster.** (issue #13) The
   leader's *first* dispatch failed: `Agent type 'spec_author' not found. Available agents:
   ... implementer, leader, reviewer`. The file `.claude/agents/spec_author.md` existed and
   was freshly generated — but its YAML frontmatter `description:` wrapped onto a column-0
   second line (`...requirements, design,⏎tasks. Writes...`), which YAML parses as a stray
   key. Claude Code silently skipped registering the agent. Root cause: `_front()`
   (`harness/hosts/claude.py:54`) takes `lens.split(".")[0]` of a `lens: |` block scalar and
   drops it into `description:` **without collapsing internal whitespace**; only spec_author's
   first sentence happened to span two source lines, so only it broke. A generated-output
   *correctness* bug — the leader masked it by improvising a `general-purpose` agent as
   spec_author (graceful, but it hid a shipped defect).
   → Fix: normalize in `_front()` — `desc = " ".join(desc.split())` (guarantees a single-line
   `description:`). Compile-check should assert every generated agent's frontmatter is
   single-line / re-parseable, and `doctor` should verify the host actually registers each
   roster agent, not just that the file exists.

10. **The profile's mechanical gate command is taken on faith.** (issue #14) `profile.yaml` shipped
    `pytest -q` as the gate; bare `pytest -q` **hangs forever** on the repo's
    `@pytest.mark.visual` suite (~98% CPU, ~9 min before the operator killed it). The usable
    gate is `pytest -q -m "not visual"` — discovered live, not declared. Sharpens #3: `init`
    should baseline-audit the gate command (does it *terminate*? what's its red/green
    baseline?) and the profile should carry the **scoped** command, so the operator never
    rediscovers it mid-run. (The hang itself is a sella-cruce bug, tracked there.)

11. **The leader busy-polls background gates.** (issue #15) With pytest backgrounded, the leader degraded
    into ~9 minutes of "I'll wait" turns — it has no await-a-background-gate primitive and no
    way to know a gate is pathological vs. merely slow. Relates to #5/#6 (background waits,
    stalled-subagent recovery). → The leader should run bounded/foreground gates or set a
    hard wall-clock cap and treat overrun as a red, not poll indefinitely.

Run metrics: 1 spec_author (improvised general-purpose, ~40k tok), 1 implementer (~34k tok,
25 tools), 1 reviewer (~36k tok, 22 tools, clean), 1 human gate (spec approval). 1 generated
roster bug surfaced, 0 incorrect outcomes shipped. Highest-leverage fix: **#9** — a fresh
`init` ships an agent the host won't load, breaking the very first dispatch of every SDD run.

## 2026-06-08 — `upgrade` validated end-to-end against a downstream repo (issue #3)

`harness upgrade` had only ever run against the selftest fixture. Driven live against a
throwaway downstream repo (pytest-shaped, seeded from the bundled `sella-cruce` example
profile) to prove the four contract bullets — propagation keyed off a **real** library
delta, not a simulated hash bump:

- **Stale render from an older library.** Rendered the agent pack from revision `14b55af`
  (parent of the leader bounded-gate fix 017dd26) via `PYTHONPATH=<old-worktree>`. The
  resulting `.claude/agents/leader.md` lacks the `wall-clock` cap language (grep count 0) —
  a genuinely outdated compiled agent, manifest stamped `tool_version 0.0.1`.
- **Propagation.** `upgrade --dry-run` from HEAD reported exactly `update 1 — leader.md`,
  `unchanged 6`, `conflict 0`; the real `upgrade` re-rendered only `leader.md`, which then
  carried `wall-clock` (count 2). A clean library fix propagated into a stale agent.
- **Local state preserved.** `feature_list.json` (with a hand-added feature), `profile.yaml`,
  `progress/current.md`, and a `specs/<feature>/spec.md` were **byte-identical** (sha256
  unchanged) across the upgrade — only managed files re-rendered.
- **Hand-edit refused without `--force`.** Appending an operator comment to `reviewer.md`
  made `upgrade` classify it `conflict (hand-edited)` and exit **non-zero (1)** without
  writing; the edit survived. `upgrade --force` overwrote it (edit gone), exit 0.
- **Adoption of a manifest-less legacy install.** A repo with pre-existing agent files but
  no `.harness/.manifest.json`: `init` refused to clobber (exit 1, names the clashing
  files); `init --force` adopted them — wrote a 7-file manifest matching the render and
  re-rendered the hand-authored `leader.md` to the library version.

Caveat surfaced: adoption via `init --force` is **overwrite-and-stamp**, not stamp-in-place —
a genuinely hand-customised managed file is replaced by the library render (the documented
`--force` semantics, but worth flagging for operators adopting a divergent legacy pack). The
version-string gate (`prior_version != __version__`) is informational only; propagation is
driven by content hashing, so it fires even when the tool version is unchanged (as here,
0.0.1 → 0.0.1). Both adoption and propagation paths are now also pinned by
`tests/test_adopt_and_propagate.py`; full suite green (61 passing).
