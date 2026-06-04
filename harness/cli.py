"""Command-line surface for the harness installer.

Trust posture: WRITE. Mutates the target repo (compiles the library + the repo's
profile into host-native files). Not untrusted-input: the library is bundled and the
only external reads are the user's own repo files (for the manifest / merge).

Surface (verbs are subcommands, properties are flags):

    harness init     --methodology ID --host ID [--from-profile P] [--dry-run] [--force]
    harness upgrade  [--dry-run] [--force]
    harness list     [methodologies|hosts|roles]
    harness selftest

I/O discipline: stdout is data (the changed-file list, the listing), stderr is logs
(progress, verdicts, warnings). Exit 0 success, non-zero failure; `upgrade` exits
non-zero when it refuses a hand-edited managed file (use --force).
"""

from __future__ import annotations

import argparse
import sys

from . import __version__

EX_OK = 0
EX_FAIL = 1
EX_USAGE = 2


def log(msg: str) -> None:
    """Human-facing output → stderr (keeps stdout a clean data channel)."""
    print(msg, file=sys.stderr)


# --- handlers (stubbed until the compiler lands) ----------------------------------

def _todo(name: str) -> int:
    log(f"harness {name}: not implemented yet (surface scaffold; compiler is next).")
    return EX_FAIL


def cmd_init(args: argparse.Namespace) -> int:
    return _todo("init")


def cmd_upgrade(args: argparse.Namespace) -> int:
    return _todo("upgrade")


def cmd_list(args: argparse.Namespace) -> int:
    return _todo("list")


def cmd_selftest(args: argparse.Namespace) -> int:
    return _todo("selftest")


# --- parser -----------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="harness",
        description="Install a methodology-driven multi-agent harness into a repo.",
    )
    p.add_argument("--version", action="version", version=f"harness {__version__}")
    p.add_argument("-v", "--verbose", action="store_true", help="more detail on stderr")
    p.add_argument("-q", "--quiet", action="store_true", help="errors only on stderr")

    sub = p.add_subparsers(dest="command", metavar="<command>")

    pi = sub.add_parser("init", help="install the harness into this repo")
    pi.add_argument("--methodology", default="sdd", metavar="ID", help="methodology pack (default: sdd)")
    pi.add_argument("--host", default="claude", metavar="ID", help="agent host to compile for (default: claude)")
    pi.add_argument("--from-profile", metavar="PATH", help="seed the project profile from an existing file")
    pi.add_argument("--dry-run", action="store_true", help="show what would change; write nothing")
    pi.add_argument("--force", action="store_true", help="overwrite an existing install")
    pi.set_defaults(func=cmd_init)

    pu = sub.add_parser("upgrade", help="re-render managed files from the library; preserve local state")
    pu.add_argument("--dry-run", action="store_true", help="report drift; write nothing")
    pu.add_argument("--force", action="store_true", help="overwrite hand-edited managed files")
    pu.set_defaults(func=cmd_upgrade)

    pl = sub.add_parser("list", help="show what the library offers")
    pl.add_argument("what", nargs="?", choices=["methodologies", "hosts", "roles"], help="filter (default: all)")
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
