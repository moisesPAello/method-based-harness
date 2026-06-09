"""compile.merge_block: idempotency and the outside-preserved / inside-overwritten rule."""

from __future__ import annotations

import pytest

from harness.compile import merge_block

BEGIN, END = "<!-- BEGIN -->", "<!-- END -->"


def _block(body: str) -> str:
    return f"{BEGIN}\n{body}\n{END}"


def test_insert_into_empty_file() -> None:
    out = merge_block("", _block("v1"), BEGIN, END)
    assert BEGIN in out and END in out and "v1" in out


def test_appends_with_separator_when_no_markers_present() -> None:
    out = merge_block("intro text", _block("v1"), BEGIN, END)
    assert out.startswith("intro text")
    assert _block("v1") in out


def test_idempotent_remerge_is_a_noop() -> None:
    once = merge_block("head\n", _block("v1"), BEGIN, END)
    twice = merge_block(once, _block("v1"), BEGIN, END)
    assert once == twice


def test_edit_outside_markers_is_preserved() -> None:
    existing = merge_block("# my heading\n", _block("v1"), BEGIN, END)
    # Human edits surrounding prose, then we re-merge an updated block.
    existing = existing.replace("# my heading", "# my EDITED heading")
    out = merge_block(existing, _block("v2"), BEGIN, END)
    assert "# my EDITED heading" in out


def test_edit_inside_markers_is_overwritten() -> None:
    existing = merge_block("head\n", _block("v1"), BEGIN, END)
    # Human tampers inside the managed region; the re-merge must replace it.
    existing = existing.replace("v1", "HAND EDITED v1")
    out = merge_block(existing, _block("v2"), BEGIN, END)
    assert "HAND EDITED" not in out
    assert "v2" in out


def test_remerge_keeps_a_single_block() -> None:
    out = merge_block("head\n", _block("v1"), BEGIN, END)
    out = merge_block(out, _block("v2"), BEGIN, END)
    assert out.count(BEGIN) == 1 and out.count(END) == 1


# --- half-deleted and scrambled marker error cases --------------------------------

def test_raises_when_only_begin_present() -> None:
    """User deleted END by hand — merge must refuse, not append a duplicate block."""
    existing = f"some text\n{BEGIN}\nold content\n"
    with pytest.raises(ValueError, match="END"):
        merge_block(existing, _block("v2"), BEGIN, END)


def test_raises_when_only_end_present() -> None:
    """User deleted BEGIN by hand — merge must refuse, not append a duplicate block."""
    existing = f"old content\n{END}\nmore text\n"
    with pytest.raises(ValueError, match="BEGIN"):
        merge_block(existing, _block("v2"), BEGIN, END)


def test_raises_when_end_before_begin() -> None:
    """Scrambled edit put END above BEGIN — merge must refuse, not produce garbled output."""
    existing = f"preamble\n{END}\nmiddle\n{BEGIN}\npostamble\n"
    with pytest.raises(ValueError, match="out of order|before BEGIN"):
        merge_block(existing, _block("v2"), BEGIN, END)


def test_error_message_mentions_repair() -> None:
    """The ValueError message should guide the user on how to fix the problem."""
    existing = f"{BEGIN}\nno closing marker"
    with pytest.raises(ValueError) as exc_info:
        merge_block(existing, _block("v2"), BEGIN, END)
    assert "manually" in str(exc_info.value).lower() or "repair" in str(exc_info.value).lower()
