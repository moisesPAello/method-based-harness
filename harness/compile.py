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
    """Read a methodology's human doc (methodology.md, CHECKPOINTS.md). '' if absent."""
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
        "CHECKPOINTS.md": library_doc(root, methodology_id, "CHECKPOINTS.md"),
    }
    return HOSTS[host](meth, roles, profile, docs)


def merge_block(existing: str, block: str, begin: str, end: str) -> str:
    """Idempotently insert/replace a marked block. Never clobbers surrounding content."""
    if begin in existing and end in existing:
        head = existing[: existing.index(begin)]
        tail = existing[existing.index(end) + len(end):]
        return head + block + tail
    sep = "" if existing.endswith("\n") or not existing else "\n"
    return existing + sep + "\n" + block + "\n"
