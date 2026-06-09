"""Command-line surface for the harness installer.

Trust posture: WRITE. Mutates the target repo (compiles the library + the repo's
profile into host-native files). Not untrusted-input: the library is bundled and the
only external reads are the user's own repo files (for the manifest / merge).

    harness init     --methodology ID --host ID [--from-profile P] [--dry-run] [--force]
                     [--verify-timeout SECS]
    harness upgrade  [--dry-run] [--force]
    harness list     [methodologies|hosts|roles]
    harness status
    harness doctor   [--no-baseline]
    harness selftest

I/O: stdout is data (changed-file list, the listing), stderr is logs (progress,
verdicts, warnings). Exit 0 ok, non-zero failure; `upgrade` exits non-zero when it
refuses a hand-edited managed file (use --force).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from ._util import resolve_interpreter

EX_OK, EX_FAIL, EX_USAGE = 0, 1, 2


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def out(msg: str) -> None:
    print(msg)


# --- helpers ----------------------------------------------------------------------

def _frontmatter_ok(text: str) -> tuple[bool, str]:
    """Validate that *text* starts with a ``---``-fenced YAML block that would
    register as a Claude Code agent (i.e. parses cleanly as a mapping carrying
    ``name``, ``description``, and ``tools``, with ``description`` on a single
    line).

    Returns ``(True, "")`` on success, ``(False, reason)`` on any failure.
    Mirrors the static check in ``cmd_selftest`` but surfaces a human-readable
    reason so ``cmd_doctor`` can cite both the file and the exact problem.
    """
    import yaml

    parts = text.split("---", 2)
    if len(parts) < 3 or parts[0].strip():
        return False, "frontmatter block not found (file must start with '---')"
    try:
        fm = yaml.safe_load(parts[1])
    except yaml.YAMLError as exc:
        return False, f"frontmatter YAML parse error: {exc}"
    if not isinstance(fm, dict):
        return False, "frontmatter did not parse as a YAML mapping"
    missing = {"name", "description", "tools"} - fm.keys()
    if missing:
        return False, f"frontmatter missing required key(s): {', '.join(sorted(missing))}"
    desc = fm.get("description", "")
    if isinstance(desc, str) and "\n" in desc:
        return False, "description is multi-line (would be dropped by the host's frontmatter parser)"
    return True, ""


def _load_yaml(path: Path) -> dict:
    import yaml
    return yaml.safe_load(path.read_text())


def _load_features(root: Path) -> list:
    """Best-effort read of the feature list (for profile cross-checks). [] if absent/bad."""
    import json
    fl = root / ".harness/feature_list.json"
    if not fl.is_file():
        return []
    try:
        return json.loads(fl.read_text()).get("features", []) or []
    except (ValueError, OSError):
        return []


def _write(root: Path, relpath: str, content: str) -> None:
    p = root / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def _scaffold_local(root: Path, profile: dict) -> list[str]:
    """Create LOCAL state files if absent (never overwritten on upgrade)."""
    import json
    written = []
    fl = root / ".harness/feature_list.json"
    if not fl.exists():
        tmpl = {
            "project": profile.get("project", root.name),
            "methodology": profile.get("methodology", "sdd"),
            "rules": {
                "one_feature_at_a_time": True,
                "require_approved_spec_to_implement": True,
                "valid_status": ["pending", "spec_ready", "in_progress", "in_review", "done", "blocked"],
            },
            "features": [],
        }
        _write(root, ".harness/feature_list.json", json.dumps(tmpl, indent=2) + "\n")
        written.append(".harness/feature_list.json")
    cur = root / ".harness/progress/current.md"
    if not cur.exists():
        _write(root, ".harness/progress/current.md", "# Current session\n\nFeature: (none active)\n\n## Plan\n\n## Notes\n")
        written.append(".harness/progress/current.md")
    keep = root / ".harness/specs/.gitkeep"
    if not keep.exists():
        _write(root, ".harness/specs/.gitkeep", "")
        written.append(".harness/specs/.gitkeep")
    return written


def _mentions_pytest(root: Path) -> bool:
    """Cheap signal that this repo's verify command is probably pytest."""
    for fn in ("pyproject.toml", "setup.cfg", "tox.ini", "requirements.txt"):
        p = root / fn
        if p.is_file():
            try:
                if "pytest" in p.read_text():
                    return True
            except OSError:
                pass
    return False


