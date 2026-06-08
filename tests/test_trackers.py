"""Tracker adapter layer (issue #4): the optional backlog-edge seam.

No real network anywhere — the `github-issues` adapter takes an injectable `gh` runner
(mirroring how `cli._run_verify` is injectable), so these tests fake every `gh` call.

Coverage:
  - registry/dispatch (name resolution, default, unknown);
  - `tracker: none` is a complete no-op (default flows byte-for-byte unchanged);
  - github-issues intake seeds feature_list entries;
  - github-issues outtake closes a done feature's issue with artifact links;
  - graceful degradation when `gh` is missing/unauthenticated.
"""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import yaml

from harness import cli, compile as _compile, trackers
from harness.trackers import github_issues


# --- registry / dispatch ----------------------------------------------------------

def test_default_tracker_is_none():
    assert trackers.tracker_name({}) == "none"
    assert trackers.tracker_name({"tracker": None}) == "none"
    assert trackers.tracker_name("not a dict") == "none"


def test_get_tracker_none_is_noop_instance():
    t = trackers.get_tracker("none")
    assert t.intake(Path("/x"), {}) == []
    assert t.outtake(Path("/x"), {}, {"status": "done"}) is False


def test_get_tracker_resolves_github_issues():
    t = trackers.for_profile({"tracker": "github-issues"})
    assert isinstance(t, github_issues.GithubIssuesTracker)


def test_unknown_tracker_raises():
    try:
        trackers.get_tracker("jira")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "jira" in str(exc)


def test_known_trackers_lists_none_and_github():
    assert "none" in trackers.known_trackers()
    assert "github-issues" in trackers.known_trackers()


# --- validation -------------------------------------------------------------------

def test_validate_accepts_known_tracker(lib_root, profile_path):
    from harness import validate
    p = yaml.safe_load(profile_path.read_text())
    p["tracker"] = "github-issues"
    errs, _ = validate.validate_profile(p, _compile.load_methodology(lib_root, "sdd"))
    assert errs == []


def test_validate_rejects_unknown_tracker(lib_root, profile_path):
    from harness import validate
    p = yaml.safe_load(profile_path.read_text())
    p["tracker"] = "jira"
    errs, _ = validate.validate_profile(p, _compile.load_methodology(lib_root, "sdd"))
    assert any("tracker" in e for e in errs)


def test_validate_default_no_tracker_is_clean(lib_root, profile_path):
    # The bundled example sets no tracker key -> still clean (unchanged behavior).
    from harness import validate
    p = yaml.safe_load(profile_path.read_text())
    assert "tracker" not in p
    errs, warns = validate.validate_profile(p, _compile.load_methodology(lib_root, "sdd"))
    assert errs == [] and warns == []


# --- github-issues intake (faked gh) ----------------------------------------------

def _gh_runner(responses: dict):
    """Build a fake `gh` runner keyed by the subcommand verb (issue/auth)."""
    def run(argv, cwd):
        key = (argv[1], argv[2]) if len(argv) > 2 else (argv[1],)
        if argv[:3] == ["gh", "auth", "status"]:
            return responses.get("auth", SimpleNamespace(returncode=0, stdout="", stderr=""))
        if argv[:3] == ["gh", "issue", "list"]:
            return responses["list"]
        if argv[:3] == ["gh", "issue", "close"]:
            responses.setdefault("closed", []).append(argv)
            return responses.get("close", SimpleNamespace(returncode=0, stdout="", stderr=""))
        return SimpleNamespace(returncode=1, stdout="", stderr="unknown")
    return run


def test_intake_seeds_feature_dicts(monkeypatch, tmp_path):
    monkeypatch.setattr(github_issues.shutil, "which", lambda _: "/usr/bin/gh")
    issues = [{"number": 7, "title": "Add export", "labels": []},
              {"number": 9, "title": "Fix parser", "labels": []}]
    run = _gh_runner({"list": SimpleNamespace(returncode=0, stdout=json.dumps(issues), stderr="")})

    t = github_issues.GithubIssuesTracker()
    feats = t.intake(tmp_path, {"tracker": "github-issues"}, run=run)

    assert [f["id"] for f in feats] == ["issue-7", "issue-9"]
    assert all(f["status"] == "pending" for f in feats)
    assert feats[0]["source"] == {"tracker": "github-issues", "issue": 7}
    assert feats[1]["name"] == "Fix parser"


