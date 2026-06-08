# Architecture

## What this is

A scaffolder. `harness init` drops a methodology-driven multi-agent harness into a
target repo; the repo *is* the runtime. There is no long-running service and no
model API key — the installed host (Claude Code first) is the runtime, driven by the
files we emit, and it authenticates via the user's existing subscription.

This is the **orchestrator** species (a supervisor *around* an agent), not an
own-the-loop agent. We never call a model directly; we shape what the host agent does.

## The four orthogonal layers

A working harness is the product of four independent dimensions. Keeping them
separate is the whole design — it's what makes methodology and host swappable.

| Layer | Answers | Examples | Lives in |
|---|---|---|---|
| **Role library** | *what a worker IS* (competence + posture) | leader, spec_author, implementer, reviewer | `harness/library/roles/*.role.yaml` (agnostic) |
| **Methodology** | *the choreography* (states, gates, handoffs) | SDD, TDD, Scrum | `harness/library/methodologies/<id>/` |
| **Project profile** | *this repo's specifics* | verify command, constitution, per-type gates | the target repo's `.harness/profile.yaml` (captured at init) |
| **Host** | *the render target* | Claude Code, OpenCode, VSCode | a renderer per host |

### Why four, and why orthogonal

- A **methodology is the non-role three-quarters of a pack** — it's the state
  machine + the artifact handoffs + the gates, imposed on a *constant* roster.
  SDD and TDD use the same `implementer` and `reviewer`; only the choreography
  differs. (See `methodology-authoring.md`.)
- The **project profile** fills the methodology's generic gate *slots* with
  repo-specific values (the verify command, the constitution, per-feature-type gate
  profiles). It is this tool's equivalent of a `harness_config.json`, captured at
  `init`. The methodology stays project-agnostic; the profile binds it.
- The **host** is the only thing that changes when you re-target. Lens and binding
  are untouched — that's the N+M payoff below.

## The init / compile flow

```
roles/ (lens)  +  methodologies/<m> (binding)  +  profile (repo)  ──compile(host)──▶  host-native files
```

For `--host claude`, the compiled output is:

- `.claude/agents/<role>.md` — one per role in the methodology's roster, frontmatter
  `tools` derived from the role's posture, body assembled from lens + binding + gate.
- `.claude/settings.json` — hooks for the **constitution** gates (see findings: hooks
  enforce the type-independent constitution; type-specific gates are run by the
  drivers, because static hooks can't be feature-type-aware).
- `.claude/CLAUDE.md` — a **merged, marked block** (never a clobber) that locks the
  session as the methodology's orchestrator role.
- `.harness/` — the host-neutral source (methodology, profile, feature_list,
  checkpoints, specs/, progress/) kept alongside the compiled output, namespaced so
  a single delete uninstalls cleanly.

The split is deliberate: `.harness/` is the **source**, `.claude/` is the **compiled
output**. Keeping both on disk gives the generator a known input→output pair.

## N + M, not N × M

Because methodology and host are orthogonal:

- adding a **host** = one renderer that serves *every* methodology;
- adding a **methodology** = one declaration that runs on *every* host.

Build only the cell you need first (SDD × Claude). Extract the renderer abstraction
when a second host or methodology actually forces it — not before.

## The tracker seam (optional, opt-in) — "issues as the membrane, disk as the organ"

On-disk state is the **source of truth** for execution: the state machine, gates and
EARS traceability never leave disk. An external issue tracker is an *optional* adapter
that syncs only the **backlog edge**, symmetric to the host layer (`harness/trackers/`
mirrors `harness/hosts/`):

| `tracker:` | Behavior |
|---|---|
| `none` (default) | Disk only. A complete no-op — no network, no auth, no `gh` code reached. The harness is byte-for-byte unchanged. |
| `github-issues` (opt-in) | The leader may run `harness tracker sync`: **intake** (open issues seed `pending` features) + **outtake** (a `done` feature closes its issue with links to the spec/review artifacts). Shells out to `gh`; degrades gracefully when `gh` is missing/unauthenticated. |

The adapter interface is deliberately tiny:

```
intake(root, profile, *, run=None)  -> list[feature_dict]   # seed backlog
outtake(root, profile, feature, *, run=None) -> bool         # close on done
```

Hard boundaries (acceptance criteria for issue #4):

- **Only the leader** integrates with the tracker. Subagents stay disk-only.
- **State machine / gates / traceability never leave disk** — the tracker only touches
  the backlog edge (new features in, closed issues out).
- The adapter is **optional**: with `tracker: none` (or absent) the render and every
  core flow (`init`/`upgrade`/`status`/`doctor`) are unchanged and run no `gh`/network
  code. The `github-issues` module is imported lazily, only when opted in.
- `harness tracker sync` is the sole entrypoint that may reach a tracker, and it is a
  no-op under `tracker: none`. The runner is injectable, so tests fake `gh` offline.
