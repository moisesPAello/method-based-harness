"""Starter-profile generator (issue #2): `harness init` with no profile scaffolds one.

The scaffold leaves required fields empty so the #8 validator gates the re-run until the
user fills them — scaffold + validate compose into a guided fill-in loop.
"""

from __future__ import annotations

import shutil
from argparse import Namespace
from pathlib import Path

import yaml

from harness import cli
from harness import compile as _compile


def test_every_generated_agent_frontmatter_parses_as_yaml(profile_path: Path):
    """Regression (issue #6 run 2): spec_author's `lens:` first sentence wraps across two
    source lines; an unnormalized `description:` leaked the newline into the frontmatter,
    which the host parses as a stray key and silently drops the agent from the roster."""
    result = _compile.render("sdd", yaml.safe_load(profile_path.read_text()), "claude")
    agent_files = [f for f in result.files if f.endswith(".md") and "/agents/" in f]
    assert ".claude/agents/spec_author.md" in agent_files  # the role that broke
    for f in agent_files:
        head, fm_text, _ = result.files[f].split("---", 2)
        assert head.strip() == "", f"{f}: content before frontmatter fence"
        fm = yaml.safe_load(fm_text)  # raises yaml.YAMLError on a wrapped value
        assert {"name", "description", "tools"} <= fm.keys(), f"{f}: missing frontmatter keys"
        assert "\n" not in fm["description"], f"{f}: description spans multiple lines"


def _ns(**kw) -> Namespace:
    base = dict(methodology="sdd", host="claude", from_profile=None, dry_run=False, force=False)
    base.update(kw)
    return Namespace(**base)


def test_bare_init_scaffolds_then_gates_on_rerun(repo: Path):
    # 1. bare init in an empty repo writes a starter and stops
    assert cli.cmd_init(_ns()) == cli.EX_FAIL
    prof = repo / ".harness/profile.yaml"
    assert prof.is_file()
    doc = yaml.safe_load(prof.read_text())
    assert doc["methodology"] == "sdd"
    assert "default" in doc["gate_profiles"]
    # 2. re-running without editing is gated by validation (empty verify + gate slots)
    assert cli.cmd_init(_ns()) == cli.EX_FAIL
    assert not (repo / ".claude/agents/leader.md").exists()  # nothing installed


def test_first_run_hint_explains_the_validate_loop(repo: Path, capsys):
    """Issue #31: the first-run hint must tell the user that re-running validates and
    will list any TODO still empty — otherwise the (expected) second failure reads like
    a regression."""
    assert cli.cmd_init(_ns()) == cli.EX_FAIL  # bare init scaffolds + stops
    err = capsys.readouterr().err
    assert "re-run" in err and "harness init" in err
    assert "validate" in err.lower(), \
        f"first-run hint should say the re-run validates, got:\n{err}"


def test_scaffold_detects_venv_and_pytest(repo: Path):
    (repo / ".venv/bin").mkdir(parents=True)
    (repo / ".venv/bin/python").write_text("")
    (repo / "tests").mkdir()
    cli._scaffold_profile(repo, "sdd")
    text = (repo / ".harness/profile.yaml").read_text()
    assert 'interpreter: ".venv/bin/python"' in text
    assert 'command: "pytest -q"' in text


def test_scaffold_detects_windows_venv_layout(repo: Path):
    """Windows venvs put the interpreter at .venv/Scripts/python.exe; the probe must
    find it or the profile pins 'python3', which typically doesn't exist on Windows."""
    (repo / ".venv/Scripts").mkdir(parents=True)
    (repo / ".venv/Scripts/python.exe").write_text("")
    (repo / "tests").mkdir()
    cli._scaffold_profile(repo, "sdd")
    text = (repo / ".harness/profile.yaml").read_text()
    assert 'interpreter: ".venv/Scripts/python.exe"' in text


def test_scaffold_prefers_posix_venv_over_windows_when_both_exist(repo: Path):
    """Tie-break is declaration order: a repo with both layouts (e.g. shared via WSL)
    pins the POSIX path first."""
    for cand in (".venv/bin/python", ".venv/Scripts/python.exe"):
        p = repo / cand
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("")
    cli._scaffold_profile(repo, "sdd")
    text = (repo / ".harness/profile.yaml").read_text()
    assert 'interpreter: ".venv/bin/python"' in text


def test_scaffold_defaults_when_nothing_detected(repo: Path):
    cli._scaffold_profile(repo, "sdd")
    doc = yaml.safe_load((repo / ".harness/profile.yaml").read_text())
    assert doc["interpreter"] == "python3"
    assert doc["verify"]["command"] == ""  # empty -> validator will require it


def test_scaffold_exposes_docs_sync_check_slot(repo: Path):
    """Issue #22: the scaffold must surface an (optional) docs.sync_check slot so a
    first-time operator can discover that filling it wires the Stop docs-parity hook.
    Empty by default -> no hook wired (correct), but visible + documented."""
    cli._scaffold_profile(repo, "sdd")
    text = (repo / ".harness/profile.yaml").read_text()
    assert "Stop hook" in text, "scaffold does not explain the conditional Stop hook"
    doc = yaml.safe_load(text)
    assert "docs" in doc and doc["docs"].get("sync_check") == "", \
        "scaffold should ship an empty docs.sync_check slot (no hook until filled)"


def test_from_profile_missing_path_errors_without_scaffolding(repo: Path):
    assert cli.cmd_init(_ns(from_profile=str(repo / "nope.yaml"))) == cli.EX_FAIL
    assert not (repo / ".harness/profile.yaml").exists()  # did NOT scaffold where user pointed


def test_bare_init_uses_existing_profile_without_clobber(repo: Path, profile_path: Path):
    (repo / ".harness").mkdir()
    shutil.copy(profile_path, repo / ".harness/profile.yaml")
    original = (repo / ".harness/profile.yaml").read_text()
    assert cli.cmd_init(_ns()) == cli.EX_OK          # installs from the existing profile
    assert (repo / ".claude/agents/leader.md").is_file()
    assert original in (repo / ".harness/profile.yaml").read_text()  # not clobbered
