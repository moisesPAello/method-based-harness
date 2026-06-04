"""Command-line surface for the harness installer.

Trust posture: WRITE. Mutates the target repo (compiles the library + the repo's
profile into host-native files). Not untrusted-input: the library is bundled and the
only external reads are the user's own repo files (for the manifest / merge).

    harness init     --methodology ID --host ID [--from-profile P] [--dry-run] [--force]
    harness upgrade  [--dry-run] [--force]
    harness list     [methodologies|hosts|roles]
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
    from . import compile as _compile, manifest
    root = Path.cwd()

    if (root / manifest.MANIFEST_REL).exists() and not args.force:
        log("init: already installed (found .harness/.manifest.json). Use `upgrade`, or --force.")
        return EX_FAIL

    prof_path = Path(args.from_profile) if args.from_profile else (root / ".harness/profile.yaml")
    if not prof_path.is_file():
        log("init: need a profile — pass --from-profile PATH (or create .harness/profile.yaml).")
        return EX_FAIL
    profile = _load_yaml(prof_path)

    result = _compile.render(args.methodology, profile, args.host)
    planned = sorted(result.files) + [".harness/profile.yaml", result.block_path]

    if args.dry_run:
        log(f"[dry-run] init {args.methodology} × {args.host} into {root}")
        for p in planned:
            out(p)
        return EX_OK

    for rel, content in result.files.items():
        _write(root, rel, content)
    _write(root, ".harness/profile.yaml", prof_path.read_text())
    local = _scaffold_local(root, profile)
    _apply_block(root, result)
    managed = {rel: manifest.hash_text(c) for rel, c in result.files.items()}
    manifest.save(root, managed, {"methodology": args.methodology, "host": args.host})

    for p in sorted(result.files) + [".harness/profile.yaml", *local, result.block_path]:
        out(p)
    log(f"init: installed {args.methodology} × {args.host} ({len(result.files)} managed files).")
    return EX_OK


def cmd_upgrade(args: argparse.Namespace) -> int:
    from . import compile as _compile, manifest
    root = Path.cwd()
    prof_path = root / ".harness/profile.yaml"
    if not prof_path.is_file():
        log("upgrade: no .harness/profile.yaml here — run `init` first.")
        return EX_FAIL
    profile = _load_yaml(prof_path)
    methodology = profile.get("methodology", "sdd")
    host = profile.get("host", "claude")

    result = _compile.render(methodology, profile, host)
    prior = manifest.load(root)

    buckets: dict[str, list[str]] = {"new": [], "update": [], "unchanged": [], "conflict": []}
    for rel, content in result.files.items():
        buckets[manifest.classify(root, rel, content, prior)].append(rel)

    if args.dry_run:
        log(f"[dry-run] upgrade {methodology} × {host} in {root}")
        for kind in ("new", "update", "conflict"):
            for rel in sorted(buckets[kind]):
                out(f"{kind:9} {rel}")
        log(f"new={len(buckets['new'])} update={len(buckets['update'])} "
            f"conflict={len(buckets['conflict'])} unchanged={len(buckets['unchanged'])}")
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
    _apply_block(root, result)
    managed = {rel: manifest.hash_text(c) for rel, c in result.files.items()}
    manifest.save(root, managed, {"methodology": methodology, "host": host})

    for rel in sorted(changed):
        out(rel)
    log(f"upgrade: {len(changed)} file(s) re-rendered; local state preserved.")
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
    checks.append(("every agent declares tools", all("tools:" in result.files[f] for f in result.files if f.endswith(".md") and "/agents/" in f)))
    checks.append(("settings has a Stop hook", '"Stop"' in settings))
    checks.append(("CLAUDE block has markers", result.block_text.startswith(result.block_markers[0])))
    ok = all(p for _, p in checks)
    for name, passed in checks:
        log(f"  [{'ok' if passed else 'XX'}] {name}")
    log("selftest: PASS" if ok else "selftest: FAIL")
    return EX_OK if ok else EX_FAIL


# --- parser -----------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="harness", description="Install a methodology-driven multi-agent harness into a repo.")
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
