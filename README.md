# method-based-harness

An `init` CLI that drops a **methodology-driven, multi-agent harness** into any
repository. The repo becomes the runtime: the installed agent host (Claude Code
first) reads role definitions, hooks, and on-disk state and drives work through a
chosen methodology's gates. No model API keys, no runtime service — it rides your
existing agent subscription.

## The niche

Two tools bracket this one:

- **GitHub Spec Kit** — same install-and-go spine, but SDD is hardcoded; no methodology dimension.
- **BMAD-METHOD** — names the abstraction ("Methodology as Code") with the richest pack grammar, but fuses the methodology to its roster.

method-based-harness is the combination neither ships: **spec-kit's lightness +
BMAD's pluggability** — swap the methodology, keep the roster.

## The model — four orthogonal layers

```
role library     ×   methodology      ×   project profile    ×   host
(competence)         (choreography)       (repo specifics)       (render target)
agnostic roles       SDD / TDD / ...      verify cmd,            Claude Code
lens + posture       states + gates       constitution,         .claude/agents,
                     + handoffs           per-type gates         settings.json, CLAUDE.md
```

`harness init --methodology sdd --host claude` binds these four and **compiles** to
the host's native format. Adding a host is one renderer that serves every
methodology (N+M, not N×M). Adding a methodology is one declaration that runs on
every host.

## Status

**Design validated; CLI working; not yet published.** A hand-authored spike of the SDD
pack ran end-to-end on a Claude Pro subscription in a real project (`sella-cruce`) —
driving a feature through `pending → spec_ready → ⏸ human → in_progress → in_review`,
gates holding under independent verification (see [`docs/findings.md`](docs/findings.md)).
That proven output was then turned into the **`init`/`upgrade` CLI**: it compiles the
bundled library + a project profile into the host's files, and `upgrade` re-renders them
(preserving local state, pruning orphans, refusing hand-edited managed files without
`--force`). The library ships inside the wheel, so the tool carries it when installed.

## Layout

| Path | What |
|---|---|
| `harness/{cli,compile,manifest}.py`, `harness/hosts/claude.py` | the `init`/`upgrade` CLI + compiler + Claude renderer |
| `harness/library/roles/*.role.yaml` | agnostic role lenses (competence + posture) |
| `harness/library/methodologies/<id>/` | states + gates + phases (the choreography) |
| `harness/library/examples/sella-cruce/` | a real, proven project profile (also the selftest fixture) |
| `docs/ARCHITECTURE.md` | the four layers, the init/compile flow, N+M |
| `docs/methodology-authoring.md` | the pack contract: 4 things, gate classes, the hard-gate rule |
| `docs/role-schema.md` | lens vs binding; how a role compiles to a host agent |
| `docs/findings.md` | learning log — the sella-cruce run and what it taught |

## Next

1. Validate `upgrade` on the real `sella-cruce` repo (adopt the hand-authored spike → upgrade).
2. Finish the banregio feature through `in_review → done`.
3. Publish so `uv tool install method-based-harness` works end to end.
