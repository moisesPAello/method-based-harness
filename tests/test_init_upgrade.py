"""init/upgrade flows end-to-end against the real bundled library, in throwaway repos.

Driven through the cli handlers (not `main`, which calls `sys.exit`) with argparse-style
namespaces. Each test runs in a chdir'd tmp repo (the `repo` fixture) because the handlers
read `Path.cwd()`.
"""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from harness import cli, manifest

MANAGED_SAMPLE = ".claude/agents/leader.md"


def _ns(**kw) -> Namespace:
    base = dict(methodology="sdd", host="claude", from_profile=None, dry_run=False, force=False)
    base.update(kw)
    return Namespace(**base)


def _init(repo: Path, profile_path: Path, **kw) -> int:
    return cli.cmd_init(_ns(from_profile=str(profile_path), **kw))


def _upgrade(repo: Path, **kw) -> int:
    return cli.cmd_upgrade(_ns(**kw))


# --- init -------------------------------------------------------------------------

def test_init_installs_managed_files_and_manifest(repo: Path, profile_path: Path) -> None:
    assert _init(repo, profile_path) == cli.EX_OK
    assert (repo / MANAGED_SAMPLE).is_file()
    assert (repo / ".claude/settings.json").is_file()
    assert (repo / ".harness/profile.yaml").is_file()
    assert (repo / manifest.MANIFEST_REL).is_file()
    # The manifest records each managed file's render hash.
    recorded = manifest.load(repo)
    assert recorded
    for rel, h in recorded.items():
        assert manifest.hash_file(repo / rel) == h
    # The orchestrator block was merged into CLAUDE.md.
    assert "METHOD-HARNESS:BEGIN" in (repo / ".claude/CLAUDE.md").read_text()


def test_init_scaffolds_local_state(repo: Path, profile_path: Path) -> None:
    _init(repo, profile_path)
    assert (repo / ".harness/feature_list.json").is_file()
    assert (repo / ".harness/progress/current.md").is_file()
    assert (repo / ".harness/specs/.gitkeep").is_file()
    # Local state is NOT in the managed manifest.
    assert ".harness/feature_list.json" not in manifest.load(repo)


def test_init_refuses_existing_install_without_force(repo: Path, profile_path: Path) -> None:
    assert _init(repo, profile_path) == cli.EX_OK
    assert _init(repo, profile_path) == cli.EX_FAIL  # manifest already present
    assert _init(repo, profile_path, force=True) == cli.EX_OK


def test_init_refuses_to_clobber_preexisting_managed_file(repo: Path, profile_path: Path) -> None:
    # A repo being adopted that already has a file the render would manage, but no manifest.
    target = repo / MANAGED_SAMPLE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("pre-existing hand-written content\n")

    assert _init(repo, profile_path) == cli.EX_FAIL
    assert target.read_text() == "pre-existing hand-written content\n"  # untouched
    assert not (repo / manifest.MANIFEST_REL).exists()  # nothing installed

    # --force adopts/overwrites it.
    assert _init(repo, profile_path, force=True) == cli.EX_OK
    assert target.read_text() != "pre-existing hand-written content\n"


def test_init_dry_run_writes_nothing(repo: Path, profile_path: Path) -> None:
    assert _init(repo, profile_path, dry_run=True) == cli.EX_OK
    assert not (repo / manifest.MANIFEST_REL).exists()
    assert not (repo / MANAGED_SAMPLE).exists()


def test_init_with_no_profile_scaffolds_a_starter(repo: Path) -> None:
    # Bare init with no profile writes a starter and stops (not installed yet).
    assert cli.cmd_init(_ns(from_profile=None)) == cli.EX_FAIL
    assert (repo / ".harness/profile.yaml").is_file()


# --- upgrade ----------------------------------------------------------------------

def test_upgrade_is_noop_on_a_fresh_install(repo: Path, profile_path: Path) -> None:
    _init(repo, profile_path)
    before = (repo / MANAGED_SAMPLE).read_text()
    assert _upgrade(repo) == cli.EX_OK
    assert (repo / MANAGED_SAMPLE).read_text() == before