def _scaffold_profile(root: Path, methodology_id: str) -> str:
    """Write a commented starter .harness/profile.yaml for `methodology_id`: best-effort
    detected interpreter/verify, and EMPTY gate slots so the profile fails validation until
    filled (scaffold + validate compose into a guided fill-in loop). Returns the relpath.
    Caller guarantees the file is absent — this never clobbers."""
    from . import compile as _compile
    interp = "python3"
    for cand in (".venv/bin/python", "venv/bin/python"):
        if (root / cand).exists():
            interp = cand
            break
    verify = "pytest -q" if ((root / "tests").is_dir() or _mentions_pytest(root)) else ""
    verify_line = (f'  command: "{verify}"          # detected' if verify else
                   '  command: ""                 # TODO: the command that proves a change is safe')
    try:
        meth = _compile.load_methodology(_compile.library_root(), methodology_id)
        slots = [n for n, g in (meth.get("gates") or {}).items()
                 if isinstance(g, dict) and g.get("class") == "per-type"]
    except FileNotFoundError:
        slots = ["impl_complete", "review_passed"]
    slot_block = "\n".join(f"    {s}: []          # TODO: checkable conditions for `{s}`"
                           for s in slots) or "    # this methodology declares no per-type gates"
    content = (
        f"# .harness/profile.yaml — this repo's binding for the `{methodology_id}` methodology.\n"
        f"# `harness init` generated this. Fill the TODOs (empty values fail validation on\n"
        f"# re-run), then re-run `harness init` to install. Full worked example:\n"
        f"# harness/library/examples/sella-cruce/profile.yaml\n"
        f"project: {root.name}\n"
        f"methodology: {methodology_id}\n"
        f"host: claude\n\n"
        f"# Interpreter the gate commands run under — pin it so they're deterministic.\n"
        f'interpreter: "{interp}"\n\n'
        f"verify:\n{verify_line}\n\n"
        f"# Docs-parity gate (OPTIONAL). Set `sync_check` to a command that proves the docs\n"
        f"# match the code and `init` compiles it into a Stop hook (runs before a feature can\n"
        f'# close) and the reviewer cites it. Leave it "" and no docs hook is wired.\n'
        f"docs:\n"
        f'  sync_check: ""              # TODO (optional): e.g. "python scripts/check_docs_sync.py"\n\n'
        f"# Always-on rules, compiled to host hooks. [] = none. Each entry needs an `id`.\n"
        f"constitution: []\n\n"
        f"# Gates differ by feature TYPE. `default` is required; add more keyed to a feature `type`.\n"
        f"gate_profiles:\n"
        f"  default:\n{slot_block}\n"
    )
    _write(root, ".harness/profile.yaml", content)
    return ".harness/profile.yaml"


def _run_verify(command: str, cwd: Path, timeout: float):
    """Run `command` once under a shell, bounded by `timeout` seconds. Returns the
    completed process. Injectable so tests can fake it without spawning anything."""
    import subprocess
    return subprocess.run(command, shell=True, cwd=cwd, capture_output=True, timeout=timeout)


def _run_sync(command: str, cwd: Path, timeout: float):
    """Run the docs sync_check `command` once under a shell, bounded by `timeout` seconds.
    Returns the completed process. Injectable so tests can fake it without spawning anything
    (mirrors _run_verify; used by _write_baseline)."""
    import subprocess
    return subprocess.run(command, shell=True, cwd=cwd, capture_output=True, timeout=timeout)


