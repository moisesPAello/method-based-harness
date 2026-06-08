# Session Report — Issue #78: Footer detection on OCR'd PDFs

**Date:** 2026-06-08
**Repo:** `sella-cruce`
**Branch:** `main`
**Issue:** [#78](https://github.com/moisesPAello/sella-cruce/issues/78) — *Bug en detección de footer en pdfs OCR* (labels: `bug`, `sella_cruce`)
**Methodology:** Spec-Driven Development (SDD) harness under `.harness/`
**Outcome:** ✅ Fixed and driven through the full SDD cycle (spec → human approval → implement → independent review → done). Changes left **uncommitted** in the working tree.

---

## 1. Task

> "take an issue to work in"

From 11 open issues, **#78** was selected. The issue body was empty (title only), so the bug was diagnosed from the code.

---

## 2. Root cause

Footer / `end_of_movements` / `page_break_marker` / legend markers are matched via
`find_text_sequence_in_coords(coords, target_phrase)` in `file_toolbox/reader/utils.py`.

That function normalized both the target phrase and the coords tokens (`normalize_text` +
`_strip_punctuation`), then required **exact contiguous token-sequence equality**:

```python
if candidate == target_tokens:   # line ~52, the brittle check
```

OCR-extracted text is noisy — per-character substitutions (`O↔0`, `l↔1`, `rn↔m`), different
word splitting/merging, stray tokens. Any of these broke the exact match, so
`_detect_footer_area` (`parsers/bank_parser.py`, ~line 427) returned `None` on OCR'd pages.

**Consequence:** footers/legends were not ignored and pages past `end_of_movements` were not
skipped, polluting extraction on scanned/OCR'd statements.

All string-marker call sites flow through this single function:
`_match_marker_in_coords` (string branch), `_detect_footer_area`, `_detect_legend_areas`,
`get_ignored_areas_per_page` — all in `parsers/bank_parser.py`.

---

## 3. Fix

**One file changed:** `file_toolbox/reader/utils.py` (+27 / −2 lines). No `parsers/` edits, no
new dependency.

- Added module constant `SIMILARITY_THRESHOLD = 0.8`.
- Added private helper `_tokens_match(cand_tok, tgt_tok, threshold)`:
  - exact equality short-circuits → preserves clean-text behavior byte-for-byte;
  - else `difflib.SequenceMatcher(None, cand_tok, tgt_tok).ratio() >= threshold`;
  - target tokens of length ≤ 2 are **exact-only** (stopwords like `de`, `y` are brittle).
- In `find_text_sequence_in_coords`, replaced `candidate == target_tokens` with an
  **all-aligned-pairs** check via `_tokens_match`. Sliding window, contiguity, normalization,
  punctuation stripping, and bbox-envelope return are unchanged.

### Design rationale (the key judgment call)

- **Every** aligned token must pass — a single strong token cannot trigger a multi-token
  marker match. This is the primary false-positive guard.
- Threshold deliberately **tight (0.8)**. Per the repo constitution *"empty/incomplete data >
  invented data"*: a missed footer leaves mild noise in the table; a **false** footer
  truncates real movements (data loss). Bias toward missing over inventing.
- The **regex** marker path was intentionally left **unchanged** — loosening regexes to absorb
  OCR glyph confusions would broaden them unpredictably and raise false-positive risk.

Representative similarity ratios observed:
- `rnovimientos` / `movimientos` ≈ 0.87 → matches
- `totai` / `total` = 0.80 → matches (at boundary)
- `c0ntlnua` / `continua` = 0.75 (two substitutions) → **rejected** (intended conservative)
- `tarjeta` / `movimientos` ≈ 0.10 → rejected (R5 guard)

---

## 4. SDD trail (all artifacts on disk under `.harness/`)

| Phase | Driver | Artifact | Result |
|---|---|---|---|
| pending → spec_ready | spec_author | `specs/ocr_footer_detection/{requirements,design,tasks}.md` | R1–R8, T1–T8 |
| spec_ready → ⏸ HUMAN | human | — | **Approved** |
| in_progress | implementer | `progress/impl_ocr_footer_detection.md` + code/tests | 14 new tests, all green |
| in_review | reviewer (fresh context) | `progress/review_ocr_footer_detection.md` | **APPROVED** |
| → done | leader | `feature_list.json` status | `done` |

### Requirements (EARS)
- **R1/R2** — tolerant matching on OCR noise; contiguity preserved (non-adjacent tokens never stitched).
- **R3/R4** — no regression: clean exact matches unchanged; punctuation/empty-token handling unchanged.
- **R5/R6** — false-positive guard: beyond-threshold lookalikes → `None`; all-tokens-must-pass.
- **R7** — regex marker path left unchanged (scoped decision, with a no-regression test).
- **R8** — constitution: change confined to technical layer, no `fitz` in `parsers/`, no new dep, no fabricated dates, money untouched; in-memory tests only.

---

## 5. Verification

**Verify command for this feature:** `pytest -q -m "not visual"`
(NOT bare `pytest -q` — see pre-existing issue #1 below).

| | passed | skipped | failed | deselected |
|---|---|---|---|---|
| Before | 45 | 4 | 1 (pre-existing) | 28 |
| After | **59** | 4 | 1 (pre-existing) | 28 |

- +14 = the new tests in `tests/file_toolbox/test_fuzzy_marker_match.py`, all green.
- No new failures introduced.
- Reviewer independently re-ran all gates (foreground), confirmed module boundaries via
  `git diff --name-only`, confirmed the regex path byte-for-byte unchanged
  (`parsers/bank_parser.py:382-425`), and confirmed both pre-existing reds as deltas.

---

## 6. Pre-existing issues surfaced (OUT OF SCOPE — not fixed, confirmed as deltas)

These are **not** caused by this change (verified red both before and after by stashing the
change). Flagged for follow-up.

1. **`pytest -q` (bare) HANGS forever** — `tests/cruce_especifico/test_visual_cruce.py`
   (`@pytest.mark.visual`) spins at ~98% CPU indefinitely. This is what made the baseline
   appear "stuck" for ~9 minutes at the start of the session. The usable gate is
   `pytest -q -m "not visual"`. **The SDD mechanical gate (`pytest -q`) is unusable until this
   is fixed.** Strong candidate for its own issue.
2. **`tests/file_toolbox/test_ocr.py::test_sparse_mode_merges_ocr_without_duplicate` fails** —
   stale mock `_fake_ocr()` missing the `dpi` kwarg that `extract_words_ocr` now requires
   (`file_toolbox/reader/extract.py:162`).
3. **`python .github/scripts/check_docs_sync.py` exits 1** — reports `modules/web.md` content
   differs. Unrelated to this feature (no docs/CLI/parser surface changed here).

---

## 7. Working-tree changes (UNCOMMITTED)

```
 M file_toolbox/reader/utils.py                          # the fix (+27/−2)
?? tests/file_toolbox/test_fuzzy_marker_match.py          # 14 new tests
?? .harness/specs/ocr_footer_detection/                   # requirements/design/tasks
?? .harness/progress/impl_ocr_footer_detection.md
?? .harness/progress/review_ocr_footer_detection.md
   .harness/feature_list.json                             # feature id 2 → done
```

Suggested commit (Conventional Commits, Spanish, per repo standard):

```
fix(file_toolbox): tolerar ruido OCR en detección de footer
```

---

## 8. Suggested follow-ups

- **New issue:** the `@pytest.mark.visual` hang in `test_visual_cruce.py` (blocks the full-suite gate).
- **Quick fix:** the `dpi` kwarg stale mock in `test_ocr.py`.
- **Investigate:** `check_docs_sync.py` / `modules/web.md` drift.

---

*Generated by Claude Code (Opus 4.8) acting as the SDD `leader`, orchestrating spec_author →
implementer → reviewer subagents.*
