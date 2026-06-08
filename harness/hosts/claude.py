"""Claude Code host renderer: methodology + role lenses + profile -> Claude-native files.

Returns a RenderResult (set by compile.render). Emits MANAGED files:
  - .claude/agents/<role>.md   (frontmatter tools from posture; body = lens + binding)
  - .claude/settings.json      (Stop hook from the constitution's mechanical gates)
  - .harness/methodology.md, .harness/methodology.yaml, .harness/CHECKPOINTS.md  (source)
and the orchestrator block to merge into .claude/CLAUDE.md.

Posture -> tools:  base Read/Glob/Grep/Bash; +Write/Edit if mutates; +Agent if dispatch.
The role LENS is emitted verbatim, so a library change (e.g. "reviewer runs gates
foreground") propagates into the compiled agent on the next `upgrade`.
"""

from __future__ import annotations

import json
import sys

BEGIN = "<!-- METHOD-HARNESS:BEGIN (managed — do not hand-edit; `harness upgrade` overwrites) -->"
END = "<!-- METHOD-HARNESS:END -->"


def _warn(msg: str) -> None:
    """Diagnostic to stderr (stdout is data); mirrors cli.log without importing it."""
    print(f"render(claude): {msg}", file=sys.stderr)


def _tools(role: dict) -> str:
    base = ["Read", "Glob", "Grep", "Bash"]
    if role.get("posture", {}).get("mutates"):
        base += ["Write", "Edit"]
    if "dispatch" in role.get("capabilities", []):
        base.append("Agent")
    return ", ".join(base)


def _bullets(items, prefix="- ") -> str:
    return "\n".join(f"{prefix}{x}" for x in (items or []))


def _flow(meth: dict) -> str:
    parts = []
    for ph in meth["phases"]:
        drv = ph["driver"]
        parts.append("⏸ HUMAN" if drv == "human" else f"[{drv}]")
    states = [meth["phases"][0]["state"]] + [ph["to"] for ph in meth["phases"]]
    out = states[0]
    for seg, st in zip(parts, states[1:]):
        out += f" → {seg} → {st}"
    return out


def _front(role: dict, extra_desc: str) -> str:
    # Collapse internal whitespace so a wrapped `lens:` block scalar can't leak a
    # newline into the YAML `description:` value (which the host's frontmatter
    # parser reads as a stray key, silently dropping the agent from the roster).
    desc = " ".join((role["lens"].strip().split(".")[0].strip() + ". " + extra_desc).split())
    return f"---\nname: {role['id']}\ndescription: {desc}\ntools: {_tools(role)}\n---\n"


def _phase_for(meth: dict, driver: str) -> dict:
    for ph in meth["phases"]:
        if ph["driver"] == driver:
            return ph
    return {}


def _gate_checks(meth: dict, name: str) -> list[str]:
    return meth.get("gates", {}).get(name, {}).get("checks", [])


def _leader(role, meth, profile) -> str:
    interp = profile.get("interpreter", "python3")
    verify = profile.get("verify", {}).get("command", "the project's test command")
    esc = meth.get("escalation", {})
    esc_lines = _bullets([f"**{k}**: {' → '.join(v)}" for k, v in esc.items()])
    return f"""{_front(role, "Orchestrates; never edits src/tests.")}
# leader (orchestrator)

{role['lens'].strip()}

## Startup
1. Read `.harness/methodology.md`, `.harness/profile.yaml`, `.harness/feature_list.json`, `.harness/progress/current.md`.
2. Confirm the baseline: run `{verify}` (via `{interp}`). If it cannot run or is red, stop and report.

## Running gates (foreground, bounded — never poll)
Run every gate in the FOREGROUND under a hard wall-clock cap (e.g. `timeout`); never
background a gate wait and poll it. A gate that overruns the cap is a **red** (a gate
that won't terminate is a failing gate) — record the red and proceed, don't wait it out.

## Flow (never skip a phase or a gate)
`{_flow(meth)}`

Act on the first feature that is not `done`/`blocked`, by status:
- **pending** → dispatch ONE `spec_author`; on `spec_ready -> ...`, STOP and ask the human to approve.
- **spec_ready + approved** → set `in_progress`, dispatch `implementer` (pass its `type`), then `reviewer`.
- **in_progress / in_review** → a driver stalled: **re-dispatch a FRESH one** (on-disk state loses nothing); never wait to resume.

## Escalation (the roster is a menu, not a cast)
{esc_lines}

## Handoff (anti-telephone)
Tell each subagent to write its product to a file and return ONE line
(e.g. `done -> .harness/progress/impl_<feature>.md`). Act on references, not pasted content.

## You never
- Edit `src/` or `tests/`.  - Mark a feature `done`.  - Skip the human approval gate.  - Accept a result with no file reference.
"""


