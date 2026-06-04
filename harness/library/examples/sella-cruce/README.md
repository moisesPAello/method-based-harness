# Example: sella-cruce

The first real project this harness was tuned against — a mature Python
bank-statement OCR / parse / cross-check tool (`moisesPAello/sella-cruce`). This
profile **actually ran**: it drove the `banregio_promote` feature end-to-end on a
Claude Pro subscription (2026-06-04). See `docs/findings.md` at the repo root.

## What's here

- `profile.yaml` — the project profile (verify command, constitution, per-type gate
  profiles) that filled the SDD methodology's gate slots for this repo. The proven
  artifact, with the four findings folded in.

## The live spike (the compiled output)

The full compiled harness — `.claude/agents/{leader,spec_author,implementer,reviewer}.md`,
`.claude/settings.json` hooks, the merged `.claude/CLAUDE.md` block, and the
`.harness/` state — lives on the branch **`harness/sdd-banregio`** in the sella-cruce
repo (hand-authored). That branch is the known-good **output**; this `profile.yaml` +
`harness/library/methodologies/sdd/` + `harness/library/roles/` are the **input**.
Together they are the input→output pair the `init` generator reproduces.

## What tuning this repo taught

sella-cruce broke the abstract gate grammar in three ways, all now reflected in the
design (see `docs/methodology-authoring.md` and `docs/findings.md`):

1. gate commands must be **probed**, not assumed (a phantom `test_integration.py`);
2. gates are **per feature type** (pytest for logic, smoke+export+visual for parsers);
3. some gates are **judgment-on-artifacts** → a second human gate (visual approval).
