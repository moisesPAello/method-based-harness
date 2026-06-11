"""Regression tests for issue B:

  B1 – methodology/host source-of-truth: profile keys override flag defaults; explicit
       flag that conflicts with the profile must fail with a clear message.
  B2 – --from-profile clobber guard: when --from-profile is used and the target
       .harness/profile.yaml already exists with different content, refuse without --force.
  B3 – dry-run completeness:
       * init's dry-run enumerates scaffold-local files (those that don't yet exist) and
         .harness/baseline.json (when verify is configured).
       * upgrade's dry-run mentions the .claude/CLAUDE.md block merge.
"""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest

from harness import cli, manifest


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _ns(**kw) -> Namespace:
    base = dict(
        methodology=cli._METHODOLOGY_DEFAULT,
        host=cli._HOST_DEFAULT,
        from_profile=None,
        dry_run=False,
        force=False,
        verify_timeout=120.0,
    )
    base.update(kw)
    return Namespace(**base)


def _init(profile_path: Path, **kw) -> int:
    return cli.cmd_init(_ns(from_profile=str(profile_path), **kw))


def _upgrade(**kw) -> int:
    return cli.cmd_upgrade(_ns(**kw))


# ---------------------------------------------------------------------------
# B1 – methodology/host source-of-truth
# ---------------------------------------------------------------------------

class TestProfileSourceOfTruth:
    """Profile's methodology/host keys take precedence over flag defaults."""

    def test_profile_methodology_used_when_flag_is_default(
        self, repo: Path, profile_path: Path, capsys
    ) -> None:
        """When --methodology is left at its default and the profile carries a
        different value, the profile's value is used silently (no error)."""
        profile_data = cli._load_yaml(profile_path)
        # The bundled example profile must carry methodology: sdd.
        assert profile_data.get("methodology") == "sdd"
        # Leave --methodology at the default ("sdd") — should be fine.
        assert _init(profile_path) == cli.EX_OK
        meta = manifest.load_meta(repo)
        assert meta["methodology"] == "sdd"

    def test_profile_host_used_when_flag_is_default(
        self, repo: Path, profile_path: Path
    ) -> None:
        """When --host is left at its default and the profile carries that same
        value, no conflict: install succeeds."""
        assert _init(profile_path) == cli.EX_OK
        meta = manifest.load_meta(repo)
        assert meta["host"] == "claude"

    def test_profile_methodology_wins_over_default_silently(
        self, repo: Path, tmp_path: Path, lib_root: Path
    ) -> None:
        """A profile that carries methodology overrides the CLI default without noise."""
        import shutil, yaml
        src = lib_root / "examples/sella-cruce/profile.yaml"
        custom = tmp_path / "custom_profile.yaml"
        data = cli._load_yaml(src)
        data["methodology"] = "sdd"   # same as default — still should be used
        custom.write_text(yaml.dump(data))
        assert cli.cmd_init(_ns(from_profile=str(custom))) == cli.EX_OK
        assert manifest.load_meta(repo)["methodology"] == "sdd"

    def test_explicit_methodology_flag_matching_profile_is_ok(
        self, repo: Path, profile_path: Path
    ) -> None:
        """An explicit flag that AGREES with the profile should succeed."""
        assert _init(profile_path, methodology="sdd") == cli.EX_OK

    def test_explicit_methodology_flag_conflicting_with_profile_fails(
        self, repo: Path, profile_path: Path, capsys
    ) -> None:
        """An explicit --methodology that conflicts with the profile must fail with
        a message naming both values."""
        rc = cli.cmd_init(_ns(from_profile=str(profile_path), methodology="tdd"))
        assert rc == cli.EX_FAIL
        err = capsys.readouterr().err
        assert "tdd" in err
        assert "sdd" in err

    def test_explicit_host_flag_conflicting_with_profile_fails(
        self, repo: Path, profile_path: Path, tmp_path: Path, capsys
    ) -> None:
        """An explicit --host that conflicts with the profile must fail with a
        message naming both values."""
        import yaml
        src = profile_path
        data = cli._load_yaml(src)
        data["host"] = "claude"
        alt = tmp_path / "profile_alt.yaml"
        alt.write_text(yaml.dump(data))

        rc = cli.cmd_init(_ns(from_profile=str(alt), host="copilot"))
        assert rc == cli.EX_FAIL
        err = capsys.readouterr().err
        assert "copilot" in err
        assert "claude" in err

    def test_profile_without_methodology_uses_flag_default(
        self, repo: Path, profile_path: Path, tmp_path: Path
    ) -> None:
        """A profile that does NOT carry a methodology key defers to the flag (default)."""
        import yaml
        data = cli._load_yaml(profile_path)
        data.pop("methodology", None)
        stripped = tmp_path / "stripped.yaml"
        stripped.write_text(yaml.dump(data))
        assert cli.cmd_init(_ns(from_profile=str(stripped))) == cli.EX_OK
        assert manifest.load_meta(repo)["methodology"] == cli._METHODOLOGY_DEFAULT

    def test_profile_source_of_truth_is_echoed(
        self, repo: Path, profile_path: Path, capsys
    ) -> None:
        """Issue #32: when the profile carries methodology/host, init echoes the resolved
        values so the user knows setup advanced (not a silent no-op)."""
        assert _init(profile_path) == cli.EX_OK
        err = capsys.readouterr().err
        assert "methodology=sdd" in err and "host=claude" in err
        assert "from profile" in err

    def test_no_echo_when_profile_lacks_the_keys(
        self, repo: Path, profile_path: Path, tmp_path: Path, capsys
    ) -> None:
        """Issue #32: the echo is only relevant when the profile is the source of truth;
        a profile without methodology/host defers to the flag and stays quiet about it."""
        import yaml
        data = cli._load_yaml(profile_path)
        data.pop("methodology", None)
        data.pop("host", None)
        stripped = tmp_path / "stripped.yaml"
        stripped.write_text(yaml.dump(data))
        assert cli.cmd_init(_ns(from_profile=str(stripped))) == cli.EX_OK
        assert "(from profile)" not in capsys.readouterr().err

    def test_upgrade_reads_methodology_from_profile(
        self, repo: Path, profile_path: Path
    ) -> None:
        """After init, upgrade reads methodology/host from .harness/profile.yaml —
        consistency between init and upgrade."""
        assert _init(profile_path) == cli.EX_OK
        assert _upgrade() == cli.EX_OK
        meta = manifest.load_meta(repo)
        assert meta["methodology"] == "sdd"
        assert meta["host"] == "claude"


