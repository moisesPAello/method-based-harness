"""`harness doctor` (issue #7): install health + baseline-gate snapshot.

Read-only w.r.t. managed files; writes only local .harness/baseline.json.
"""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from harness import cli


def _ns(**kw) -> Namespace:
    base = dict(methodology="sdd", host="claude", from_profile=None, dry_run=False, force=False)
    base.update(kw)
    return Namespace(**base)


def _install(profile_path: Path) -> None:
    assert cli.cmd_init(_ns(from_profile=str(profile_path))) == cli.EX_OK


def test_doctor_fails_when_not_installed(repo: Path):
    assert cli.cmd_doctor(Namespace(no_baseline=True)) == cli.EX_FAIL


def test_doctor_ok_on_clean_install(repo: Path, profile_path: Path):
    _install(profile_path)
    assert cli.cmd_doctor(Namespace(no_baseline=True)) == cli.EX_OK


def test_doctor_fails_on_missing_managed_file(repo: Path, profile_path: Path):
    _install(profile_path)
    (repo / ".claude/agents/leader.md").unlink()
    assert cli.cmd_doctor(Namespace(no_baseline=True)) == cli.EX_FAIL


def test_doctor_passes_with_warning_on_drift(repo: Path, profile_path: Path):
    _install(profile_path)
    # Simulate hand-editing: change the body but keep valid frontmatter so the file
    # still registers with the host.  Hash mismatch is a warn, not a hard FAIL.
    leader = repo / ".claude/agents/leader.md"
    original = leader.read_text()
    # Append a comment at the end — frontmatter stays intact, hash differs.
    leader.write_text(original + "\n<!-- hand-edited -->\n")
    assert cli.cmd_doctor(Namespace(no_baseline=True)) == cli.EX_OK


def test_doctor_is_read_only_on_managed_files(repo: Path, profile_path: Path):
    _install(profile_path)
    before = (repo / ".claude/agents/leader.md").read_text()
    cli.cmd_doctor(Namespace(no_baseline=True))
    assert (repo / ".claude/agents/leader.md").read_text() == before


def test_baseline_records_red_and_green_gates(tmp_path: Path):
    cli._write_baseline(tmp_path, {"docs": {"sync_check": "true"}})
    green = json.loads((tmp_path / ".harness/baseline.json").read_text())
    assert green["gates"]["docs_sync"]["red"] is False

    cli._write_baseline(tmp_path, {"docs": {"sync_check": "false"}})
    red = json.loads((tmp_path / ".harness/baseline.json").read_text())
    assert red["gates"]["docs_sync"]["red"] is True


def test_baseline_empty_when_no_sync_check(tmp_path: Path):
    gates = cli._write_baseline(tmp_path, {"docs": {}})
    assert gates == {}
    assert (tmp_path / ".harness/baseline.json").is_file()  # still writes the snapshot


# --- regression: init then doctor must not clobber the verify audit ---------------

