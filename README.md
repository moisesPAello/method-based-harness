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

**Design validated; the CLI is not built yet.** A hand-authored spike of the SDD
pack was installed into a real project (`sella-cruce`) and **ran end-to-end on a
Claude Pro subscription** — driving a real feature through
`pending → spec_ready → ⏸ human → in_progress → in_review`, with the type-aware
gates and the human visual gate holding under independent verification. See
[`docs/findings.md`](docs/findings.md).

This repo currently holds the **design** and the **proven content** the future CLI
will consume and emit.

## Layout

| Path | What |
|---|---|
| `docs/ARCHITECTURE.md` | the four layers, the init/compile flow, N+M |
| `docs/methodology-authoring.md` | the pack contract: 4 things, gate classes, the hard-gate rule |
| `docs/role-schema.md` | lens vs binding; how a role compiles to a host agent |
| `docs/findings.md` | learning log — the sella-cruce run and what it taught |
| `roles/*.role.yaml` | agnostic role lenses (competence + posture) |
| `methodologies/<id>/methodology.md` | states + gates + phases (the choreography) |
| `examples/sella-cruce/` | a real, proven project profile |

## Next

1. Take the proven spike (`examples/sella-cruce/` + the live branch
   `harness/sdd-banregio` in the sella-cruce repo) as a known-good input→output pair
   and extract the `init` generator.
2. Fold the four findings (`docs/findings.md`) into the profile schema.
