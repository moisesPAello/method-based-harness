"""Shared low-level helpers used by both the CLI layer (cli.py) and the host
renderers (hosts/claude.py).  Kept separate to avoid the circular import that
would arise if either layer imported from the other."""

from __future__ import annotations


def resolve_interpreter(profile: dict) -> str:
    """Return the non-empty interpreter string for *profile*.

    Normalises every falsy value (``None``, ``""`` from a bare
    ``interpreter:`` key in YAML) to the safe default ``"python3"``, so
    callers never produce broken ``Bash( *)`` permission strings or
    "via ``''" text in leader.md from an empty value.

    >>> resolve_interpreter({"interpreter": ".venv/bin/python"})
    '.venv/bin/python'
    >>> resolve_interpreter({"interpreter": ""})
    'python3'
    >>> resolve_interpreter({"interpreter": None})
    'python3'
    >>> resolve_interpreter({})
    'python3'
    """
    return (profile.get("interpreter") or "python3").strip() or "python3"
