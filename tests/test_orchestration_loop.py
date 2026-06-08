"""Orchestration-loop static validation (issue #6).

Grounded in the actual generated render, not the library source: asserts that
the checklist from issue #6 passes on the compiled output so regressions in
either the role lenses OR the host renderer are caught before a live session.

Checks:
  1. CLAUDE.md block names `leader` and instructs the session to lock to it.
  2. Every generated agent file (.claude/agents/*.md) has well-formed frontmatter
     (already in test_scaffold.py; repeated here for completeness as a named check).
  3. settings.json wires a Stop hook when a docs.sync_check is present; when absent
     (fresh bare profile) the hook dict is empty (not missing / not malformed).
  4. Folded-in fixes appear in the GENERATED agents, not just the library source:
     - reviewer: "foreground" + "delta"
     - leader:   "re-dispatch" + "wall-clock"
  5. SDD state machine expresses the human-approval pause (spec_ready → human → in_progress).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from harness import compile as _compile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _render(profile_path: Path) -> _compile.RenderResult:
    return _compile.render("sdd", yaml.safe_load(profile_path.read_text()), "claude")


def _agent(result: _compile.RenderResult, name: str) -> str:
    return result.files[f".claude/agents/{name}.md"]


def _frontmatter(text: str) -> dict:
    """Parse the YAML frontmatter from a generated agent file."""
    parts = text.split("---", 2)
    assert len(parts) >= 3 and not parts[0].strip(), "expected fenced frontmatter"
    return yaml.safe_load(parts[1])


# ---------------------------------------------------------------------------
# 1. CLAUDE.md block — session locked to leader
# ---------------------------------------------------------------------------

class TestClaudeMdBlock:
    def test_block_names_leader_agent(self, profile_path: Path):
        """The merged block must explicitly tell the session to act as `leader`.

        Evidence: block_text must contain the literal string 'leader' and reference
        .claude/agents/leader.md so the operator knows where to find the agent."""
        result = _render(profile_path)
        block = result.block_text
        assert "leader" in block, "block doesn't mention 'leader'"
        assert ".claude/agents/leader.md" in block, "block doesn't reference the leader agent file"

    def test_block_instructs_orchestrate_not_edit(self, profile_path: Path):
        """Block must tell the session to orchestrate, never edit src/tests directly."""
        result = _render(profile_path)
        block = result.block_text
        # The block says "orchestrate, never edit `src/`/`tests/` yourself"
        assert "orchestrate" in block.lower() or "orchestrat" in block.lower()

    def test_block_shows_human_pause_in_flow(self, profile_path: Path):
        """Block must show the ⏸ HUMAN pause so the operator sees the approval gate."""
        result = _render(profile_path)
        assert "⏸ HUMAN" in result.block_text or "HUMAN" in result.block_text

    def test_block_has_markers(self, profile_path: Path):
        result = _render(profile_path)
        begin, end = result.block_markers
        assert result.block_text.startswith(begin)
        assert result.block_text.rstrip().endswith(end)


# ---------------------------------------------------------------------------
# 2. Agent frontmatter — well-formed and registrable
# ---------------------------------------------------------------------------

class TestAgentFrontmatter:
    def test_all_agents_have_valid_frontmatter(self, profile_path: Path):
        """Every generated agent must have name/description/tools in parseable YAML.

        Regression for issue #9 (multi-line description silently drops agent from roster).
        All four SDD agents are checked."""
        result = _render(profile_path)
        agent_files = [f for f in result.files if f.endswith(".md") and "/agents/" in f]
        assert len(agent_files) >= 4, f"expected 4+ agents, got {len(agent_files)}"
        for fpath in agent_files:
            fm = _frontmatter(result.files[fpath])
            assert {"name", "description", "tools"} <= fm.keys(), \
                f"{fpath}: missing required frontmatter keys"
            assert isinstance(fm["description"], str), \
                f"{fpath}: description is not a string"
            assert "\n" not in fm["description"], \
                f"{fpath}: description spans multiple lines (would break host registration)"

    def test_spec_author_specifically_registers(self, profile_path: Path):
        """spec_author is the role whose long first sentence broke in issue #9."""
        result = _render(profile_path)
        assert ".claude/agents/spec_author.md" in result.files
        fm = _frontmatter(result.files[".claude/agents/spec_author.md"])
        assert fm["name"] == "spec_author"
        assert "\n" not in fm["description"]


