# Drive your first feature in Claude Code

A concrete walkthrough: zero to a feature at `in_review`, driven by the SDD harness.
Every command below was run against a real repo and the output is quoted verbatim.
The in-session agent behavior (what Claude Code does once you open it) is described
from the rendered `.claude/CLAUDE.md` block and agent files — not from a fabricated
transcript.

---

## Prerequisites

- **Claude Code** installed and authenticated (any Claude Pro or higher subscription).
- **[uv](https://docs.astral.sh/uv/)** for installing the tool.
- A git repository with a test suite (the tool auto-detects pytest).

---

## Step 1 — Install the tool

```bash
uv tool install git+https://github.com/moisesPAello/method-based-harness
harness --version
# harness 0.0.1
```

---

## Step 2 — Scaffold a starter profile

Inside your repo, run the bare init. It sniffs the interpreter and test command,
writes `.harness/profile.yaml`, and exits — it never compiles anything until the
profile is filled.

```bash
cd your-repo
harness init --methodology sdd --host claude
```

**Actual stderr output (bare run):**

```
init: no profile yet — wrote a starter .harness/profile.yaml
      edit it (verify command, interpreter, gate_profiles), then re-run `harness init`.
```

Exit code is 1 — this is intentional: the scaffolded profile has empty gate slots
(`[]`) that fail validation on re-run. It's a fill-in-the-blanks loop by design.

**What `.harness/profile.yaml` looks like after the bare run** (auto-detected a
pytest repo):

```yaml
# .harness/profile.yaml — this repo's binding for the `sdd` methodology.
# `harness init` generated this. Fill the TODOs (empty values fail validation on
# re-run), then re-run `harness init` to install. Full worked example:
# harness/library/examples/sella-cruce/profile.yaml
project: myapp
methodology: sdd
host: claude

# Interpreter the gate commands run under — pin it so they're deterministic.
interpreter: "python3"

verify:
  command: "pytest -q"          # detected

# Docs-parity gate (OPTIONAL). Set `sync_check` to a command that proves the docs
# match the code and `init` compiles it into a Stop hook (runs before a feature can
# close) and the reviewer cites it. Leave it "" and no docs hook is wired.
docs:
  sync_check: ""              # TODO (optional): e.g. "python scripts/check_docs_sync.py"

# Always-on rules, compiled to host hooks. [] = none. Each entry needs an `id`.
constitution: []

# Gates differ by feature TYPE. `default` is required; add more keyed to a feature `type`.
gate_profiles:
  default:
    impl_complete: []          # TODO: checkable conditions for `impl_complete`
    review_passed: []          # TODO: checkable conditions for `review_passed`
```

---

## Step 3 — Fill in the profile

The two `[]` slot lists are what you must fill. For a standard pytest repo, a
minimal but sufficient fill looks like this:

```yaml
project: myapp
methodology: sdd
host: claude

interpreter: "python3"      # pin to .venv/bin/python if you use a venv

verify:
  command: "pytest -q"

# Always-on rules (compiled to Stop hooks). Add entries with an `id`.
constitution:
  - {id: no-placeholders, class: judgment, check: "no TODO/FIXME/pass/... in changed source"}

# Per-feature-type gate conditions. `default` is required.
gate_profiles:
  default:
    impl_complete:
      - "all tasks in tasks.md are [x]"
      - "verify.command is green (pytest -q)"
      - "each R<n> maps to a concrete pytest test under tests/"
    review_passed:
      - "traceability R<n> <-> test confirmed"
      - "no placeholders in changed src"
      - "CHECKPOINTS satisfied"
      - "verdict == APPROVED"
```

See `harness/library/examples/sella-cruce/profile.yaml` for a real-world profile
with multiple feature types, a constitution with delta-aware mechanical gates, and
a docs sync check.

---

## Step 4 — Compile the harness

Re-run init. This time the profile is valid and the compiler runs:

```bash
harness init --methodology sdd --host claude
```

**Actual stderr + stdout output:**

```
init: baseline-auditing the verify gate (cap 120s): pytest -q
init: verify gate terminated, baseline green (exit 0) -> .harness/baseline.json
.claude/agents/implementer.md
.claude/agents/leader.md
.claude/agents/reviewer.md
.claude/agents/spec_author.md
.claude/settings.json
.harness/CHECKPOINTS.md
.harness/methodology.md
.harness/methodology.yaml
.harness/profile.yaml
.harness/feature_list.json
.harness/progress/current.md
.harness/specs/.gitkeep
.claude/CLAUDE.md
init: installed sdd × claude (8 managed files).
```

(Stdout is the file list; stderr is the progress lines. Exit 0.)

### What each file is

**Managed files** — compiled from the library; never hand-edit; `harness upgrade` overwrites them:

| File | What |
|---|---|
| `.claude/agents/leader.md` | Orchestrator agent: reads the state machine, dispatches roles, enforces the human-approval pause |
| `.claude/agents/spec_author.md` | Spec writer agent: produces the three EARS spec files |
| `.claude/agents/implementer.md` | Implementer agent: codes from the approved spec |
| `.claude/agents/reviewer.md` | Reviewer agent: independent judge, re-runs gates |
| `.claude/settings.json` | Permissions allowlist and Stop hook (constitution's mechanical gates) |
| `.harness/methodology.md` | The SDD process doc (source for agents to read at startup) |
| `.harness/methodology.yaml` | Structured state machine (phases/gates/states) for agents and tooling to parse |
| `.harness/CHECKPOINTS.md` | Definition of "correct final state" (the reviewer's checklist) |

**Local state files** — created once; never overwritten by `upgrade`; yours to edit:

| File | What |
|---|---|
| `.harness/profile.yaml` | Your profile (the binding) |
| `.harness/feature_list.json` | Work items and their current status |
| `.harness/progress/current.md` | Free-form session notes |
| `.harness/specs/` | Spec files written by the spec_author |
| `.harness/baseline.json` | Snapshot of the verify-gate baseline at install time |

**Merged block** — `init` merges a fenced block into `.claude/CLAUDE.md` (never clobbers the file):

```
<!-- METHOD-HARNESS:BEGIN (managed — do not hand-edit; `harness upgrade` overwrites) -->
## Active harness: Spec-Driven Development

This repo has a `sdd` harness under `.harness/`. When asked to build or change a
feature, act as the **`leader`** agent (`.claude/agents/leader.md`): orchestrate, never edit
`src/`/`tests/` yourself, and drive every feature through:

`pending → [spec_author] → spec_ready → ⏸ HUMAN → in_progress → [implementer] → in_review → [reviewer] → done`

- Work items + status: `.harness/feature_list.json`
- Process: `.harness/methodology.md`; this repo's gate values: `.harness/profile.yaml`
- Definition of done: `.harness/CHECKPOINTS.md`

For pure questions or doc/config edits outside `src/`+`tests/`, answer directly. To
uninstall: delete `.harness/`, the `.claude/agents/*` role files, `.claude/settings.json`,
and this block.
<!-- METHOD-HARNESS:END -->
```

`.claude/settings.json` also pre-authorizes `Bash(python3)`, `Bash(python3 *)`,
`Bash(pytest)`, and `Bash(pytest *)` so the agents can run the verify gate without a
permission prompt (bare form covers no-argument invocations; space-star form covers
invocations with arguments).

---

## Step 5 — Check install health

```bash
harness doctor
```

**Actual stderr output (clean install):**

```
doctor: ok.
```

If something is wrong, `doctor` lists `FAIL:` lines. Common issues:

- `FAIL: managed file missing` — a compiled file was deleted; re-run `harness upgrade`.
- `warn: interpreter 'python3' not found` — set `interpreter` to the full venv path.
- `warn: verify command 'pytest' not found` — install pytest or fix the `verify.command`.

---

## Step 6 — Add your first feature

Edit `.harness/feature_list.json` and add an entry to the `features` array:

```json
{
  "id": "add-greet",
  "name": "add-greet",
  "type": "default",
  "status": "pending",
  "description": "Add a greet(name) function that returns 'Hello, <name>!'"
}
```

Check the status:

```bash
harness status
```

**Actual stdout + stderr:**

```
status: myapp (sdd) — 1 feature(s)
ID         STATUS   TYPE     NEXT
add-greet  pending  default  spec_author -> spec_ready
```

The `NEXT` column is derived live from the methodology's phase table.

---

## Step 7 — Open Claude Code and drive the feature

Open Claude Code in your repo (`claude` in the terminal, or via the IDE extension).

Because `init` merged the harness block into `.claude/CLAUDE.md`, the session reads
it on startup. The block instructs the session to act as the **`leader`** orchestrator
and to drive every feature through the SDD state machine. The leader's full
instructions are in `.claude/agents/leader.md`.

From `leader.md` (the actual compiled file):

> **Startup**  
> 1. Read `.harness/methodology.md`, `.harness/profile.yaml`,
>    `.harness/feature_list.json`, `.harness/progress/current.md`.  
> 2. Confirm the baseline: run `pytest -q` (via `python3`). If it cannot run or is
>    red, stop and report.

Then say something like:

```
Build the next feature.
```

**What the leader does** (from the compiled agent files — this is the instruction
it operates under, not a fabricated transcript):

1. Reads the state files, confirms the verify baseline.
2. Sees `add-greet` is `pending` — dispatches a `spec_author` subagent.
3. The `spec_author` writes three files under `.harness/specs/add-greet/`:
   - `requirements.md` — numbered EARS requirements (`R1`, `R2`, …)
   - `design.md` — design decisions addressing each requirement
   - `tasks.md` — ordered task list (`T1`, `T2`, …) each citing at least one `R<n>`
4. `spec_author` self-checks for coherence (every `R<n>` addressed in design and
   covered by a task; nothing in design/tasks exceeds the requirements) and marks
   any gaps `[NEEDS CLARIFICATION: <question>]` rather than guessing.
5. Sets `status` to `spec_ready` in `feature_list.json`.
6. Returns one line to the leader: `spec_ready -> .harness/specs/add-greet/`
7. **Leader stops** and asks you to review and approve the spec.

---

## Step 8 — The human-approval gate (the deliberate pause)

This is the `⏸ HUMAN` gate in the flow. The leader will not dispatch the implementer
until you explicitly approve.

1. Read `.harness/specs/add-greet/requirements.md`, `design.md`, `tasks.md`.
2. Resolve any `[NEEDS CLARIFICATION]` markers by editing the spec files directly.
   A stray marker is a grep-able fail on the gate — none may survive into implementation.
3. Reply in the Claude Code session: `approved` (or `approved for add-greet`).

The leader then:

- Sets `status` to `in_progress` in `feature_list.json`.
- Dispatches an `implementer` subagent.

---

## Step 9 — Implementation and review

**Implementer** (from `implementer.md`):

> Implements ONE `in_progress` feature from its approved spec. Writes code and its
> test/evidence, follows the tasks in order, self-verifies against the feature's type
> gate, and never self-approves.

The implementer works through the tasks in `tasks.md`, writes code and tests,
runs `pytest -q`, and writes a progress report to
`.harness/progress/impl_add-greet.md`. It returns one line to the leader:
`done -> .harness/progress/impl_add-greet.md`.

**Reviewer** (from `reviewer.md`):

> Skeptical, independent judge. Assumes the work is incomplete until verified;
> re-runs the gates itself rather than trusting the producer's report; cites files
> and lines. Approves or rejects — never fixes.

The reviewer is dispatched in a **fresh context** (independence from the implementer).
It re-runs `pytest -q` itself, checks traceability (each `R<n>` has a real test),
walks CHECKPOINTS, and writes a verdict to
`.harness/progress/review_add-greet.md`. Mechanical gates are evaluated as a
**delta**: if `pytest` was already red before the feature (stash + re-run), the
pre-existing failure does not block this feature — it is flagged, not gated on.

After review the feature is either `done` (approved) or back to `in_progress`
(changes requested). Check with:

```bash
harness status
```

**Actual status at in_review:**

```
status: myapp (sdd) — 1 feature(s)
ID         STATUS     TYPE     NEXT
add-greet  in_review  default  reviewer -> done
```

---

## Where state lives

| What you want | Where to look |
|---|---|
| Feature statuses | `.harness/feature_list.json` |
| Current session notes | `.harness/progress/current.md` |
| Spec for a feature | `.harness/specs/<feature>/` |
| Implementation report | `.harness/progress/impl_<feature>.md` |
| Review verdict | `.harness/progress/review_<feature>.md` |
| Gate baseline snapshot | `.harness/baseline.json` |
| Installed agent definitions | `.claude/agents/*.md` |

All handoffs are on disk. If an agent stalls mid-run, the leader re-dispatches a
fresh one — it picks up from the spec/progress files and continues, losing nothing.

---

## Resuming a stalled run

From `leader.md`:

> `in_progress / in_review` → a driver stalled: **re-dispatch a FRESH one** (on-disk
> state loses nothing); never wait to resume.

Just tell the leader in the Claude Code session:

```
The implementer stalled. Re-dispatch.
```

It will start a new subagent reading `.harness/specs/add-greet/` and
`.harness/progress/impl_add-greet.md`.

---

## Keeping the harness current

Two separate update paths:

```bash
# Update the tool (and its bundled library):
uv tool upgrade method-based-harness

# Then re-render the compiled files in this repo:
harness upgrade
```

`upgrade` re-renders from the library bundled in the installed tool. It preserves
all local state files, prunes orphaned managed files, and refuses to overwrite
hand-edited managed files without `--force`. Preview what would change without
writing anything:

```bash
harness upgrade --dry-run
```

---

## Uninstalling

From the CLAUDE.md block (quoted verbatim):

> To uninstall: delete `.harness/`, the `.claude/agents/*` role files,
> `.claude/settings.json`, and this block.

```bash
rm -rf .harness/
rm .claude/agents/leader.md .claude/agents/spec_author.md \
   .claude/agents/implementer.md .claude/agents/reviewer.md
rm .claude/settings.json
# Then remove the fenced block from .claude/CLAUDE.md manually
#   (between <!-- METHOD-HARNESS:BEGIN --> and <!-- METHOD-HARNESS:END -->)
```

---

## What was verified live vs. described from files

**Verified by running actual commands** (all output quoted verbatim above):

- `harness init` bare run output and the exact scaffolded `profile.yaml` content.
- `harness init` full run output (file list, baseline audit message, exit code).
- Contents of `.harness/feature_list.json`, `.harness/baseline.json`,
  `.claude/CLAUDE.md` block, `.claude/settings.json`, and all four agent `.md` files.
- `harness status` output at every state (`pending`, `spec_ready`, `in_progress`,
  `in_review`, `done`) — the NEXT column is real, derived live from the methodology.
- `harness doctor` output on a clean install.

**Described from the rendered files** (not from a live agent session):

- What the leader, spec_author, implementer, and reviewer do during a session — this
  is described from their compiled `.claude/agents/*.md` files, which contain the
  actual instructions the agents operate under. The in-session behavior of Claude Code
  itself (what it says, how many turns it takes) was not observed in a live session
  and is not described here.
