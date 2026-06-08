"""manifest.classify across all four states, plus the hash helpers it relies on."""

from __future__ import annotations

from pathlib import Path

from harness import manifest

RENDERED = "managed body\n"


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def test_hash_text_and_hash_file_agree(tmp_path: Path) -> None:
    p = tmp_path / "f.txt"
    p.write_text(RENDERED)
    assert manifest.hash_file(p) == manifest.hash_text(RENDERED)


def test_classify_new_when_absent(tmp_path: Path) -> None:
    assert manifest.classify(tmp_path, "a.md", RENDERED, prior={}) == "new"


def test_classify_unchanged_when_on_disk_matches_render(tmp_path: Path) -> None:
    _write(tmp_path, "a.md", RENDERED)
    prior = {"a.md": manifest.hash_text(RENDERED)}
    assert manifest.classify(tmp_path, "a.md", RENDERED, prior) == "unchanged"


def test_classify_update_when_render_changed_but_disk_untouched(tmp_path: Path) -> None:
    # On disk == what we last rendered (recorded), but the new render differs: clean update.
    _write(tmp_path, "a.md", RENDERED)
    prior = {"a.md": manifest.hash_text(RENDERED)}
    assert manifest.classify(tmp_path, "a.md", "new render\n", prior) == "update"


def test_classify_conflict_when_hand_edited(tmp_path: Path) -> None:
    # Disk differs from BOTH the recorded hash and the new render -> hand-edited.
    _write(tmp_path, "a.md", "hand edit\n")
    prior = {"a.md": manifest.hash_text(RENDERED)}
    assert manifest.classify(tmp_path, "a.md", "new render\n", prior) == "conflict"


def test_classify_edited_back_to_render_is_unchanged(tmp_path: Path) -> None:
    # Edited away from the recorded hash, but back to exactly the current render:
    # 'unchanged' wins over 'conflict' because nothing needs writing.
    _write(tmp_path, "a.md", RENDERED)
    prior = {"a.md": manifest.hash_text("an older render\n")}
    assert manifest.classify(tmp_path, "a.md", RENDERED, prior) == "unchanged"


def test_classify_update_when_no_prior_record(tmp_path: Path) -> None:
    # File present, no manifest entry, render differs -> not a conflict, just an update.
    _write(tmp_path, "a.md", "something\n")
    assert manifest.classify(tmp_path, "a.md", "new render\n", prior={}) == "update"


def test_save_load_roundtrip(tmp_path: Path) -> None:
    managed = {"a.md": manifest.hash_text(RENDERED)}
    meta = {"methodology": "sdd", "host": "claude", "tool_version": "0.0.1"}
    manifest.save(tmp_path, managed, meta)
    assert manifest.load(tmp_path) == managed
    assert manifest.load_meta(tmp_path) == meta


def test_load_missing_manifest_is_empty(tmp_path: Path) -> None:
    assert manifest.load(tmp_path) == {}
    assert manifest.load_meta(tmp_path) == {}
