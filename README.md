# method-based-harness

> Install a methodology-driven, multi-agent coding harness into any repository.

*English · [Español](README.es.md)*

`method-based-harness` is a small CLI that drops a **multi-agent, methodology-driven
harness** into a repo. The repo itself becomes the runtime: your agent host (Claude Code
today) reads the generated role definitions, hooks, and on-disk state, and drives work
through a chosen methodology's gates. No model API keys and no running service — it rides
the agent subscription you already have.

## Why

Two existing tools bracket this one:

- **GitHub Spec Kit** — same install-and-go shape, but the methodology (spec-driven
  development) is hardcoded.
- **BMAD-METHOD** — a rich "methodology as code" grammar, but the methodology is fused
  to its agent roster.

This tool aims at the gap between them: **Spec Kit's lightness with BMAD's
pluggability** — swap the methodology, keep the roster.

## How it works — four orthogonal layers

```
role library   ×   methodology   ×   project profile   ×   host
(competence)       (choreography)    (this repo's        (render target:
agnostic roles     states + gates    verify cmd,          Claude Code ->
lens + posture     + handoffs)       constitution,        .claude/agents,
                                     per-type gates)      settings.json)
```

`harness init` binds the four and **compiles** them into the host's native files. Because
methodology and host are independent, adding a host is one renderer that serves every
methodology, and adding a methodology is one declaration that runs on every host.

Two ideas make it work:

- **A methodology is structure, not prose.** Gates are hard, verifiable conditions on
  state transitions — not advisory text a model can wave away. You don't teach the model
  *about* a method; you encode the method *between* its turns.
- **Agents hand off on disk.** Each role reads input files, writes its product to a file,
  and returns a one-line reference — durable, versioned, and resumable if an agent stalls.

## Install

Not yet on PyPI. Install from Git with [uv](https://docs.astral.sh/uv/):

```bash
uv tool install git+https://github.com/moisesPAello/method-based-harness
```

## Onboarding

New here? See **[docs/ONBOARDING.md](docs/ONBOARDING.md)** for a step-by-step walkthrough:
install → scaffold → compile → add a feature → drive it from `pending` to `in_review` with
real command output at every step.

## Quickstart

```bash
cd your-repo

# 1. Scaffold a starter profile. A bare init writes .harness/profile.yaml
#    (sniffing your interpreter and test command) and stops.
harness init --methodology sdd --host claude

# 2. Fill it in: the verify command, the always-on "constitution" rules, and
#    per-feature-type gates. Re-running is gated until the required fields are set.
#    A worked example: harness/library/examples/sella-cruce/profile.yaml
$EDITOR .harness/profile.yaml

# 3. Re-run init to compile the harness into the repo.
harness init --methodology sdd --host claude

# 4. Open your agent host (Claude Code) and ask it to build the next feature.
#    It acts as the orchestrator and drives the methodology's gates.
#    Check progress any time with `harness status`; check install health with `harness doctor`.
```

## Commands

| Command | What it does |
|---|---|
| `harness init` | scaffold a starter profile (bare run), or compile the library + your profile into the repo (`--methodology`, `--host`, `--from-profile`, `--dry-run`, `--force`) |
| `harness upgrade` | re-render the managed files from the (updated) library; preserves local state, prunes orphans, refuses hand-edited files without `--force` |
| `harness status` | show each feature and its current state from `.harness/feature_list.json` (read-only) |
| `harness doctor` | diagnose an installed harness — profile validity, manifest integrity, resolvable interpreter/verify — and snapshot the mechanical gate(s) (`--no-baseline`) |
| `harness list` | show available methodologies, hosts, and roles |
| `harness selftest` | render a bundled fixture and verify the output (offline) |

### Keeping things current — two layers

- **The tool itself** (and its bundled library) → your package manager:
  `uv tool upgrade method-based-harness`.
- **An installed repo** → this CLI, per repo: `harness upgrade`.

`harness upgrade` re-renders from the library inside the *installed* tool, so update the
tool first, then upgrade each repo. Managed files are derived — customize the **source**
(your profile, or the library), not the generated output.

## Status

Early (`0.0.1`). The **SDD** methodology on the **Claude Code** host is validated end to
end: a hand-authored spike drove a real feature through
`pending → spec_ready → ⏸ human → in_progress → in_review` on a Claude Pro subscription, on
a real-world repository (a Python bank-statement processing tool, included as the bundled
example), with the gates holding under independent review. That proven output is what the
CLI now generates. A **TDD** methodology is sketched to demonstrate the pluggability seam.

## Layout

| Path | What |
|---|---|
| `harness/` | the CLI, compiler, and Claude renderer |
| `harness/library/roles/` | agnostic role lenses (competence + posture) |
| `harness/library/methodologies/` | methodology declarations (`sdd/`, `tdd/`) |
| `harness/library/examples/` | a worked project profile (also the selftest fixture) |
| `docs/` | architecture, methodology authoring, role schema, findings log |

## License

MIT
