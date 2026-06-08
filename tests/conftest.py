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


@pytest.fixture(autouse=True)
def _offline_verify_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the whole suite offline and instant: stub the init verify-gate runner so it
    never spawns the profile's real command (the bundled example ships `pytest -q`).
    Tests that exercise the audit explicitly install their own fake runner."""
    from types import SimpleNamespace

    from harness import cli

    def _fake(command, cwd, timeout):  # green, no-op
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(cli, "_run_verify", _fake)
