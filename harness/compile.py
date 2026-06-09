"""Compiler: library (role lenses) + methodology (binding) + project profile -> host files.

`init`/`upgrade` are not file-copy — they RENDER. This module loads the library and
dispatches to a host renderer (hosts/<host>.py), which returns a RenderResult.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .hosts import claude


@dataclass
class RenderResult:
    # MANAGED files: relpath (from repo root) -> content. Overwritten on upgrade.
    files: dict[str, str] = field(default_factory=dict)
    # The orchestrator block to MERGE into the host instruction file (not a plain write).
    block_path: str = ""
    block_text: str = ""
    block_markers: tuple[str, str] = ("", "")


HOSTS = {"claude": claude.render}


def library_root() -> Path:
    """Where roles/ and methodologies/ live. Env override, else the bundled package data
    (`harness/library/`) so the tool carries its library when installed anywhere."""
    env = os.environ.get("HARNESS_LIBRARY")
    if env:
        return Path(env)
    from importlib.resources import files
    return Path(str(files("harness"))) / "library"


def load_roles(root: Path) -> dict[str, dict]:
    roles: dict[str, dict] = {}
    for f in sorted((root / "roles").glob("*.role.yaml")):
        d = yaml.safe_load(f.read_text())
        roles[d["id"]] = d
    return roles


def load_methodology(root: Path, mid: str) -> dict:
    f = root / "methodologies" / mid / "methodology.yaml"
    if not f.is_file():
        raise FileNotFoundError(f"no methodology '{mid}' (looked for {f})")
    return yaml.safe_load(f.read_text())


def library_doc(root: Path, mid: str, name: str) -> str:
    """Read a methodology's bundled file (methodology.md, methodology.yaml, CHECKPOINTS.md)
    as raw text — verbatim, so the structured source keeps its comments/order. '' if absent."""
    f = root / "methodologies" / mid / name
    return f.read_text() if f.is_file() else ""


def list_library(root: Path) -> dict[str, list[str]]:
    meths = [
        p.name for p in sorted((root / "methodologies").glob("*"))
        if (p / "methodology.yaml").is_file()
    ]
    return {"methodologies": meths, "hosts": sorted(HOSTS), "roles": sorted(load_roles(root))}


def render(methodology_id: str, profile: dict, host: str, root: Path | None = None) -> RenderResult:
    root = root or library_root()
    if host not in HOSTS:
        raise ValueError(f"unknown host '{host}' (have: {', '.join(sorted(HOSTS))})")
    meth = load_methodology(root, methodology_id)
    roles = load_roles(root)
    docs = {
        "methodology.md": library_doc(root, methodology_id, "methodology.md"),
        # The structured state machine, copied verbatim so an installed repo can read
        # phases/gates/states without importing the library (issue #23).
        "methodology.yaml": library_doc(root, methodology_id, "methodology.yaml"),
        "CHECKPOINTS.md": library_doc(root, methodology_id, "CHECKPOINTS.md"),
    }
    return HOSTS[host](meth, roles, profile, docs)


def merge_block(existing: str, block: str, begin: str, end: str) -> str:
    """Idempotently insert/replace a marked block. Never clobbers surrounding content.

    Raises ValueError for malformed marker states so callers can surface a clear
    message instead of silently producing corrupted output:
      - Only one of BEGIN / END is present (half-deleted by hand).
      - END appears before BEGIN (scrambled edit).
    """
    has_begin = begin in existing
    has_end = end in existing
    if has_begin != has_end:
        missing = "END" if has_begin else "BEGIN"
        present = "BEGIN" if has_begin else "END"
        raise ValueError(
            f"malformed harness block in target file: {present} marker found but "
            f"{missing} marker is missing. Repair or delete the block manually, "
            f"then re-run."
        )
    if has_begin and has_end:
        begin_idx = existing.index(begin)
        end_idx = existing.index(end)
        if end_idx < begin_idx:
            raise ValueError(
                "malformed harness block in target file: END marker appears before "
                "BEGIN marker (scrambled edit). Repair or delete the block manually, "
                "then re-run."
            )
        head = existing[:begin_idx]
        tail = existing[end_idx + len(end):]
        return head + block + tail
    sep = "" if existing.endswith("\n") or not existing else "\n"
    return existing + sep + "\n" + block + "\n"
