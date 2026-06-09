"""Tracker adapters — the optional *backlog edge* between an external issue tracker
and the on-disk `feature_list.json`. Symmetric to `harness/hosts/`.

"Issues as the membrane, disk as the organ." On-disk state is the source of truth for
execution (state machine, gates, EARS traceability); a tracker only syncs the backlog
edge — intake (an issue seeds a feature) and outtake (reaching `done` closes the issue
with links to artifacts). The harness core path NEVER depends on a tracker:

  - `tracker: none` (default) — disk only; a complete no-op. Today's behavior, unchanged.
  - `tracker: github-issues` (opt-in) — shells out to `gh`; only ever runs when the
    profile explicitly selects it, and only from the leader/orchestrator path.

The interface every adapter implements (kept deliberately tiny):

    intake(root, profile, *, run=None) -> list[dict]
        Return feature dicts to seed into feature_list.json (caller merges + dedupes).
    outtake(root, profile, feature, *, run=None) -> bool
        React to a feature reaching `done` (e.g. close its issue with artifact links).
        Return True if it acted, False if it was a no-op. Never raises on tracker
        failure — degrades gracefully (clear error to stderr, disk state untouched).

`run` is an injectable subprocess runner (mirrors `cli._run_verify`) so tests can fake
`gh` without touching the network.
"""

from __future__ import annotations

import sys
from typing import Callable, Protocol

NONE = "none"


def _warn(msg: str) -> None:
    """Diagnostic to stderr (stdout is data); mirrors cli.log without importing it."""
    print(f"tracker: {msg}", file=sys.stderr)


class Tracker(Protocol):
    def intake(self, root, profile, *, run: Callable | None = ...) -> list[dict]: ...
    def outtake(self, root, profile, feature, *, run: Callable | None = ...) -> bool: ...


class _NoneTracker:
    """The default. Every operation is a no-op — disk stays the sole source of truth,
    and no network/auth/`gh` code is ever reached on the core path."""

    def intake(self, root, profile, *, run=None) -> list[dict]:
        return []

    def outtake(self, root, profile, feature, *, run=None) -> bool:
        return False


def _registry() -> dict[str, object]:
    # github_issues is imported lazily inside get_tracker so that selecting `none`
    # never imports the adapter module — the gh code path stays completely cold.
    return {NONE: _NoneTracker()}


def tracker_name(profile: dict) -> str:
    """The tracker a profile selects, defaulting to `none`. Tolerates a missing/None key."""
    return (profile.get("tracker") or NONE) if isinstance(profile, dict) else NONE


def known_trackers() -> list[str]:
    """Names a profile may select. Static (no import side effects) for validation/help."""
    return [NONE, "github-issues"]


def get_tracker(name: str):
    """Resolve a tracker by name. `none` (and anything falsy) -> the no-op tracker.
    Raises ValueError on an unknown name (validation should catch it earlier)."""
    if not name or name == NONE:
        return _NoneTracker()
    if name == "github-issues":
        from . import github_issues
        return github_issues.GithubIssuesTracker()
    raise ValueError(f"unknown tracker '{name}' (have: {', '.join(known_trackers())})")


def for_profile(profile: dict):
    """Convenience: the tracker instance a profile selects."""
    return get_tracker(tracker_name(profile))
