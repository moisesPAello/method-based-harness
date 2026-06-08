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
    (repo / ".claude/agents/leader.md").write_text("hand edited\n")
    # drift is a warning, not a hard problem
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