def _audit_verify_gate(root: Path, profile: dict, timeout: float, runner=None) -> dict | None:
    """Baseline-audit the profile's mechanical gate (finding #10): run ``verify.command``
    once under the interpreter, bounded by a wall-clock ``timeout``, and record whether it
    TERMINATES and its red/green baseline.  Writes the result into LOCAL state
    (.harness/baseline.json, never a managed file) so a later reviewer diffs against a
    known baseline instead of re-deriving it each feature.

    Returns the audit dict, or None when there is no verify command (graceful skip).
    Non-termination within the cap is a loud WARNING, never a hard failure — the timeout
    could be a slow-but-valid suite, and init must not hang or fall over on it.

    Interpreter pinning rules (mirrors how agents actually invoke the gate):
    - ``python``/``python3`` prefix → replace with ``<interpreter>``
    - ``pytest`` prefix + python interpreter → rewrite as ``<interpreter> -m pytest ...``

    The second rule is the canonical case: ``verify.command: "pytest -q"`` with
    ``interpreter: ".venv/bin/python"`` (see library/examples/sella-cruce/profile.yaml).
    Without it the audit runs PATH ``pytest`` while agents run ``<interpreter> -m pytest``,
    making the audit green when the agents' run is red.
    """
    import json, datetime, subprocess
    command = ((profile.get("verify") or {}).get("command", "") or "").strip()
    if not command:
        return None
    if runner is None:
        runner = _run_verify

    interp = resolve_interpreter(profile)
    # Run the gate the way the agents will: pinned under the profile's interpreter.
    # Rule 1: bare python/python3 prefix → replace with the pinned interpreter.
    # Rule 2: pytest prefix with a python interpreter → rewrite as `<interp> -m pytest ...`
    #   so the audit reflects the real virtualenv run, not whatever `pytest` is on PATH.
    full = command
    first = command.split()[0]
    if first in ("python", "python3"):
        full = f"{interp} {' '.join(command.split()[1:])}".rstrip()
    elif first == "pytest" and ("python" in interp.split("/")[-1]):
        rest = command.split()[1:]
        full = " ".join([interp, "-m", "pytest"] + rest)

    audit: dict = {"command": command, "interpreter": interp, "timeout_s": timeout}
    log(f"init: baseline-auditing the verify gate (cap {int(timeout)}s): {command}")
    try:
        r = runner(full, root, timeout)
    except subprocess.TimeoutExpired:
        audit.update(terminated=False, timed_out=True)
        log("init: WARNING — the verify gate did NOT terminate within "
            f"{int(timeout)}s. As written it is likely UNUSABLE as a gate (it may hang,")
        log("      e.g. a visual/interactive suite). Scope it down (e.g. add a marker "
            "filter) before relying on it, or raise --verify-timeout if it is merely slow.")
    except (subprocess.SubprocessError, OSError) as exc:
        audit.update(terminated=False, error=str(exc))
        log(f"init: WARNING — could not run the verify gate: {exc}")
    else:
        audit.update(terminated=True, exit=r.returncode, red=r.returncode != 0)
        color = "RED" if r.returncode != 0 else "green"
        log(f"init: verify gate terminated, baseline {color} (exit {r.returncode}) "
            "-> .harness/baseline.json")

    baseline_path = root / ".harness/baseline.json"
    existing: dict = {}
    if baseline_path.is_file():
        try:
            existing = json.loads(baseline_path.read_text())
        except (ValueError, OSError):
            existing = {}
    existing["generated"] = datetime.datetime.now().isoformat(timespec="seconds")
    existing["verify"] = audit
    _write(root, ".harness/baseline.json", json.dumps(existing, indent=2) + "\n")
    return audit


def _apply_block(root: Path, result) -> str:
    from . import compile as _compile
    target = root / result.block_path
    existing = target.read_text() if target.exists() else ""
    begin, end = result.block_markers
    merged = _compile.merge_block(existing, result.block_text, begin, end)
    _write(root, result.block_path, merged)
    return result.block_path


# --- handlers ---------------------------------------------------------------------

def cmd_list(args: argparse.Namespace) -> int:
    from . import compile as _compile
    lib = _compile.list_library(_compile.library_root())
    if args.what:
        for item in lib[args.what]:
            out(item)
    else:
        for group in ("methodologies", "hosts", "roles"):
            out(f"{group}: {' '.join(lib[group])}")
    return EX_OK


