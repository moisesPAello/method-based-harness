"""Profile validation: catch a malformed/incomplete `.harness/profile.yaml` early with
clear, key-naming messages instead of a late `KeyError` mid-render or a silent default.

`validate_profile` returns `(errors, warnings)`:
  - errors   — block `init`/`upgrade` (the profile can't render a trustworthy harness);
  - warnings — advisory (renders, but a deterministic/complete profile would be better).

Required slots are derived from the METHODOLOGY, not hardcoded to SDD: each `gate_profile`
must fill the gate names the methodology marks `class: per-type`. Keeps the tool agnostic.
"""

from __future__ import annotations


def _per_type_gates(meth: dict) -> list[str]:
    """Gate names the methodology resolves from the profile's per-type gate_profiles."""
    return [name for name, g in (meth.get("gates") or {}).items()
            if isinstance(g, dict) and g.get("class") == "per-type"]


def validate_profile(profile, meth: dict, features: list | None = None) -> tuple[list[str], list[str]]:
    """Check `profile` against `meth`. Return (errors, warnings), both human-readable."""
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(profile, dict):
        kind = type(profile).__name__
        return ([f"profile.yaml did not parse to a mapping (got {kind})"], [])

    # verify.command — the leader runs it as the baseline; needed to render real gates.
    verify = profile.get("verify")
    if not (isinstance(verify, dict) and verify.get("command")):
        errors.append("missing `verify.command` — the project's verify/test command")

    # gate_profiles — must have a `default`, and each profile must fill the methodology's
    # per-type gate slots.
    slots = _per_type_gates(meth)
    gp = profile.get("gate_profiles")
    if not isinstance(gp, dict) or "default" not in gp:
        errors.append("`gate_profiles` must be a mapping with at least a `default` profile")
    else:
        for name, prof in gp.items():
            if not isinstance(prof, dict):
                errors.append(f"`gate_profiles.{name}` must be a mapping")
                continue
            for slot in slots:
                if slot not in prof:
                    errors.append(f"`gate_profiles.{name}` is missing `{slot}`")
                elif not prof.get(slot):
                    # Present-but-empty is what the scaffold writes (`{slot}: []  # TODO`);
                    # don't call it "missing" — that contradicts the file we just wrote.
                    errors.append(f"`gate_profiles.{name}`: `{slot}` has no conditions — "
                                  f"fill in the TODO (see harness/library/examples/"
                                  f"sella-cruce/profile.yaml)")

    # tracker — optional backlog-edge adapter; defaults to `none`. If set, must be a
    # known tracker. `none` keeps the harness byte-for-byte unchanged (no network/auth).
    tracker = profile.get("tracker")
    if tracker is not None:
        from .trackers import known_trackers
        if not isinstance(tracker, str) or tracker not in known_trackers():
            errors.append(f"`tracker` must be one of {known_trackers()} "
                          f"(got {tracker!r}); omit it or set `tracker: none` for disk-only")

    # constitution — optional, but if present must be a list of entries with an `id`.
    con = profile.get("constitution")
    if con is not None and (not isinstance(con, list)
                            or any(not isinstance(c, dict) or "id" not in c for c in con)):
        errors.append("`constitution` must be a list of entries, each a mapping with an `id`")

    # --- warnings (don't block) ---------------------------------------------------
    if not profile.get("interpreter"):
        warnings.append("no `interpreter:` set — gate commands default to `python3`; "
                        "pin it so they are deterministic (finding #1)")
    if con is None:
        warnings.append("no `constitution:` set — add always-on rules, or set "
                        "`constitution: []` to silence this")

    # A feature whose `type` has no matching gate_profile falls through to whatever the
    # role resolves — flag it so it's a deliberate choice, not a surprise.
    if features and isinstance(gp, dict):
        known = set(gp)
        for f in features:
            if not isinstance(f, dict):
                continue
            t = f.get("type")
            if t and t not in known:
                fid = f.get("id") or f.get("name") or "?"
                warnings.append(f"feature '{fid}' has type '{t}' but there is no "
                                f"`gate_profiles.{t}` (it will fall back to whatever the role resolves)")

    return errors, warnings