# ---------------------------------------------------------------------------
# 3. settings.json — Stop hook wired when profile has sync_check; clean when absent
# ---------------------------------------------------------------------------

class TestSettingsJson:
    def test_settings_has_stop_hook_when_sync_check_present(self, profile_path: Path):
        """When the profile declares docs.sync_check the Stop hook must be wired.

        The sella-cruce fixture profile carries docs.sync_check."""
        import json
        result = _render(profile_path)
        settings = json.loads(result.files[".claude/settings.json"])
        hooks = settings.get("hooks", {})
        assert "Stop" in hooks, \
            "settings.json has no Stop hook even though profile has docs.sync_check"
        stop = hooks["Stop"]
        assert isinstance(stop, list) and len(stop) > 0

    def test_settings_hooks_empty_when_no_sync_check(self):
        """A bare profile (no docs.sync_check) must still produce valid JSON with an
        empty hooks dict — not absent or malformed."""
        import json
        bare_profile = {
            "project": "test",
            "methodology": "sdd",
            "host": "claude",
            "interpreter": "python3",
            "verify": {"command": "pytest -q"},
            "constitution": [],
            "gate_profiles": {
                "default": {
                    "impl_complete": ["tests pass"],
                    "review_passed": ["tests pass"],
                }
            },
        }
        result = _compile.render("sdd", bare_profile, "claude")
        settings = json.loads(result.files[".claude/settings.json"])
        assert "hooks" in settings, "settings.json must have a 'hooks' key"
        assert isinstance(settings["hooks"], dict)
        # No sync_check → no Stop hook → empty hooks dict (not missing)
        assert settings["hooks"] == {}, \
            "hooks should be empty when no docs.sync_check; got: " + str(settings["hooks"])

    def test_settings_is_valid_json(self, profile_path: Path):
        import json
        result = _render(profile_path)
        # If this raises, the test fails with a clear parse error
        settings = json.loads(result.files[".claude/settings.json"])
        assert isinstance(settings, dict)


# ---------------------------------------------------------------------------
# 4. Folded-in fixes appear in GENERATED agents
# ---------------------------------------------------------------------------

class TestFoldedInFixes:
    """Asserts that library fixes propagate into the compiled output.

    If these fail after a source edit, the fix was applied to the wrong layer
    (e.g. only in the host renderer, not the lens, or vice-versa)."""

    def test_reviewer_runs_foreground(self, profile_path: Path):
        """Fix for finding #5: reviewer must NOT spawn background gate waits."""
        rev = _agent(_render(profile_path), "reviewer")
        assert "foreground" in rev.lower(), \
            "reviewer.md does not carry the 'foreground' gate fix"

    def test_reviewer_uses_delta_gates(self, profile_path: Path):
        """Fix for finding #7: mechanical gates are a delta (pre-existing red ≠ block)."""
        rev = _agent(_render(profile_path), "reviewer")
        assert "delta" in rev.lower(), \
            "reviewer.md does not carry the 'delta' gate fix"

    def test_leader_redispatches_stalled_subagent(self, profile_path: Path):
        """Fix for finding #6: leader re-dispatches fresh (no resume promise)."""
        led = _agent(_render(profile_path), "leader")
        assert "re-dispatch" in led.lower(), \
            "leader.md does not carry the 're-dispatch' fix"

    def test_leader_has_wall_clock_bounded_gate(self, profile_path: Path):
        """Fix for finding #11: leader uses wall-clock cap, never polls a hung gate."""
        led = _agent(_render(profile_path), "leader")
        assert "wall-clock" in led.lower(), \
            "leader.md does not carry the 'wall-clock' bounded-gate fix"


# ---------------------------------------------------------------------------
# 5. SDD state machine — human-approval pause
# ---------------------------------------------------------------------------

