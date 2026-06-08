"""Issue #3 mechanics: adopting a manifest-less legacy install, and clean upgrade
propagation (the `update` classification).

These exercise two paths the other suites don't:
  - `init --force` over a repo whose managed files exist but has NO manifest (a repo
    that was hand-installed before manifests, or had .harness/.manifest.json deleted) —
    it adopts the files and writes a manifest that matches the render.
  - `upgrade` re-renders a managed file that is CLEAN (on disk == recorded hash) but
    whose render has since changed — propagation, distinct from the conflict path.

Both run in a chdir'd tmp repo (the `repo` fixture); the handlers read `Path.cwd()`.
"""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from harness import cli, manifest

MANAGED_SAMPLE = ".claude/agents/leader.md"


def _ns(**kw) -> Namespace:
    base = dict(methodology="sdd", host="claude", from_profile=None, dry_run=False, force=False)
    base.update(kw)
    return Namespace(**base)


def _init(profile_path: Path, **kw) -> int:
    return cli.cmd_init(_ns(from_profile=str(profile_path), **kw))


def _upgrade(**kw) -> int:
    return cli.cmd_upgrade(_ns(**kw))


def _manifest_matches_disk(repo: Path) -> bool:
    recorded = manifest.load(repo)
    assert recorded  # non-empty
    return all(manifest.hash_file(repo / rel) == h for rel, h in recorded.items())


# --- adopt: a manifest-less legacy install ----------------------------------------

def test_init_force_adopts_manifestless_install(repo: Path, profile_path: Path) -> None:
    # Stand up a real install, then simulate a "legacy" repo: managed files present on
    # disk with STALE content, and the manifest deleted entirely.
    assert _init(profile_path) == cli.EX_OK
    managed_rels = list(manifest.load(repo))
    for rel in managed_rels:
        (repo / rel).write_text("stale legacy content\n")
    (repo / manifest.MANIFEST_REL).unlink()
    assert not (repo / manifest.MANIFEST_REL).exists()

    # Bare init now refuses (files clash, no manifest to vouch for them).
    assert _init(profile_path) == cli.EX_FAIL

    # --force adopts: overwrites with the current render and re-writes the manifest.
    assert _init(profile_path, force=True) == cli.EX_OK
    assert (repo / manifest.MANIFEST_REL).is_file()
    assert _manifest_matches_disk(repo)
    assert (repo / MANAGED_SAMPLE).read_text() != "stale legacy content\n"
    # Once adopted, a follow-up upgrade is a clean no-op (no conflicts).
    before = (repo / MANAGED_SAMPLE).read_text()
    assert _upgrade() == cli.EX_OK
    assert (repo / MANAGED_SAMPLE).read_text() == before


# --- propagate: a clean managed file whose render moved on -------------------------

def test_upgrade_propagates_to_clean_stale_file(repo: Path, profile_path: Path) -> None:
    # A managed file that is CLEAN (disk == recorded) but whose render has drifted:
    # write stale content and record its hash, so classify() sees disk == recorded but
    # disk != render -> 'update'. No --force needed (this isn't a hand-edit conflict).
    assert _init(profile_path) == cli.EX_OK
    target = repo / MANAGED_SAMPLE
    rendered = target.read_text()

    stale = "stale but harness-managed\n"
    target.write_text(stale)
    managed = manifest.load(repo)
    managed[MANAGED_SAMPLE] = manifest.hash_text(stale)  # pretend the render produced this
    manifest.save(repo, managed, manifest.load_meta(repo))

    # Sanity: this is the 'update' bucket, not 'conflict'.
    assert manifest.classify(repo, MANAGED_SAMPLE, rendered, managed) == "update"

    assert _upgrade() == cli.EX_OK  # no --force
    assert target.read_text() == rendered  # propagated back to the real render
    assert manifest.load(repo)[MANAGED_SAMPLE] == manifest.hash_text(rendered)  # re-recorded
