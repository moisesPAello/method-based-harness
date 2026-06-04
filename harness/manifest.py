"""Managed-file manifest: relpath -> content hash, for safe upgrades.

`upgrade` compares each managed file's on-disk hash against the manifest:
  - matches manifest  -> harness-managed, safe to overwrite with the new render;
  - differs           -> hand-edited since install, refuse unless --force;
  - absent            -> new managed file, write it.
Local/state files (feature_list, progress/, specs/, profile.yaml) are never managed.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

MANIFEST_REL = ".harness/.manifest.json"


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(root: Path) -> dict[str, str]:
    p = root / MANIFEST_REL
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text()).get("managed", {})
    except (ValueError, OSError):
        return {}


def load_meta(root: Path) -> dict:
    p = root / MANIFEST_REL
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text()).get("meta", {})
    except (ValueError, OSError):
        return {}


def save(root: Path, managed: dict[str, str], meta: dict) -> None:
    p = root / MANIFEST_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"meta": meta, "managed": managed}, indent=2) + "\n")


def classify(root: Path, relpath: str, new_content: str, prior: dict[str, str]) -> str:
    """Return one of: 'new', 'unchanged', 'update', 'conflict'.

    'conflict' = the file exists, was hand-edited since install (hash != manifest),
    and the new render differs from what's on disk.
    """
    target = root / relpath
    if not target.exists():
        return "new"
    on_disk = hash_file(target)
    if on_disk == hash_text(new_content):
        return "unchanged"
    recorded = prior.get(relpath)
    if recorded is not None and on_disk != recorded:
        return "conflict"
    return "update"
