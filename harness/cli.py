"""Command-line surface for the harness installer.

Trust posture: WRITE. Mutates the target repo (compiles the library + the repo's
profile into host-native files). Not untrusted-input: the library is bundled and the
only external reads are the user's own repo files (for the manifest / merge).

    harness init     --methodology ID --host ID [--from-profile P] [--dry-run] [--force]
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

EX_OK, EX_FAIL, EX_USAGE = 0, 1, 2


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def out(msg: str) -> None:
    print(msg)


# --- helpers ----------------------------------------------------------------------

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
        f"# Always-on rules, compiled to host hooks. [] = none. Each entry needs an `id`.\n"
        f"constitution: []\n\n"
        f"# Gates differ by feature TYPE. `default` is required; add more keyed to a feature `type`.\n"
        f"gate_profiles:\n"
        f"  default:\n{slot_block}\n"
    )
    _write(root, ".harness/profile.yaml", content)
    return ".harness/profile.yaml"


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


def _write_baseline(root: Path, profile: dict) -> dict:
    """Snapshot the runnable mechanical gate(s) so the reviewer can diff against a known
    baseline (finding #3) instead of re-deriving 'pre-existing red' each feature. Today the
    one generically-runnable gate is the profile's `docs.sync_check`. Writes LOCAL state
    (.harness/baseline.json), never a managed file. Returns the gates dict."""
    import json, subprocess, datetime
    sync = (profile.get("docs") or {}).get("sync_check")
    gates: dict = {}
    if sync:
        try:
            r = subprocess.run(sync, shell=True, cwd=root, capture_output=True, timeout=120)
            gates["docs_sync"] = {"command": sync, "exit": r.returncode, "red": r.returncode != 0}
        except (subprocess.SubprocessError, OSError) as exc:
            gates["docs_sync"] = {"command": sync, "error": str(exc)}
    baseline = {"generated": datetime.datetime.now().isoformat(timespec="seconds"), "gates": gates}
    _write(root, ".harness/baseline.json", json.dumps(baseline, indent=2) + "\n")
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
    interp = profile.get("interpreter", "python3")
    interp_bin = interp.split()[0] if interp else ""
    if interp_bin and not (shutil.which(interp_bin) or (root / interp_bin).exists()):
        log(f"  warn: interpreter '{interp}' not found on PATH or in the repo")
    vtok = ((profile.get("verify") or {}).get("command", "") or "").split()
    if vtok and not shutil.which(vtok[0]):
        log(f"  warn: verify command '{vtok[0]}' not found on PATH")

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
    import yaml
    agent_files = [f for f in result.files if f.endswith(".md") and "/agents/" in f]

    def _frontmatter_ok(text: str) -> bool:
        # An agent file must lead with a `---`-fenced block that parses as a YAML
        # mapping carrying name/description/tools — a wrapped value silently drops
        # the agent from the host roster, so re-parse it rather than substring-match.
        parts = text.split("---", 2)
        if len(parts) < 3 or parts[0].strip():
            return False
        try:
            fm = yaml.safe_load(parts[1])
        except yaml.YAMLError:
            return False
        return isinstance(fm, dict) and {"name", "description", "tools"} <= fm.keys()

    checks.append(("every agent's frontmatter parses as YAML", all(_frontmatter_ok(result.files[f]) for f in agent_files)))
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