def _spec_author(role, meth, profile) -> str:
    ph = _phase_for(meth, "spec_author")
    return f"""{_front(role, "Writes the EARS spec; never writes app code or tests.")}
# spec_author

{role['lens'].strip()}

## What you do
Produce the spec for ONE `pending` feature, then STOP for human approval.
- **Read:** {', '.join(ph.get('reads', []))} (and `.harness/methodology.md`, `.harness/profile.yaml`)
- **Write:** {', '.join('`.harness/' + w + '`' for w in ph.get('writes', []))}

## Gate to pass — spec_complete
{_bullets(_gate_checks(meth, 'spec_complete'))}
Then set the feature to `spec_ready`. Do NOT implement.

## Output
One line: `spec_ready -> .harness/specs/<feature>/` (or `blocked -> .harness/progress/spec_<feature>.md`). Never paste the spec.
"""


def _implementer(role, meth, profile) -> str:
    ph = _phase_for(meth, "implementer")
    con = ", ".join(c["id"] for c in profile.get("constitution", []))
    return f"""{_front(role, "Implements one feature from its approved spec; self-verifies, never self-approves.")}
# implementer

{role['lens'].strip()}

## What you do
Implement ONE `in_progress` feature from its approved spec.
- **Read:** {', '.join(ph.get('reads', []))} (and `.harness/profile.yaml`)
- **Write:** {', '.join(ph.get('writes', []))}

## Gate to pass — impl_complete (per the feature's `type`)
Resolve `gate_profiles[<type>].impl_complete` in `.harness/profile.yaml`. Different feature
types require different evidence — run exactly the gate commands your type lists, in the
FOREGROUND. Don't assume a particular test runner; the profile says what proves your type.

## Constitution (always): {con}

## Output
One line: `done -> .harness/progress/impl_<feature>.md` (or `blocked -> ...`). Never paste the diff.
"""


def _reviewer(role, meth, profile) -> str:
    ph = _phase_for(meth, "reviewer")
    # Only name a docs-parity check when the profile actually configures one. With no
    # `docs.sync_check`, emitting a placeholder string here reads to a live reviewer as a
    # runnable command it cannot find (issue #21) — so drop the clause entirely instead.
    sync = profile.get("docs", {}).get("sync_check")
    sync_clause = f" (incl. `{sync}`)" if sync else ""
    verify = profile.get("verify", {}).get("command", "the verify command")
    return f"""{_front(role, "Independent judge; re-runs gates; never fixes.")}
# reviewer (independent — fresh context)

{role['lens'].strip()}

## What you do
- **Read:** {', '.join(ph.get('reads', []))}, plus `.harness/profile.yaml` (`gate_profiles[<type>].review_passed`) and `.harness/CHECKPOINTS.md`.
- Re-run every gate yourself, in the FOREGROUND. **Mechanical gates are a DELTA**: if red both
  before AND after the change (stash + re-run), it is pre-existing — flag it, do not block.
- Check traceability (each `R<n>` → real evidence), placeholders, the constitution{sync_clause}, and `{verify}`.
- Walk CHECKPOINTS + the type's `review_passed`. Do NOT self-approve human gates (e.g. visual) — surface the evidence.

## Output
One line: `APPROVED -> .harness/progress/review_<feature>.md` or `CHANGES_REQUESTED -> ...`. Cite files+lines.
"""


_BUILDERS = {
    "leader": _leader,
    "spec_author": _spec_author,
    "implementer": _implementer,
    "reviewer": _reviewer,
}


def _roster(meth: dict) -> list[str]:
    names = {meth.get("orchestrator", "leader")}
    for ph in meth["phases"]:
        if ph["driver"] != "human":
            names.add(ph["driver"])
    return [n for n in ["leader", "spec_author", "implementer", "reviewer"] if n in names]