def cmd_init(args: argparse.Namespace) -> int:
    from . import compile as _compile, manifest, validate
    root = Path.cwd()

    if (root / manifest.MANIFEST_REL).exists() and not args.force:
        log("init: already installed (found .harness/.manifest.json). Use `upgrade`, or --force.")
        return EX_FAIL

    if args.from_profile:
        prof_path = Path(args.from_profile)
        if not prof_path.is_file():
            log(f"init: --from-profile {prof_path} not found.")
            return EX_FAIL
    else:
        prof_path = root / ".harness/profile.yaml"
        if not prof_path.is_file():
            rel = _scaffold_profile(root, args.methodology)
            log(f"init: no profile yet — wrote a starter {rel}")
            log("      edit it (verify command, interpreter, gate_profiles), then re-run `harness init`.")
            return EX_FAIL
    profile = _load_yaml(prof_path)

    try:
        meth = _compile.load_methodology(_compile.library_root(), args.methodology)
    except FileNotFoundError as exc:
        log(f"init: {exc}")
        return EX_FAIL
    errs, warns = validate.validate_profile(profile, meth)
    for w in warns:
        log(f"profile: {w}")
    if errs:
        for e in errs:
            log(f"profile: {e}")
        log(f"init: invalid profile ({prof_path}) — fix it and retry.")
        return EX_FAIL

    result = _compile.render(args.methodology, profile, args.host)
    planned = sorted(result.files) + [".harness/profile.yaml", result.block_path]

    if args.dry_run:
        log(f"[dry-run] init {args.methodology} × {args.host} into {root}")
        for p in planned:
            out(p)
        return EX_OK

    # Protect pre-existing files (adoption of a repo with no manifest): don't clobber silently.
    clash = [rel for rel in result.files if (root / rel).exists()]
    if clash and not args.force:
        log("init: these files already exist — refusing to overwrite without --force:")
        for rel in sorted(clash):
            log(f"  {rel}")
        log("Re-run with --force to adopt/overwrite them.")
        return EX_FAIL

    for rel, content in result.files.items():
        _write(root, rel, content)
    _write(root, ".harness/profile.yaml", prof_path.read_text())
    local = _scaffold_local(root, profile)
    _apply_block(root, result)
    managed = {rel: manifest.hash_text(c) for rel, c in result.files.items()}
    manifest.save(root, managed, {"methodology": args.methodology, "host": args.host, "tool_version": __version__})

    # Baseline-audit the mechanical gate: does it terminate, and is it red or green?
    # (finding #10). Advisory — never fails init. Graceful no-op without a verify command.
    _audit_verify_gate(root, profile, timeout=getattr(args, "verify_timeout", 120.0) or 120.0)

    for p in sorted(result.files) + [".harness/profile.yaml", *local, result.block_path]:
        out(p)
    log(f"init: installed {args.methodology} × {args.host} ({len(result.files)} managed files).")
    return EX_OK


def cmd_upgrade(args: argparse.Namespace) -> int:
    from . import compile as _compile, manifest, validate
    root = Path.cwd()
    prof_path = root / ".harness/profile.yaml"
    if not prof_path.is_file():
        log("upgrade: no .harness/profile.yaml here — run `init` first.")
        return EX_FAIL
    profile = _load_yaml(prof_path)
    methodology = profile.get("methodology", "sdd")
    host = profile.get("host", "claude")

    try:
        meth = _compile.load_methodology(_compile.library_root(), methodology)
    except FileNotFoundError as exc:
        log(f"upgrade: {exc}")
        return EX_FAIL
    errs, warns = validate.validate_profile(profile, meth, features=_load_features(root))
    for w in warns:
        log(f"profile: {w}")
    if errs:
        for e in errs:
            log(f"profile: {e}")
        log("upgrade: invalid .harness/profile.yaml — fix it and retry.")
        return EX_FAIL

    result = _compile.render(methodology, profile, host)
    prior = manifest.load(root)
    prior_version = manifest.load_meta(root).get("tool_version")
    if prior_version and prior_version != __version__:
        log(f"upgrade: this repo was last rendered by harness {prior_version}; running {__version__}.")

    buckets: dict[str, list[str]] = {"new": [], "update": [], "unchanged": [], "conflict": []}
    for rel, content in result.files.items():
        buckets[manifest.classify(root, rel, content, prior)].append(rel)

    # Orphans: files managed before but absent from the new render (e.g. a role removed
    # from the roster). Prune them; keep one that was hand-edited unless --force.
    removes, removes_edited = [], []
    for rel in prior:
        if rel in result.files:
            continue
        target = root / rel
        if not target.exists():
            continue
        (removes if manifest.hash_file(target) == prior[rel] else removes_edited).append(rel)

    if args.dry_run:
        log(f"[dry-run] upgrade {methodology} × {host} in {root}")
        for kind in ("new", "update", "conflict"):
            for rel in sorted(buckets[kind]):
                out(f"{kind:9} {rel}")
        for rel in sorted(removes):
            out(f"remove    {rel}")
        for rel in sorted(removes_edited):
            out(f"remove?   {rel}  (orphaned + hand-edited; kept unless --force)")
        log(f"new={len(buckets['new'])} update={len(buckets['update'])} conflict={len(buckets['conflict'])} "
            f"remove={len(removes)} remove?={len(removes_edited)} unchanged={len(buckets['unchanged'])}")
        return EX_OK

    if buckets["conflict"] and not args.force:
        for rel in sorted(buckets["conflict"]):
            log(f"conflict (hand-edited): {rel}")
        log("upgrade: refusing to overwrite hand-edited managed files. Re-run with --force.")
        return EX_FAIL

    changed = []
    for rel, content in result.files.items():
        kind = manifest.classify(root, rel, content, prior)
        if kind in ("new", "update") or (kind == "conflict" and args.force):
            _write(root, rel, content)
            changed.append(rel)
    for rel in removes:
        (root / rel).unlink()
        changed.append(f"(removed) {rel}")
    for rel in removes_edited:
        if args.force:
            (root / rel).unlink()
            changed.append(f"(removed) {rel}")
        else:
            log(f"orphaned but hand-edited, kept: {rel}  (use --force to remove)")

    _apply_block(root, result)
    managed = {rel: manifest.hash_text(c) for rel, c in result.files.items()}
    manifest.save(root, managed, {"methodology": methodology, "host": host, "tool_version": __version__})

    for rel in sorted(changed):
        out(rel)
    n_rm = sum(1 for c in changed if c.startswith("(removed)"))
    log(f"upgrade: {len(changed) - n_rm} re-rendered, {n_rm} removed; local state preserved.")
    return EX_OK


