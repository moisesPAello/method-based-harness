# Authoring a methodology

> A methodology is a pack of **structure**, not a tutorial. You don't make a model
> follow a method by feeding it knowledge *about* the method — it already has the
> mushy averaged version. You encode the method as enforceable structure *between*
> turns. Books are your source at authoring time; they never enter runtime.
>
> - ❌ **Knowledge** (the book, "what SDD is") → authoring-time only.
> - ✅ **Structure** (templates, gates, state transitions) → distilled from the
>   books, shipped as the runtime contract.

## A pack declares four things

1. **Roles** — which agnostic roles from the library this methodology uses (by id).
2. **Artifact I/O** — which files each role reads and writes. *The handoff is the
   methodology.* Agents pass products on disk and return one-line references
   (anti-telephone): durable, versioned, resumable when an agent stops mid-flow.
3. **Gates / checklists** — the hard conditions on each transition. This is where
   the rigor lives.
4. **State machine** — the states, the transitions, and the human-approval halts.

Roles are agnostic and shared; the methodology is the other three. **The methodology
is the choreography over a constant roster** — same actors, different play.

## Gates are hard, verifiable exit-conditions

A gate is never advisory prose ("the developer should write tests first"). It is the
hardest checkable condition on a state transition ("the implement phase cannot start
until a failing test exists"). Every gate has a **class**, which tells the compiler
where it goes:

| Class | Hardness | Compiles to |
|---|---|---|
| **mechanical** | absolute — a command returns pass/fail | `init.sh`/host hook — un-skippable. **Probe the command exists; never assume it from docs.** |
| **human** | the deliberate halt | an orchestrator halt rule in the host instructions |
| **judgment** | only as hard as the judge is independent | the reviewer role, run in a *fresh* context |

The craft: push everything you can into **mechanical**; for the irreducible rest,
isolate the reviewer so its judgment is real. Some gates judge *artifacts*, not just
code (e.g. "seals legible in this annotated PDF") — those become a second **human**
gate, mid-flow.

## State machine + handoffs

Express the methodology as phases. Each phase entry binds a role:

```
state · driver(role id) · reads(files) · writes(files) · exit_gate · to(state) [· halt | on_reject]
```

Stack the phases and you have both the state machine and the per-role bindings — they
are the same thing viewed two ways.

## Requirements style (SDD example): EARS

Each requirement is one numbered `R<n>`, one pattern: Ubiquitous (`SHALL`), Event
(`WHEN … SHALL`), State (`WHILE … SHALL`), Optional (`WHERE … SHALL`), Unwanted
(`IF … THEN … SHALL`). One `SHALL` each; every `R<n>` verifiable by ≥1 concrete
evidence; no soft verbs.

## Gates are per feature *type*

Different feature types need different evidence. The methodology declares gate
*slots*; the **project profile** fills them with per-type `gate_profiles`. Example
(from sella-cruce): a `cli` feature is proven by `pytest`; a `parser` feature is
proven by a smoke script + an export CSV + visual-debug PDFs — `pytest` proves
nothing about it. A feature carries a `type`; the type selects the profile.

## Prior art worth reading

- **GitHub Spec Kit** — the lightweight install-and-go shape; steal its
  `constitution.md` (non-negotiables) → our always-on global gates.
- **BMAD-METHOD** — the mature pack grammar (agents / workflows / tasks / templates /
  expansion packs). Read it for the grammar; don't copy its role↔methodology coupling.
