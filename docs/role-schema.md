# Role schema

A role splits into two parts that live in two places.

| | **Lens** — agnostic, shared library | **Binding** — supplied by the methodology |
|---|---|---|
| Answers | *what this role IS* (competence, posture) | *how it's wired into this methodology* |
| Reusable across | every pack and project | one pack |
| Declares | id, lens prose, posture, capabilities | the state it acts on, reads, writes, gate, next state |
| Lives in | `harness/library/roles/<id>.role.yaml` | a phase entry in `harness/library/methodologies/<m>/methodology.yaml` |

## The lens (library)

```yaml
id: reviewer
lens: |
  Skeptical, independent judge. Assume the work is incomplete until verified; your
  value is catching what the producer rationalized. Cite files+lines. Judge, never fix.
posture:
  mutates: false      # → host renders a read-only toolset
  context: fresh      # bias isolation — run uncontaminated by the producer
  output: verdict
capabilities: [read, search, run_checks]   # host-neutral; the renderer maps to real tools
```

`posture` is the host seam:

- `mutates: false` → the host gives a read-only toolset (no Edit/Write).
- `context: fresh` → the host runs this role as an isolated subagent (independence).
- `capabilities` → host-neutral verbs the renderer maps to concrete tools.

## The binding (methodology)

```yaml
- role: reviewer
  on:   in_review
  reads:  [specs/<f>/*, progress/impl_<f>.md, src/**, tests/**, CHECKPOINTS.md]
  writes: [progress/review_<f>.md]
  gate:   [verify, traceability]
  to:     {approve: done, reject: in_progress}
```

## Compile → host agent

`init` merges lens ⊕ binding and emits (for Claude) `.claude/agents/<role>.md`:

| Source | → `.claude/agents/<role>.md` |
|---|---|
| `lens.id` | filename + `name:` |
| lens prose + role-in-pack | `description:` + body intro |
| `posture.mutates` + `capabilities` | `tools:` (host map) |
| binding `reads`/`writes` | body "You read / You write" + one-line-reference rule |
| binding `gate` | judgment checklist in body; mechanical gates → hooks |
| binding `on`/`to` | body precondition + transition |

Re-target with `--host opencode` and only the right column changes; lens and binding
are untouched.

## Menu, not cast

The roster is the *available* cast; who is *summoned* per task is the orchestrator's
escalation policy, declared in the pack so a 20-line fix doesn't convene seven agents:

```yaml
escalation:
  trivial: [implementer]                          # 1 file
  normal:  [spec_author, implementer, reviewer]
  complex: [explorer*2, spec_author, implementer, reviewer]
```

## Domain roles (expansion packs)

A domain expert's *knowledge is its lens* — legitimate, because that's
competence-it-IS (authored once, reused), not methodology-knowledge fed per turn. It
ships in an expansion pack and overrides a base lens; the core library stays agnostic:

```yaml
# packs/domain-iva/roles/iva_expert.role.yaml
id: iva_expert
extends: reviewer
lens: |
  Spanish VAT-refund expert: NIF validation, AEAT/SAT filing constraints,
  modelo-303/390 fields. Reject anything that violates them.
domain: true
```