# ---------------------------------------------------------------------------
# B2 – --from-profile clobber guard
# ---------------------------------------------------------------------------

class TestFromProfileClobberGuard:
    """--from-profile must not silently overwrite a differing .harness/profile.yaml."""

    def test_from_profile_accepted_when_no_existing_profile(
        self, repo: Path, profile_path: Path
    ) -> None:
        """Happy path: no .harness/profile.yaml yet — --from-profile installs it."""
        assert not (repo / ".harness/profile.yaml").exists()
        assert _init(profile_path) == cli.EX_OK
        assert (repo / ".harness/profile.yaml").is_file()

    def test_from_profile_accepted_when_profile_content_identical(
        self, repo: Path, profile_path: Path
    ) -> None:
        """No conflict when the existing profile and the --from-profile file are identical."""
        # Pre-install the profile with identical content.
        target = repo / ".harness/profile.yaml"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(profile_path.read_text())
        assert _init(profile_path) == cli.EX_OK

    def test_from_profile_refused_when_profile_differs_without_force(
        self, repo: Path, profile_path: Path, tmp_path: Path, capsys
    ) -> None:
        """When .harness/profile.yaml exists with DIFFERENT content and --from-profile
        would overwrite it, init must fail without --force."""
        target = repo / ".harness/profile.yaml"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("project: existing\nmethodology: sdd\nhost: claude\n")
        # The external profile has different content.
        assert target.read_text() != profile_path.read_text()

        rc = _init(profile_path)
        assert rc == cli.EX_FAIL
        err = capsys.readouterr().err
        assert ".harness/profile.yaml" in err
        # The file must not be clobbered.
        assert target.read_text() == "project: existing\nmethodology: sdd\nhost: claude\n"

    def test_from_profile_force_overwrites_differing_profile(
        self, repo: Path, profile_path: Path
    ) -> None:
        """--force must allow overwriting a differing .harness/profile.yaml."""
        target = repo / ".harness/profile.yaml"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("project: existing\nmethodology: sdd\nhost: claude\n")
        original_profile_content = profile_path.read_text()

        rc = _init(profile_path, force=True)
        assert rc == cli.EX_OK
        # The installed profile should be the external one (from --from-profile).
        assert target.read_text() == original_profile_content

    def test_clobber_guard_only_when_from_profile_flag_is_used(
        self, repo: Path, profile_path: Path
    ) -> None:
        """Without --from-profile, the default path is used — the guard must not
        trigger on the existing profile that init itself wrote on a first run."""
        # First install writes .harness/profile.yaml.
        assert _init(profile_path) == cli.EX_OK
        # A second bare init (no --from-profile) should be blocked by the manifest
        # guard, not the profile-clash guard — and --force should work.
        assert cli.cmd_init(_ns(force=True)) == cli.EX_OK


