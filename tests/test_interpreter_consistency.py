"""Tests for issue C — interpreter/verify handling consistency across audit, render, doctor.

Three sub-issues covered:
  C-1: audit pins pytest commands under the profile interpreter (as `<interp> -m pytest ...`)
  C-2: resolve_interpreter normalises empty/null values to "python3" everywhere
  C-3: doctor's verify-resolvability check also tries repo-relative paths
"""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness import cli
from harness._util import resolve_interpreter


# ---------------------------------------------------------------------------
# C-1: pytest pinning in _audit_verify_gate
# ---------------------------------------------------------------------------

def test_audit_pins_pytest_under_python_interpreter(repo: Path) -> None:
    """The canonical profile (pytest -q + .venv/bin/python) must run as
    `.venv/bin/python -m pytest -q`, NOT bare `pytest -q` from PATH."""
    seen: dict = {}

    def runner(cmd, cwd, timeout):
        seen["cmd"] = cmd
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    cli._audit_verify_gate(
        repo,
        {"interpreter": ".venv/bin/python", "verify": {"command": "pytest -q"}},
        timeout=5.0,
        runner=runner,
    )
    assert seen["cmd"] == ".venv/bin/python -m pytest -q"


def test_audit_pins_pytest_with_extra_args(repo: Path) -> None:
    """Extra pytest args must be preserved after the rewrite."""
    seen: dict = {}

    def runner(cmd, cwd, timeout):
        seen["cmd"] = cmd
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    cli._audit_verify_gate(
        repo,
        {"interpreter": ".venv/bin/python3", "verify": {"command": "pytest -q tests/"}},
        timeout=5.0,
        runner=runner,
    )
    assert seen["cmd"] == ".venv/bin/python3 -m pytest -q tests/"


def test_audit_does_not_rewrite_non_python_interpreter_pytest(repo: Path) -> None:
    """When the interpreter is not a python binary (e.g. 'node'), pytest is left alone."""
    seen: dict = {}

    def runner(cmd, cwd, timeout):
        seen["cmd"] = cmd
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    cli._audit_verify_gate(
        repo,
        {"interpreter": "node", "verify": {"command": "pytest -q"}},
        timeout=5.0,
        runner=runner,
    )
    # No rewrite — "node" is not a python interpreter.
    assert seen["cmd"] == "pytest -q"


def test_audit_pins_bare_python_command_as_before(repo: Path) -> None:
    """Rule 1 (bare python/python3) still works alongside the new pytest rule."""
    seen: dict = {}

    def runner(cmd, cwd, timeout):
        seen["cmd"] = cmd
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    cli._audit_verify_gate(
        repo,
        {"interpreter": ".venv/bin/python", "verify": {"command": "python -m mymodule"}},
        timeout=5.0,
        runner=runner,
    )
    assert seen["cmd"] == ".venv/bin/python -m mymodule"


# ---------------------------------------------------------------------------
# C-2: resolve_interpreter normalises falsy values
# ---------------------------------------------------------------------------

class TestResolveInterpreter:
    def test_explicit_path_returned_verbatim(self):
        assert resolve_interpreter({"interpreter": ".venv/bin/python"}) == ".venv/bin/python"

    def test_empty_string_falls_back_to_python3(self):
        assert resolve_interpreter({"interpreter": ""}) == "python3"

    def test_null_value_falls_back_to_python3(self):
        assert resolve_interpreter({"interpreter": None}) == "python3"

    def test_missing_key_falls_back_to_python3(self):
        assert resolve_interpreter({}) == "python3"

    def test_whitespace_only_falls_back_to_python3(self):
        assert resolve_interpreter({"interpreter": "   "}) == "python3"

    def test_normal_python3_returned_as_is(self):
        assert resolve_interpreter({"interpreter": "python3"}) == "python3"


def test_settings_with_empty_interpreter_does_not_produce_broken_permission(
    profile_path: Path,
) -> None:
    """A profile with interpreter: '' must not render Bash( *) or 'via ``'."""
    import yaml
    from harness.hosts import claude as claude_host

    profile = yaml.safe_load(profile_path.read_text())
    profile["interpreter"] = ""  # the problematic case

    settings_json = claude_host._settings(profile)
    settings = json.loads(settings_json)
    for perm in settings.get("permissions", {}).get("allow", []):
        # Bash( *) would be "Bash( *)" — the leading space from an empty interp
        assert not perm.startswith("Bash( "), (
            f"Empty interpreter produced broken permission: {perm!r}"
        )


def test_leader_with_empty_interpreter_does_not_produce_via_blank(
    lib_root: Path, profile_path: Path
) -> None:
    """leader.md must not contain 'via ``' (double-backtick empty) when interpreter is ''."""
    import yaml
    from harness import compile as _compile
    from harness.hosts import claude as claude_host

    profile = yaml.safe_load(profile_path.read_text())
    profile["interpreter"] = ""

    meth = _compile.load_methodology(lib_root, "sdd")
    roles = _compile.load_roles(lib_root)
    role = roles["leader"]
    leader_text = claude_host._leader(role, meth, profile)
    assert "via ``" not in leader_text, (
        "Empty interpreter produced 'via ``' in leader.md"
    )


# ---------------------------------------------------------------------------
# C-3: doctor verify-resolvability checks repo-relative path
# ---------------------------------------------------------------------------

def test_doctor_does_not_warn_for_repo_relative_verify_command(
    repo: Path, profile_path: Path, capsys
) -> None:
    """A verify command like `.venv/bin/pytest` that exists as a repo-relative path
    must NOT trigger the 'not found on PATH or in the repo' warning."""
    import yaml
    from argparse import Namespace

    # Install the harness first.
    from harness import cli
    assert cli.cmd_init(
        Namespace(
            methodology="sdd", host="claude",
            from_profile=str(profile_path),
            dry_run=False, force=False,
        )
    ) == cli.EX_OK

    # Create a fake .venv/bin/pytest in the repo so the file exists.
    fake_pytest = repo / ".venv/bin/pytest"
    fake_pytest.parent.mkdir(parents=True, exist_ok=True)
    fake_pytest.write_text("#!/bin/sh\nexec pytest \"$@\"\n")

    # Rewrite the profile to use a repo-relative verify command.
    prof = repo / ".harness/profile.yaml"
    text = prof.read_text()
    # Replace the verify command with a repo-relative path.
    import re
    text = re.sub(r'command: "pytest -q"', 'command: ".venv/bin/pytest -q"', text)
    prof.write_text(text)

    capsys.readouterr()  # flush
    cli.cmd_doctor(Namespace(no_baseline=True))
    err = capsys.readouterr().err
    # The warning should NOT appear for the verify command.
    assert ".venv/bin/pytest" not in err or "not found" not in err, (
        f"doctor spuriously warned about repo-relative verify command:\n{err}"
    )


def test_doctor_still_warns_for_truly_missing_verify_command(
    repo: Path, profile_path: Path, capsys
) -> None:
    """A verify command that doesn't exist anywhere should still produce a warning."""
    import re
    from argparse import Namespace

    assert cli.cmd_init(
        Namespace(
            methodology="sdd", host="claude",
            from_profile=str(profile_path),
            dry_run=False, force=False,
        )
    ) == cli.EX_OK

    prof = repo / ".harness/profile.yaml"
    text = prof.read_text()
    text = re.sub(r'command: "pytest -q"', 'command: "no-such-binary-xyz -q"', text)
    prof.write_text(text)

    capsys.readouterr()
    cli.cmd_doctor(Namespace(no_baseline=True))
    err = capsys.readouterr().err
    assert "no-such-binary-xyz" in err and "not found" in err