def _next_action(meth: dict | None, status: str) -> str:
    """Cheap next-expected-action for a feature in `status`, derived from the
    methodology's phases ([{state, driver, to}, ...]). '' if not derivable."""
    if not meth:
        return ""
    for phase in meth.get("phases", []):
        if phase.get("state") == status:
            driver, to = phase.get("driver"), phase.get("to")
            if driver and to:
                return f"{driver} -> {to}"
            if driver:
                return str(driver)
            return ""
    return ""


def cmd_status(args: argparse.Namespace) -> int:
    import json
    root = Path.cwd()
    fl = root / ".harness/feature_list.json"
    if not fl.is_file():
        log("status: no .harness/feature_list.json here — run `init` first.")
        return EX_FAIL

    data = json.loads(fl.read_text())
    features = data.get("features", []) or []

    # Optional: load the methodology to annotate the next expected action. Best-effort —
    # never fail status because the methodology is unknown/unavailable.
    meth = None
    try:
        from . import compile as _compile
        meth = _compile.load_methodology(_compile.library_root(), data.get("methodology", "sdd"))
    except Exception:
        meth = None

    project = data.get("project", root.name)
    log(f"status: {project} ({data.get('methodology', '?')}) — {len(features)} feature(s)")

    if not features:
        out("(no features yet — add one to .harness/feature_list.json to get started)")
        return EX_OK

    rows = []
    show_type = any(f.get("type") for f in features)
    show_next = meth is not None
    for f in features:
        fid = str(f.get("id") or f.get("name") or "?")
        status = str(f.get("status") or "?")
        row = [fid, status]
        if show_type:
            row.append(str(f.get("type") or "-"))
        if show_next:
            row.append(_next_action(meth, status) or "-")
        rows.append(row)

    headers = ["ID", "STATUS"]
    if show_type:
        headers.append("TYPE")
    if show_next:
        headers.append("NEXT")
    table = [headers, *rows]
    widths = [max(len(r[c]) for r in table) for c in range(len(headers))]
    for r in table:
        out("  ".join(cell.ljust(widths[c]) for c, cell in enumerate(r)).rstrip())
    return EX_OK


def _write_baseline(root: Path, profile: dict, runner=None) -> dict:
    """Snapshot the runnable mechanical gate(s) so the reviewer can diff against a known
    baseline (finding #3) instead of re-deriving 'pre-existing red' each feature. Today the
    one generically-runnable gate is the profile's `docs.sync_check`. Writes LOCAL state
    (.harness/baseline.json), never a managed file. Returns the gates dict.

    Read-merges into any existing baseline.json so sibling keys written by other
    callers (e.g. the `verify` audit written by `_audit_verify_gate` during `init`)
    are preserved — only `generated` and `gates` are updated."""
    import json, datetime, subprocess
    if runner is None:
        runner = _run_sync
    sync = (profile.get("docs") or {}).get("sync_check")
    gates: dict = {}
    if sync:
        try:
            r = runner(sync, root, 120)
            gates["docs_sync"] = {"command": sync, "exit": r.returncode, "red": r.returncode != 0}
        except (subprocess.SubprocessError, OSError) as exc:
            gates["docs_sync"] = {"command": sync, "error": str(exc)}

    # Read-merge: preserve any keys already in the file (e.g. `verify` from init)
    # and only overwrite the parts this function is responsible for.
    baseline_path = root / ".harness/baseline.json"
    existing: dict = {}
    if baseline_path.is_file():
        try:
            existing = json.loads(baseline_path.read_text())
        except (ValueError, OSError):
            existing = {}
    existing["generated"] = datetime.datetime.now().isoformat(timespec="seconds")
    existing["gates"] = gates
    _write(root, ".harness/baseline.json", json.dumps(existing, indent=2) + "\n")
    return gates


