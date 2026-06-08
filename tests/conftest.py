"""Shared fixtures: throwaway repos that drive the real init/upgrade flows offline.

The CLI handlers operate on `Path.cwd()`, so every test that touches a flow runs in a
chdir'd `tmp_path`. We render against the real bundled library (the default resolution
in `compile.library_root()`), seeding from the bundled example profile.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness import compile as _compile


@pytest.fixture
def lib_root() -> Path:
    """The real bundled library root (env override honoured by compile)."""
    return _compile.library_root()


@pytest.fixture
def profile_path(lib_root: Path) -> Path:
    return lib_root / "examples/sella-cruce/profile.yaml"


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty repo as the cwd, so the cli handlers act on it."""
    monkeypatch.chdir(tmp_path)
    return tmp_path