def test_doctor_preserves_verify_audit_after_init(
    repo: Path, profile_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Running `doctor` (without --no-baseline) after `init` must NOT clobber the
    `verify` key that `_audit_verify_gate` wrote during init. This is the regression
    for the bug where `_write_baseline` rebuilt the dict from scratch, silently
    dropping any key it didn't own."""
    from types import SimpleNamespace

    # Stub _run_sync so doctor's docs-sync gate never spawns a real subprocess.
    def _fake_sync(command, cwd, timeout):
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(cli, "_run_sync", _fake_sync)

    # Install (conftest already stubs _run_verify; _audit_verify_gate records verify).
    _install(profile_path)

    # Verify that init wrote the verify audit into baseline.json.
    baseline_path = repo / ".harness/baseline.json"
    assert baseline_path.is_file(), "init must create .harness/baseline.json"
    after_init = json.loads(baseline_path.read_text())
    assert "verify" in after_init, "init must write 'verify' key into baseline.json"

    # Run doctor without --no-baseline.
    result = cli.cmd_doctor(Namespace(no_baseline=False))
    assert result == cli.EX_OK

    # The verify key must survive the doctor run.
    after_doctor = json.loads(baseline_path.read_text())
    assert "verify" in after_doctor, (
        "doctor must not clobber the 'verify' audit written by init"
    )
    assert after_doctor["verify"] == after_init["verify"]


# --- agent frontmatter registration checks (issue #13 follow-up) -----------------

def test_doctor_ok_agent_frontmatter_healthy(repo: Path, profile_path: Path):
    """A clean install has valid frontmatter on every agent file -> doctor passes."""
    _install(profile_path)
    assert cli.cmd_doctor(Namespace(no_baseline=True)) == cli.EX_OK


def test_doctor_fails_on_multiline_description(repo: Path, profile_path: Path):
    """An agent whose description wraps to a second line would be silently dropped by
    Claude Code's frontmatter parser.  doctor must catch this and return EX_FAIL."""
    _install(profile_path)
    # Inject a multi-line description into one agent file (simulates the bug from #13).
    agent_path = repo / ".claude/agents/leader.md"
    original = agent_path.read_text()
    # Replace the description line with a block scalar that spans two lines.
    corrupted = original.replace(
        "name: leader",
        "name: leader",
        1,
    )
    # Build a minimal broken frontmatter that has a literal newline in description.
    broken_front = "---\nname: leader\ndescription: |\n  Line one\n  Line two\ntools: Read, Glob\n---\n"
    # Replace only the frontmatter (everything up to the second ---).
    body_start = original.index("---", 3)  # skip the opening ---
    body = original[original.index("\n", body_start):]  # body after closing ---
    agent_path.write_text(broken_front + body)
    result = cli.cmd_doctor(Namespace(no_baseline=True))
    assert result == cli.EX_FAIL


def test_doctor_fails_on_missing_required_key(repo: Path, profile_path: Path):
    """An agent file whose frontmatter is missing 'tools' would not register."""
    _install(profile_path)
    agent_path = repo / ".claude/agents/reviewer.md"
    original = agent_path.read_text()
    # Drop the tools line from the frontmatter.
    lines = original.splitlines(keepends=True)
    fixed = [l for l in lines if not l.startswith("tools:")]
    agent_path.write_text("".join(fixed))
    assert cli.cmd_doctor(Namespace(no_baseline=True)) == cli.EX_FAIL


def test_doctor_fails_on_unparseable_frontmatter(repo: Path, profile_path: Path):
    """An agent file with malformed YAML frontmatter should fail doctor."""
    _install(profile_path)
    agent_path = repo / ".claude/agents/spec_author.md"
    original = agent_path.read_text()
    body_start = original.index("---", 3)
    body = original[original.index("\n", body_start):]
    broken = "---\nname: spec_author\ndescription: [unclosed bracket\ntools: Read\n---\n" + body
    agent_path.write_text(broken)
    assert cli.cmd_doctor(Namespace(no_baseline=True)) == cli.EX_FAIL


def test_frontmatter_ok_helper_single_line_passes():
    """Unit-test the shared helper directly: single-line description -> ok."""
    text = "---\nname: foo\ndescription: A short description.\ntools: Read\n---\n# body\n"
    ok, reason = cli._frontmatter_ok(text)
    assert ok is True
    assert reason == ""


def test_frontmatter_ok_helper_multiline_fails():
    """Unit-test the shared helper: multi-line description -> fail with reason."""
    text = "---\nname: foo\ndescription: |\n  Line one.\n  Line two.\ntools: Read\n---\n# body\n"
    ok, reason = cli._frontmatter_ok(text)
    assert ok is False
    assert "multi-line" in reason


def test_frontmatter_ok_helper_missing_key_fails():
    text = "---\nname: foo\ndescription: ok\n---\n# no tools key\n"
    ok, reason = cli._frontmatter_ok(text)
    assert ok is False
    assert "tools" in reason


def test_frontmatter_ok_helper_no_fence_fails():
    text = "# Just a markdown file with no frontmatter\n"
    ok, reason = cli._frontmatter_ok(text)
    assert ok is False


# --- .claude/CLAUDE.md block integrity checks ------------------------------------

def test_doctor_fails_when_claude_md_missing(repo: Path, profile_path: Path):
    """Installed harness with .claude/CLAUDE.md removed -> doctor FAIL."""
    _install(profile_path)
    (repo / ".claude/CLAUDE.md").unlink()
    assert cli.cmd_doctor(Namespace(no_baseline=True)) == cli.EX_FAIL


def test_doctor_fails_when_block_absent_from_claude_md(repo: Path, profile_path: Path):
    """CLAUDE.md exists but both markers were deleted -> doctor FAIL (install incomplete)."""
    _install(profile_path)
    claude_md = repo / ".claude/CLAUDE.md"
    from harness.hosts.claude import BEGIN, END
    original = claude_md.read_text()
    # Strip out the entire managed block, leaving only surrounding content.
    begin_idx = original.index(BEGIN)
    end_idx = original.index(END) + len(END)
    stripped = original[:begin_idx] + original[end_idx:]
    claude_md.write_text(stripped)
    assert cli.cmd_doctor(Namespace(no_baseline=True)) == cli.EX_FAIL


def test_doctor_fails_when_only_begin_marker_present(repo: Path, profile_path: Path):
    """CLAUDE.md has BEGIN but END was deleted by hand -> half-marker state -> FAIL."""
    _install(profile_path)
    claude_md = repo / ".claude/CLAUDE.md"
    from harness.hosts.claude import BEGIN, END
    original = claude_md.read_text()
    # Remove only the END marker.
    claude_md.write_text(original.replace(END, ""))
    assert cli.cmd_doctor(Namespace(no_baseline=True)) == cli.EX_FAIL


def test_doctor_fails_when_only_end_marker_present(repo: Path, profile_path: Path):
    """CLAUDE.md has END but BEGIN was deleted by hand -> half-marker state -> FAIL."""
    _install(profile_path)
    claude_md = repo / ".claude/CLAUDE.md"
    from harness.hosts.claude import BEGIN, END
    original = claude_md.read_text()
    # Remove only the BEGIN marker.
    claude_md.write_text(original.replace(BEGIN, ""))
    assert cli.cmd_doctor(Namespace(no_baseline=True)) == cli.EX_FAIL


def test_doctor_fails_when_markers_out_of_order(repo: Path, profile_path: Path):
    """END before BEGIN in CLAUDE.md -> scrambled edit -> FAIL."""
    _install(profile_path)
    claude_md = repo / ".claude/CLAUDE.md"
    from harness.hosts.claude import BEGIN, END
    # Build a file where END literally precedes BEGIN.
    claude_md.write_text(f"preamble\n{END}\nmiddle\n{BEGIN}\npostamble\n")
    assert cli.cmd_doctor(Namespace(no_baseline=True)) == cli.EX_FAIL


def test_doctor_ok_when_claude_md_block_intact(repo: Path, profile_path: Path):
    """Clean install has an intact CLAUDE.md block -> doctor passes."""
    _install(profile_path)
    assert cli.cmd_doctor(Namespace(no_baseline=True)) == cli.EX_OK