def test_intake_graceful_when_gh_missing(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(github_issues.shutil, "which", lambda _: None)
    t = github_issues.GithubIssuesTracker()
    assert t.intake(tmp_path, {"tracker": "github-issues"}, run=lambda *a: None) == []
    assert "not found" in capsys.readouterr().err


def test_intake_graceful_when_unauthenticated(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(github_issues.shutil, "which", lambda _: "/usr/bin/gh")
    run = _gh_runner({"auth": SimpleNamespace(returncode=1, stdout="", stderr="not logged in")})
    t = github_issues.GithubIssuesTracker()
    assert t.intake(tmp_path, {"tracker": "github-issues"}, run=run) == []
    assert "not authenticated" in capsys.readouterr().err


# --- github-issues outtake (faked gh) ---------------------------------------------

def test_outtake_closes_done_issue_with_artifact_links(monkeypatch, tmp_path):
    monkeypatch.setattr(github_issues.shutil, "which", lambda _: "/usr/bin/gh")
    # Lay down on-disk artifacts the closing comment should reference.
    (tmp_path / ".harness/specs/issue-7").mkdir(parents=True)
    (tmp_path / ".harness/progress").mkdir(parents=True)
    (tmp_path / ".harness/progress/review_issue-7.md").write_text("APPROVED\n")
    responses = {}
    run = _gh_runner(responses)

    feature = {"id": "issue-7", "status": "done",
               "source": {"tracker": "github-issues", "issue": 7}}
    t = github_issues.GithubIssuesTracker()
    assert t.outtake(tmp_path, {"tracker": "github-issues"}, feature, run=run) is True

    close_argv = responses["closed"][0]
    assert close_argv[:4] == ["gh", "issue", "close", "7"]
    comment = close_argv[close_argv.index("--comment") + 1]
    assert ".harness/specs/issue-7/" in comment
    assert ".harness/progress/review_issue-7.md" in comment


def test_outtake_is_noop_for_non_done_feature(tmp_path):
    t = github_issues.GithubIssuesTracker()
    feature = {"id": "issue-7", "status": "in_progress",
               "source": {"tracker": "github-issues", "issue": 7}}
    # run must never be called for a not-done feature.
    assert t.outtake(tmp_path, {}, feature, run=lambda *a: 1 / 0) is False


def test_outtake_is_noop_for_non_tracker_feature(tmp_path):
    t = github_issues.GithubIssuesTracker()
    feature = {"id": "F1", "status": "done"}  # no issue number anywhere
    assert t.outtake(tmp_path, {}, feature, run=lambda *a: 1 / 0) is False


# --- `tracker: none` is a complete no-op via the CLI ------------------------------

def _install(repo: Path, profile: dict) -> None:
    (repo / ".harness").mkdir(parents=True, exist_ok=True)
    (repo / ".harness/profile.yaml").write_text(yaml.safe_dump(profile))
    (repo / ".harness/feature_list.json").write_text(
        json.dumps({"features": [{"id": "F1", "status": "done"}]}, indent=2) + "\n")


def test_cli_tracker_none_is_noop(repo: Path):
    _install(repo, {"methodology": "sdd"})  # no tracker key -> none
    before = (repo / ".harness/feature_list.json").read_text()
    # If any gh code ran, this exploding runner would raise; it must never be reached.
    rc = cli.cmd_tracker(Namespace(_run=lambda *a: 1 / 0))
    assert rc == cli.EX_OK
    assert (repo / ".harness/feature_list.json").read_text() == before


def test_cli_tracker_explicit_none_is_noop(repo: Path):
    _install(repo, {"methodology": "sdd", "tracker": "none"})
    before = (repo / ".harness/feature_list.json").read_text()
    rc = cli.cmd_tracker(Namespace(_run=lambda *a: 1 / 0))
    assert rc == cli.EX_OK
    assert (repo / ".harness/feature_list.json").read_text() == before


# --- CLI tracker sync end-to-end with a faked gh ----------------------------------

def test_cli_tracker_sync_intake_and_outtake(repo: Path, monkeypatch):
    monkeypatch.setattr(github_issues.shutil, "which", lambda _: "/usr/bin/gh")
    _install(repo, {"methodology": "sdd", "tracker": "github-issues"})
    # F1 (done) has no issue -> outtake skips it; intake adds issue-7.
    issues = [{"number": 7, "title": "Add export", "labels": []}]
    responses = {"list": SimpleNamespace(returncode=0, stdout=json.dumps(issues), stderr="")}
    run = _gh_runner(responses)

    rc = cli.cmd_tracker(Namespace(_run=run))
    assert rc == cli.EX_OK

    data = json.loads((repo / ".harness/feature_list.json").read_text())
    ids = [f["id"] for f in data["features"]]
    assert "issue-7" in ids and "F1" in ids  # seeded, existing preserved


def test_cli_tracker_sync_outtake_closes_done_issue(repo: Path, monkeypatch):
    monkeypatch.setattr(github_issues.shutil, "which", lambda _: "/usr/bin/gh")
    (repo / ".harness").mkdir(parents=True, exist_ok=True)
    (repo / ".harness/profile.yaml").write_text(
        yaml.safe_dump({"methodology": "sdd", "tracker": "github-issues"}))
    (repo / ".harness/feature_list.json").write_text(json.dumps({"features": [
        {"id": "issue-3", "status": "done", "source": {"tracker": "github-issues", "issue": 3}},
    ]}, indent=2) + "\n")
    responses = {"list": SimpleNamespace(returncode=0, stdout="[]", stderr="")}
    run = _gh_runner(responses)

    rc = cli.cmd_tracker(Namespace(_run=run))
    assert rc == cli.EX_OK
    assert responses["closed"][0][:4] == ["gh", "issue", "close", "3"]


def test_cli_tracker_without_profile_fails(repo: Path):
    assert cli.cmd_tracker(Namespace(_run=None)) == cli.EX_FAIL


# --- the `none`-default render is byte-for-byte unchanged --------------------------

def test_render_with_no_tracker_is_unchanged(profile_path):
    """A profile with no tracker key must render identically to one explicitly `none`."""
    base = yaml.safe_load(profile_path.read_text())
    base.pop("tracker", None)
    none = dict(base, tracker="none")

    r_absent = _compile.render("sdd", base, "claude")
    r_none = _compile.render("sdd", none, "claude")
    assert r_absent.files == r_none.files
    # And the leader carries NO tracker section in either (opt-in only).
    assert "Backlog edge" not in r_absent.files[".claude/agents/leader.md"]


def test_render_with_github_tracker_adds_leader_section(profile_path):
    p = dict(yaml.safe_load(profile_path.read_text()), tracker="github-issues")
    r = _compile.render("sdd", p, "claude")
    leader = r.files[".claude/agents/leader.md"]
    assert "Backlog edge (tracker: github-issues)" in leader
    assert "harness tracker sync" in leader
