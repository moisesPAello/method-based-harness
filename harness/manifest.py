"""Managed-file manifest: file -> content hash, for safe upgrades.

Lifted in spirit from the prior harness's core.py drift detection. `upgrade` compares
each managed file's on-disk hash against the manifest: unchanged -> overwrite with the
new render; changed (hand-edited) -> refuse unless --force. Local/state files
(feature_list, progress/, specs/, profile) are never managed.

Not implemented yet.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

MANIFEST_PATH = ".harness/.manifest.json"


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()
