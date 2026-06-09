"""CLI UX regressions: dead flags removed, clean errors on malformed hand-edited files.

Issue E:
1. -v/--verbose and -q/--quiet were defined but never read.  They must be gone from --help.
2. cmd_status crashed with a raw traceback on malformed .harness/feature_list.json.
3. cmd_init / cmd_upgrade / cmd_doctor crashed with a raw traceback on a syntactically
   invalid .harness/profile.yaml.

All handlers operate on Path.cwd() (the `repo` fixture chdir's there).
`cli._run_verify` is stubbed suite-wide by conftest.
"""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest

from harness import cli


# ---------------------------------------------------------------------------
# 1.  Dead flags removed from --help
# ---------------------------------------------------------------------------

def test_build_parser_has_no_verbose_flag():
    p = cli.build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["-v"])


def test_build_parser_has_no_quiet_flag():
    p = cli.build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["-q"])


def test_help_text_does_not_advertise_verbose_or_quiet(capsys):
    p = cli.build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["--help"])
    out = capsys.readouterr().out
    assert "--verbose" not in out
    assert "--quiet" not in out


# ---------------------------------------------------------------------------
# 2.  cmd_status: clean error on malformed feature_list.json
# ---------------------------------------------------------------------------

def test_status_malformed_json_returns_ex_fail(repo: Path, capsys):
    fl = repo / ".harness/feature_list.json"
    fl.parent.mkdir(parents=True, exist_ok=True)
    fl.write_text("{not valid json\n")

    rc = cli.cmd_status(Namespace())

    assert rc == cli.EX_FAIL
    err = capsys.readouterr().err
    # One clean line naming the file and describing the problem — no traceback.
    assert "feature_list.json" in err
    assert "JSON" in err or "parse" in err.lower() or "json" in err.lower()


def test_status_truncated_json_returns_ex_fail(repo: Path, capsys):
    fl = repo / ".harness/feature_list.json"
    fl.parent.mkdir(parents=True, exist_ok=True)
    fl.write_text('{"features": [')  # truncated / unclosed array

    rc = cli.cmd_status(Namespace())

    assert rc == cli.EX_FAIL
    err = capsys.readouterr().err
    assert "feature_list.json" in err


# ---------------------------------------------------------------------------
# 3.  cmd_init / cmd_upgrade / cmd_doctor: clean error on invalid profile.yaml
# ---------------------------------------------------------------------------

def _write_broken_profile(repo: Path) -> None:
    prof = repo / ".harness/profile.yaml"
    prof.parent.mkdir(parents=True, exist_ok=True)
    prof.write_text("key: [\nunclosed bracket\n")  # syntactically invalid YAML


def _ns(**kw) -> Namespace:
    base = dict(methodology="sdd", host="claude", from_profile=None,
                dry_run=False, force=False)
    base.update(kw)
    return Namespace(**base)


def test_init_malformed_profile_yaml_returns_ex_fail(repo: Path, capsys):
    _write_broken_profile(repo)
    rc = cli.cmd_init(_ns(from_profile=str(repo / ".harness/profile.yaml")))

    assert rc == cli.EX_FAIL
    err = capsys.readouterr().err
    assert "profile.yaml" in err
    assert "YAML" in err or "parse" in err.lower() or "yaml" in err.lower()


def test_upgrade_malformed_profile_yaml_returns_ex_fail(repo: Path, capsys):
    _write_broken_profile(repo)
    rc = cli.cmd_upgrade(_ns())

    assert rc == cli.EX_FAIL
    err = capsys.readouterr().err
    assert "profile.yaml" in err
    assert "YAML" in err or "parse" in err.lower() or "yaml" in err.lower()


def test_doctor_malformed_profile_yaml_returns_ex_fail(repo: Path, capsys):
    _write_broken_profile(repo)
    rc = cli.cmd_doctor(Namespace(no_baseline=True))

    assert rc == cli.EX_FAIL
    err = capsys.readouterr().err
    assert "profile.yaml" in err
    assert "YAML" in err or "parse" in err.lower() or "yaml" in err.lower()