def cmd_doctor(args: argparse.Namespace) -> int:
    """Diagnose an installed harness: profile validity, managed-file integrity, interpreter
    + verify resolvability, and a baseline snapshot of the runnable mechanical gate(s).
    Read-only w.r.t. managed files; only writes local .harness/baseline.json."""
    from . import compile as _compile, manifest, validate
    root = Path.cwd()
    prof_path = root / ".harness/profile.yaml"
    if not prof_path.is_file():
        log("doctor: not installed here (no .harness/profile.yaml). Run `init` first.")
        return EX_FAIL

    problems: list[str] = []
    profile = _load_yaml(prof_path)
    methodology = profile.get("methodology", "sdd")

    # profile validity (same checks as init/upgrade)
    try:
        meth = _compile.load_methodology(_compile.library_root(), methodology)
    except FileNotFoundError as exc:
        log(f"doctor: {exc}")
        return EX_FAIL
    errs, warns = validate.validate_profile(profile, meth, features=_load_features(root))
    for w in warns:
        log(f"  warn: profile: {w}")
    for e in errs:
        log(f"  FAIL: profile: {e}")
    problems += errs

    # manifest + managed files present and matching
    prior = manifest.load(root)
    if not prior:
        log("  FAIL: no manifest (.harness/.manifest.json) — install looks incomplete.")
        problems.append("no manifest")
    else:
        for rel, h in prior.items():
            t = root / rel
            if not t.is_file():
                log(f"  FAIL: managed file missing: {rel}")
                problems.append(rel)
            elif manifest.hash_file(t) != h:
                log(f"  warn: managed file hand-edited (drift): {rel}")

    # interpreter + verify resolvability (warnings — environment-dependent)
    import shutil
    interp = resolve_interpreter(profile)
    interp_bin = interp.split()[0] if interp else ""
    if interp_bin and not (shutil.which(interp_bin) or (root / interp_bin).exists()):
        log(f"  warn: interpreter '{interp}' not found on PATH or in the repo")
    vtok = ((profile.get("verify") or {}).get("command", "") or "").split()
    # Check both PATH and repo-relative path (same logic as the interpreter check above),
    # so a repo-local binary like ".venv/bin/pytest" does not warn spuriously.
    if vtok and not (shutil.which(vtok[0]) or (root / vtok[0]).exists()):
        log(f"  warn: verify command '{vtok[0]}' not found on PATH or in the repo")

    # agent frontmatter registration check: every .claude/agents/*.md must have
    # parseable frontmatter with name/description/tools and a single-line description —
    # the exact conditions that cause Claude Code to silently drop an agent from the roster
    # (issue #13 follow-up).
    agent_dir = root / ".claude/agents"
    agent_files = sorted(agent_dir.glob("*.md")) if agent_dir.is_dir() else []
    for agent_path in agent_files:
        rel = str(agent_path.relative_to(root))
        try:
            text = agent_path.read_text()
        except OSError as exc:
            log(f"  FAIL: cannot read agent file {rel}: {exc}")
            problems.append(rel)
            continue
        ok, reason = _frontmatter_ok(text)
        if not ok:
            log(f"  FAIL: agent file would not register with host — {rel}: {reason}")
            problems.append(rel)

    # baseline snapshot of the runnable mechanical gate(s)
    if not args.no_baseline:
        gates = _write_baseline(root, profile)
        if gates:
            red = [k for k, v in gates.items() if v.get("red")]
            tail = f" — RED: {','.join(red)}" if red else ""
            log(f"  baseline: {len(gates)} mechanical gate(s){tail} -> .harness/baseline.json")

    if problems:
        log(f"doctor: {len(problems)} problem(s) — fix the FAIL lines above.")
        return EX_FAIL
    log("doctor: ok.")
    return EX_OK