def test_upgrade_refuses_hand_edited_managed_file_without_force(repo: Path, profile_path: Path) -> None:
    _init(repo, profile_path)
    # Force a real divergence: edit the file AND make the render differ from disk by
    # rewriting the manifest hash to a stale value so classify sees a conflict.
    target = repo / MANAGED_SAMPLE
    target.write_text("HAND EDITED leader\n")

    assert _upgrade(repo) == cli.EX_FAIL  # conflict: disk != render and != recorded
    assert target.read_text() == "HAND EDITED leader\n"  # not clobbered


def test_upgrade_force_overwrites_hand_edited_managed_file(repo: Path, profile_path: Path) -> None:
    _init(repo, profile_path)
    target = repo / MANAGED_SAMPLE
    original = target.read_text()
    target.write_text("HAND EDITED leader\n")

    assert _upgrade(repo, force=True) == cli.EX_OK
    assert target.read_text() == original  # re-rendered back


def test_upgrade_preserves_local_state(repo: Path, profile_path: Path) -> None:
    _init(repo, profile_path)
    fl = repo / ".harness/feature_list.json"
    fl.write_text('{"features": ["edited by human"]}\n')
    assert _upgrade(repo) == cli.EX_OK
    assert fl.read_text() == '{"features": ["edited by human"]}\n'


def test_upgrade_prunes_clean_orphan(repo: Path, profile_path: Path) -> None:
    _init(repo, profile_path)
    # Inject an orphan: a managed file no longer in the render, on disk == recorded hash.
    orphan_rel = ".claude/agents/obsolete.md"
    orphan = repo / orphan_rel
    orphan.write_text("obsolete role\n")
    managed = manifest.load(repo)
    managed[orphan_rel] = manifest.hash_text("obsolete role\n")
    manifest.save(repo, managed, manifest.load_meta(repo))

    assert _upgrade(repo) == cli.EX_OK
    assert not orphan.exists()  # pruned
    assert orphan_rel not in manifest.load(repo)


def test_upgrade_keeps_hand_edited_orphan_without_force(repo: Path, profile_path: Path) -> None:
    _init(repo, profile_path)
    orphan_rel = ".claude/agents/obsolete.md"
    orphan = repo / orphan_rel
    orphan.write_text("hand edited orphan\n")
    managed = manifest.load(repo)
    managed[orphan_rel] = manifest.hash_text("ORIGINAL orphan render\n")  # disk != recorded
    manifest.save(repo, managed, manifest.load_meta(repo))

    assert _upgrade(repo) == cli.EX_OK
    assert orphan.read_text() == "hand edited orphan\n"  # kept


def test_upgrade_force_removes_hand_edited_orphan(repo: Path, profile_path: Path) -> None:
    _init(repo, profile_path)
    orphan_rel = ".claude/agents/obsolete.md"
    orphan = repo / orphan_rel
    orphan.write_text("hand edited orphan\n")
    managed = manifest.load(repo)
    managed[orphan_rel] = manifest.hash_text("ORIGINAL orphan render\n")  # disk != recorded
    manifest.save(repo, managed, manifest.load_meta(repo))

    assert _upgrade(repo, force=True) == cli.EX_OK
    assert not orphan.exists()  # removed under --force


def test_upgrade_without_profile_fails(repo: Path) -> None:
    assert _upgrade(repo) == cli.EX_FAIL  # no .harness/profile.yaml


def test_upgrade_dry_run_writes_nothing(repo: Path, profile_path: Path) -> None:
    _init(repo, profile_path)
    target = repo / MANAGED_SAMPLE
    target.write_text("HAND EDITED leader\n")
    assert _upgrade(repo, dry_run=True) == cli.EX_OK
    assert target.read_text() == "HAND EDITED leader\n"  # untouched by dry-run
