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


def test_scaffold_detects_venv_and_pytest(repo: Path):
    (repo / ".venv/bin").mkdir(parents=True)
    (repo / ".venv/bin/python").write_text("")
    (repo / "tests").mkdir()
    cli._scaffold_profile(repo, "sdd")
    text = (repo / ".harness/profile.yaml").read_text()
    assert 'interpreter: ".venv/bin/python"' in text
    assert 'command: "pytest -q"' in text


def test_scaffold_defaults_when_nothing_detected(repo: Path):
    cli._scaffold_profile(repo, "sdd")
    doc = yaml.safe_load((repo / ".harness/profile.yaml").read_text())
    assert doc["interpreter"] == "python3"
    assert doc["verify"]["command"] == ""  # empty -> validator will require it


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