def cmd_selftest(args: argparse.Namespace) -> int:
    from . import compile as _compile
    root = _compile.library_root()
    prof = root / "examples/sella-cruce/profile.yaml"
    if not prof.is_file():
        log("selftest: missing fixture examples/sella-cruce/profile.yaml")
        return EX_FAIL
    result = _compile.render("sdd", _load_yaml(prof), "claude")
    checks = []
    rev = result.files.get(".claude/agents/reviewer.md", "")
    led = result.files.get(".claude/agents/leader.md", "")
    settings = result.files.get(".claude/settings.json", "")
    checks.append(("reviewer carries the foreground fix", "foreground" in rev.lower()))
    checks.append(("reviewer carries the delta-gate fix", "delta" in rev.lower()))
    checks.append(("leader carries the re-dispatch fix", "re-dispatch" in led.lower()))
    checks.append(("leader carries the bounded-gate fix", "wall-clock" in led.lower()))
    agent_files = [f for f in result.files if f.endswith(".md") and "/agents/" in f]
    checks.append(("every agent's frontmatter parses as YAML",
                   all(_frontmatter_ok(result.files[f])[0] for f in agent_files)))
    checks.append(("settings has a Stop hook", '"Stop"' in settings))
    checks.append(("CLAUDE block has markers", result.block_text.startswith(result.block_markers[0])))
    ok = all(p for _, p in checks)
    for name, passed in checks:
        log(f"  [{'ok' if passed else 'XX'}] {name}")
    log("selftest: PASS" if ok else "selftest: FAIL")
    return EX_OK if ok else EX_FAIL


# --- parser -----------------------------------------------------------------------

UPDATE_EPILOG = """\
Two updates, deliberately separate:
  the TOOL itself   -> your package manager:   uv tool upgrade method-based-harness
  an installed repo -> this CLI, per repo:     harness upgrade

`harness upgrade` re-renders from the library bundled in the INSTALLED tool, so update
the tool first, then run `harness upgrade` in each repo. (There is no `harness update`;
`upgrade` already means re-render-this-repo.)
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="harness",
        description="Install a methodology-driven multi-agent harness into a repo.",
        epilog=UPDATE_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--version", action="version", version=f"harness {__version__}")
    p.add_argument("-v", "--verbose", action="store_true", help="more detail on stderr")
    p.add_argument("-q", "--quiet", action="store_true", help="errors only on stderr")
    sub = p.add_subparsers(dest="command", metavar="<command>")

    pi = sub.add_parser("init", help="install the harness into this repo")
    pi.add_argument("--methodology", default="sdd", metavar="ID")
    pi.add_argument("--host", default="claude", metavar="ID")
    pi.add_argument("--from-profile", metavar="PATH", help="seed the project profile from a file")
    pi.add_argument("--dry-run", action="store_true", help="show what would change; write nothing")
    pi.add_argument("--force", action="store_true", help="overwrite an existing install")
    pi.add_argument("--verify-timeout", type=float, default=120.0, metavar="SECS",
                    help="wall-clock cap for the post-install verify-gate baseline audit (default 120)")
    pi.set_defaults(func=cmd_init)

    pu = sub.add_parser("upgrade", help="re-render managed files; preserve local state")
    pu.add_argument("--dry-run", action="store_true", help="report drift; write nothing")
    pu.add_argument("--force", action="store_true", help="overwrite hand-edited managed files")
    pu.set_defaults(func=cmd_upgrade)

    pl = sub.add_parser("list", help="show what the library offers")
    pl.add_argument("what", nargs="?", choices=["methodologies", "hosts", "roles"])
    pl.set_defaults(func=cmd_list)

    pst = sub.add_parser("status", help="show features and their state from .harness/feature_list.json (read-only)")
    pst.set_defaults(func=cmd_status)

    pd = sub.add_parser("doctor", help="diagnose an installed harness; snapshot baseline gates")
    pd.add_argument("--no-baseline", action="store_true", help="skip running the profile's mechanical gate(s)")
    pd.set_defaults(func=cmd_doctor)

    ps = sub.add_parser("selftest", help="render a bundled fixture and verify output (offline)")
    ps.set_defaults(func=cmd_selftest)
    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help(sys.stderr)
        sys.exit(EX_USAGE)
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