def _validate_roles(meth: dict, roles: dict) -> None:
    """Warn (stderr) about any role this host cannot render. Covers the phase drivers
    AND the escalation menu, so a dangling reference in either is surfaced, not dropped."""
    def renderable(name: str) -> bool:
        return name in _BUILDERS and name in roles

    for ph in meth["phases"]:
        drv = ph["driver"]
        if drv != "human" and not renderable(drv):
            why = "no builder" if drv not in _BUILDERS else "no role lens"
            _warn(f"phase driver '{drv}' cannot render ({why}); the phase will have no agent file.")

    for tier, names in (meth.get("escalation") or {}).items():
        for name in names:
            if name == "human" or renderable(name):
                continue
            why = "no builder" if name not in _BUILDERS else "no role lens"
            _warn(f"escalation.{tier} names '{name}' but it cannot render ({why}); fix the methodology or add the role.")


def _settings(profile: dict) -> str:
    sync = profile.get("docs", {}).get("sync_check")
    interp = profile.get("interpreter", "python3")
    allow = [f"Bash({interp} *)"]
    verify_cmd = (profile.get("verify", {}) or {}).get("command", "")
    verify_tok = verify_cmd.split()[0] if verify_cmd else ""
    if verify_tok:
        allow.append(f"Bash({verify_tok}*)")   # derived from the profile, not hardcoded
    if sync:
        allow.append(f"Bash({sync})")
    hooks: dict = {}
    if sync:
        hooks["Stop"] = [{
            "hooks": [{
                "type": "command",
                "command": f"{sync} 2>&1 | tail -5; echo '[harness] run the feature-type gate (profile.yaml) before marking done'",
                "description": "Constitution (delta-aware docs parity) + gate reminder before closing.",
            }]
        }]
    cfg = {
        "$comment": "Generated by method-based-harness. Hooks enforce the type-INDEPENDENT "
                    "constitution; type-specific gates are run by the drivers (foreground), "
                    "not hooks (a static hook can't be feature-type-aware).",
        "hooks": hooks,
        "permissions": {"allow": allow},
    }
    return json.dumps(cfg, indent=2) + "\n"


def _claude_block(meth: dict) -> str:
    orch = meth.get("orchestrator", "leader")
    return (
        f"{BEGIN}\n"
        f"## Active harness: {meth['name']}\n\n"
        f"This repo has a `{meth['id']}` harness under `.harness/`. When asked to build or change a\n"
        f"feature, act as the **`{orch}`** agent (`.claude/agents/{orch}.md`): orchestrate, never edit\n"
        f"`src/`/`tests/` yourself, and drive every feature through:\n\n"
        f"`{_flow(meth)}`\n\n"
        f"- Work items + status: `.harness/feature_list.json`\n"
        f"- Process: `.harness/methodology.md`; this repo's gate values: `.harness/profile.yaml`\n"
        f"- Definition of done: `.harness/CHECKPOINTS.md`\n\n"
        f"For pure questions or doc/config edits outside `src/`+`tests/`, answer directly. To\n"
        f"uninstall: delete `.harness/`, the `.claude/agents/*` role files, `.claude/settings.json`,\n"
        f"and this block.\n"
        f"{END}"
    )


def render(meth: dict, roles: dict, profile: dict, docs: dict):
    # imported here to avoid a circular import at module load
    from ..compile import RenderResult

    _validate_roles(meth, roles)

    files: dict[str, str] = {}
    for name in _roster(meth):
        role = roles.get(name)
        if role is None:
            _warn(f"roster role '{name}' has no lens (roles/{name}.role.yaml); skipping its agent file.")
            continue
        files[f".claude/agents/{name}.md"] = _BUILDERS[name](role, meth, profile)

    files[".claude/settings.json"] = _settings(profile)
    files[".harness/methodology.md"] = docs.get("methodology.md", "")
    files[".harness/CHECKPOINTS.md"] = docs.get("CHECKPOINTS.md", "")

    return RenderResult(
        files={k: v for k, v in files.items() if v != ""},
        block_path=".claude/CLAUDE.md",
        block_text=_claude_block(meth),
        block_markers=(BEGIN, END),
    )
