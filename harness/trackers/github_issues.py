"""GitHub Issues tracker adapter (opt-in: `tracker: github-issues`).

Syncs only the BACKLOG EDGE between GitHub issues and `.harness/feature_list.json`:

  - intake:  open issues (optionally filtered by a label) seed feature_list entries.
  - outtake: a feature that reached `done` closes its issue with links to the spec /
             review artifacts on disk.

This module is imported ONLY when the profile opts into `github-issues` (the registry
imports it lazily). It shells out to `gh`; every `gh` call is wrapped so a missing or
unauthenticated CLI is a clear stderr warning and a graceful no-op — it NEVER raises
into the leader's flow and NEVER mutates on-disk state. Disk remains the organ.

The subprocess runner is injectable (`run=`) so tests fake `gh` without the network.
"""

from __future__ import annotations

import json
import shutil
import sys
from typing import Callable


def _warn(msg: str) -> None:
    print(f"tracker(github-issues): {msg}", file=sys.stderr)


def _default_run(argv: list[str], cwd) -> "object":
    """Run `gh` (or any argv) without a shell, capturing output. Injectable for tests."""
    import subprocess
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=30)


def _opts(profile: dict) -> dict:
    """Adapter options live under `tracker_options:` in the profile (all optional)."""
    o = profile.get("tracker_options") if isinstance(profile, dict) else None
    return o if isinstance(o, dict) else {}


class GithubIssuesTracker:
    name = "github-issues"

    # --- intake ------------------------------------------------------------------

    def intake(self, root, profile, *, run: Callable | None = None) -> list[dict]:
        """List open issues via `gh` and return them as feature dicts the caller can
        merge into feature_list.json. Returns [] (graceful) on any `gh` problem."""
        run = run or _default_run
        if not self._gh_available(run, root):
            return []

        opts = _opts(profile)
        argv = ["gh", "issue", "list", "--state", "open",
                "--json", "number,title,labels", "--limit", str(opts.get("limit", 100))]
        label = opts.get("label")
        if label:
            argv += ["--label", str(label)]

        proc = self._call(run, argv, root, what="list issues")
        if proc is None or proc.returncode != 0:
            if proc is not None:
                _warn(f"`gh issue list` failed (exit {proc.returncode}): "
                      f"{(proc.stderr or '').strip()}")
            return []
        try:
            issues = json.loads(proc.stdout or "[]")
        except ValueError as exc:
            _warn(f"could not parse `gh issue list` output: {exc}")
            return []

        features = []
        for issue in issues:
            num = issue.get("number")
            if num is None:
                continue
            features.append({
                "id": f"issue-{num}",
                "name": issue.get("title", f"issue {num}"),
                "status": "pending",
                "source": {"tracker": self.name, "issue": num},
            })
        return features

    # --- outtake -----------------------------------------------------------------

    def outtake(self, root, profile, feature, *, run: Callable | None = None) -> bool:
        """If `feature` reached `done` and carries an issue number, close that issue
        with a comment linking the on-disk spec/review artifacts. Returns True if it
        closed an issue, False otherwise (not done / not tracker-sourced / gh missing)."""
        run = run or _default_run
        if not isinstance(feature, dict) or feature.get("status") != "done":
            return False
        num = self._issue_number(feature)
        if num is None:
            return False
        if not self._gh_available(run, root):
            return False

        comment = self._closing_comment(root, feature)
        argv = ["gh", "issue", "close", str(num), "--comment", comment,
                "--reason", "completed"]
        proc = self._call(run, argv, root, what=f"close issue #{num}")
        if proc is None or proc.returncode != 0:
            if proc is not None:
                _warn(f"`gh issue close` failed (exit {proc.returncode}): "
                      f"{(proc.stderr or '').strip()} — disk state is unaffected.")
            return False
        return True

    # --- helpers -----------------------------------------------------------------

    @staticmethod
    def _issue_number(feature: dict):
        src = feature.get("source")
        if isinstance(src, dict) and src.get("tracker") == "github-issues":
            return src.get("issue")
        fid = str(feature.get("id") or "")
        if fid.startswith("issue-") and fid[len("issue-"):].isdigit():
            return int(fid[len("issue-"):])
        return None

    @staticmethod
    def _closing_comment(root, feature: dict) -> str:
        """A short closing note linking the artifacts that prove this feature done."""
        fid = feature.get("id") or feature.get("name") or "?"
        lines = [f"Closed by the harness: feature `{fid}` reached `done`.", "", "Artifacts:"]
        candidates = [
            f".harness/specs/{fid}/",
            f".harness/progress/impl_{fid}.md",
            f".harness/progress/review_{fid}.md",
        ]
        found = [c for c in candidates if (root / c).exists()]
        if found:
            lines += [f"- `{c}`" for c in found]
        else:
            lines.append("- (no on-disk artifacts located by path convention)")
        return "\n".join(lines)

    def _gh_available(self, run: Callable, root) -> bool:
        """True only if `gh` is on PATH AND authenticated. Either failure is a clear,
        non-fatal warning — the core path keeps working, disk untouched."""
        if shutil.which("gh") is None:
            _warn("`gh` not found on PATH — skipping tracker sync (disk state unchanged).")
            return False
        proc = self._call(run, ["gh", "auth", "status"], root, what="check auth")
        if proc is None or proc.returncode != 0:
            _warn("`gh` is not authenticated (`gh auth login`) — skipping tracker sync "
                  "(disk state unchanged).")
            return False
        return True

    def _call(self, run: Callable, argv: list[str], root, *, what: str):
        """Invoke the runner, turning any spawn/timeout error into a warning + None."""
        try:
            return run(argv, root)
        except Exception as exc:  # subprocess errors, OSError, timeout — all non-fatal
            _warn(f"could not {what} ({type(exc).__name__}: {exc}); skipping.")
            return None