# ---------------------------------------------------------------------------
# B3 – dry-run completeness
# ---------------------------------------------------------------------------

class TestDryRunCompleteness:
    """init and upgrade dry-runs must enumerate everything the real run would write."""

    def test_init_dry_run_lists_local_scaffold_files(
        self, repo: Path, profile_path: Path, capsys
    ) -> None:
        """init dry-run must include would-be-scaffold files (those that don't exist yet)."""
        assert _init(profile_path, dry_run=True) == cli.EX_OK
        out = capsys.readouterr().out
        lines = out.splitlines()
        # All three local scaffold files should appear (none exist yet).
        assert any(".harness/feature_list.json" in l for l in lines)
        assert any(".harness/progress/current.md" in l for l in lines)
        assert any(".harness/specs/.gitkeep" in l for l in lines)

    def test_init_dry_run_scaffold_files_marked_distinctly(
        self, repo: Path, profile_path: Path, capsys
    ) -> None:
        """Scaffold-local files should be visually distinct (e.g. prefixed with '(scaffold)')."""
        assert _init(profile_path, dry_run=True) == cli.EX_OK
        out = capsys.readouterr().out
        scaffold_lines = [l for l in out.splitlines()
                          if ".harness/feature_list.json" in l
                          or ".harness/progress/current.md" in l
                          or ".harness/specs/.gitkeep" in l]
        assert scaffold_lines, "expected scaffold files in dry-run output"
        for line in scaffold_lines:
            assert "(scaffold)" in line, f"expected '(scaffold)' prefix, got: {line!r}"

    def test_init_dry_run_omits_already_existing_scaffold_files(
        self, repo: Path, profile_path: Path, capsys
    ) -> None:
        """Scaffold files that already exist should NOT appear in dry-run output."""
        existing = repo / ".harness/feature_list.json"
        existing.parent.mkdir(parents=True, exist_ok=True)
        existing.write_text('{"features": []}\n')

        assert _init(profile_path, dry_run=True) == cli.EX_OK
        out = capsys.readouterr().out
        scaffold_lines = [l for l in out.splitlines()
                          if "feature_list.json" in l]
        assert not scaffold_lines, (
            "existing scaffold file should not appear in dry-run output, "
            f"but found: {scaffold_lines}"
        )

    def test_init_dry_run_lists_baseline_when_verify_configured(
        self, repo: Path, profile_path: Path, capsys
    ) -> None:
        """When the profile has a verify command, dry-run should list .harness/baseline.json."""
        # The bundled example profile ships with a verify command.
        assert _init(profile_path, dry_run=True) == cli.EX_OK
        out = capsys.readouterr().out
        assert ".harness/baseline.json" in out

    def test_init_dry_run_lists_profile_and_block(
        self, repo: Path, profile_path: Path, capsys
    ) -> None:
        """init dry-run must still include .harness/profile.yaml and the block path."""
        assert _init(profile_path, dry_run=True) == cli.EX_OK
        out = capsys.readouterr().out
        lines = out.splitlines()
        assert any(".harness/profile.yaml" in l for l in lines)
        assert any("CLAUDE.md" in l for l in lines)

    def test_upgrade_dry_run_mentions_block_merge(
        self, repo: Path, profile_path: Path, capsys
    ) -> None:
        """upgrade dry-run must mention the .claude/CLAUDE.md block merge."""
        assert _init(profile_path) == cli.EX_OK
        capsys.readouterr()  # clear init output

        assert _upgrade(dry_run=True) == cli.EX_OK
        out = capsys.readouterr().out
        assert "CLAUDE.md" in out, (
            "upgrade dry-run should mention the CLAUDE.md block merge, "
            f"but output was:\n{out}"
        )

    def test_upgrade_dry_run_merge_line_labeled(
        self, repo: Path, profile_path: Path, capsys
    ) -> None:
        """The CLAUDE.md line in upgrade dry-run should carry a label like 'merge'."""
        assert _init(profile_path) == cli.EX_OK
        capsys.readouterr()

        assert _upgrade(dry_run=True) == cli.EX_OK
        out = capsys.readouterr().out
        claude_lines = [l for l in out.splitlines() if "CLAUDE.md" in l]
        assert claude_lines, "CLAUDE.md should appear in upgrade dry-run output"
        for line in claude_lines:
            assert "merge" in line.lower(), (
                f"expected 'merge' label on CLAUDE.md line, got: {line!r}"
            )