class TestSddStateMachine:
    def test_methodology_yaml_has_human_phase(self):
        """The SDD library methodology must declare a human-driver phase between
        spec_ready and in_progress (the approval gate)."""
        meth = _compile.load_methodology(_compile.library_root(), "sdd")
        phases = meth.get("phases", [])
        human_phases = [p for p in phases if p.get("driver") == "human"]
        assert len(human_phases) >= 1, \
            "SDD methodology has no human-driver phase (human-approval pause missing)"

    def test_human_phase_is_between_spec_ready_and_in_progress(self):
        """The human gate must sit at spec_ready → human → in_progress, not elsewhere."""
        meth = _compile.load_methodology(_compile.library_root(), "sdd")
        phases = meth.get("phases", [])
        human_phases = [p for p in phases if p.get("driver") == "human"]
        assert len(human_phases) >= 1
        hp = human_phases[0]
        assert hp.get("state") == "spec_ready", \
            f"human phase starts at {hp.get('state')!r}, expected 'spec_ready'"
        assert hp.get("to") == "in_progress", \
            f"human phase leads to {hp.get('to')!r}, expected 'in_progress'"

    def test_flow_string_shows_human_pause(self, profile_path: Path):
        """The rendered flow string (embedded in leader.md + CLAUDE.md) must show
        the ⏸ HUMAN pause so no agent can miss the gate."""
        result = _render(profile_path)
        led = _agent(result, "leader")
        # The leader body embeds the flow string
        assert "⏸ HUMAN" in led, "leader.md flow string does not show ⏸ HUMAN pause"

    def test_leader_instructs_halt_and_ask_human(self, profile_path: Path):
        """Leader's dispatch instructions must tell it to STOP and ask the human
        after spec_ready — not auto-advance."""
        led = _agent(_render(profile_path), "leader")
        # "STOP and ask the human to approve" is the canonical phrasing
        assert "STOP" in led and ("human" in led.lower() or "approve" in led.lower()), \
            "leader.md does not tell the orchestrator to halt and ask a human to approve"


# ---------------------------------------------------------------------------
# 6. reviewer docs-parity clause — present only when configured (issue #21)
# ---------------------------------------------------------------------------

class TestReviewerDocsParityClause:
    """Regression for #21: when the profile has no `docs.sync_check`, the reviewer
    must NOT name a docs-parity check at all — the old renderer emitted a literal
    placeholder `the docs/parity check` that reads to a live reviewer as a runnable
    command it cannot find. When a sync_check IS configured, the reviewer names it."""

    def _reviewer_with(self, profile_path: Path, docs) -> str:
        profile = yaml.safe_load(profile_path.read_text())
        if docs is None:
            profile.pop("docs", None)
        else:
            profile["docs"] = docs
        return _compile.render("sdd", profile, "claude").files[".claude/agents/reviewer.md"]

    def test_no_placeholder_when_sync_check_absent(self, profile_path: Path):
        rev = self._reviewer_with(profile_path, docs=None)
        assert "the docs/parity check" not in rev, \
            "reviewer.md still emits the placeholder docs-parity string when none is configured"
        assert "(incl. ``)" not in rev and "(incl. `)" not in rev, \
            "reviewer.md emits an empty docs-parity clause"
        # the clause is dropped: constitution is followed directly by the verify check
        assert "the constitution," in rev

    def test_names_real_sync_check_when_present(self, profile_path: Path):
        rev = self._reviewer_with(profile_path, docs={"sync_check": "make docs-check"})
        assert "(incl. `make docs-check`)" in rev, \
            "reviewer.md does not name the configured docs.sync_check command"


# ---------------------------------------------------------------------------
# 7. structured state machine emitted into the installed repo (issue #23)
# ---------------------------------------------------------------------------

class TestMethodologyYamlEmitted:
    """Regression for #23: the render must emit `.harness/methodology.yaml` (the
    structured state machine) alongside the human-readable `.harness/methodology.md`,
    so agents/tooling can parse phases/gates/states from the installed repo without
    importing the library. The copy is verbatim (keeps comments/order)."""

    def test_methodology_yaml_is_emitted(self, profile_path: Path):
        result = _render(profile_path)
        assert ".harness/methodology.yaml" in result.files, \
            "render does not emit .harness/methodology.yaml"

    def test_methodology_yaml_parses_with_state_machine(self, profile_path: Path):
        result = _render(profile_path)
        meth = yaml.safe_load(result.files[".harness/methodology.yaml"])
        assert isinstance(meth, dict)
        assert {"phases", "states", "gates"} <= meth.keys(), \
            "emitted methodology.yaml is missing the structured state machine keys"

    def test_methodology_yaml_is_verbatim_library_copy(self, profile_path: Path, lib_root: Path):
        result = _render(profile_path)
        raw = (lib_root / "methodologies/sdd/methodology.yaml").read_text()
        assert result.files[".harness/methodology.yaml"] == raw, \
            "emitted methodology.yaml diverges from the library source (should be verbatim)"
