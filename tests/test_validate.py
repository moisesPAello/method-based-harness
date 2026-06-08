"""Profile validation (issue #8): clear errors/warnings instead of late KeyErrors.

Errors block init/upgrade; warnings are advisory. Required gate slots are derived from
the methodology (the gates it marks `class: per-type`), so these assert against the real
bundled SDD methodology + example profile.
"""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import yaml

from harness import cli, compile as _compile, validate


def _sdd(lib_root: Path) -> dict:
    return _compile.load_methodology(lib_root, "sdd")


def _example(profile_path: Path) -> dict:
    return yaml.safe_load(profile_path.read_text())


def test_example_profile_is_clean(lib_root, profile_path):
    # The bundled example pins interpreter + constitution + full gate_profiles.
    errs, warns = validate.validate_profile(_example(profile_path), _sdd(lib_root))
    assert errs == []
    assert warns == []


def test_non_mapping_profile_is_error(lib_root):
    errs, _ = validate.validate_profile(["not", "a", "mapping"], _sdd(lib_root))
    assert errs and "mapping" in errs[0]


def test_missing_verify_command_is_error(lib_root, profile_path):
    p = _example(profile_path)
    p.pop("verify", None)
    errs, _ = validate.validate_profile(p, _sdd(lib_root))
    assert any("verify.command" in e for e in errs)


def test_gate_profiles_needs_default(lib_root, profile_path):
    p = _example(profile_path)
    p["gate_profiles"] = {"parser": p["gate_profiles"]["parser"]}  # drop `default`
    errs, _ = validate.validate_profile(p, _sdd(lib_root))
    assert any("default" in e for e in errs)


def test_gate_profile_missing_per_type_slot_is_error(lib_root, profile_path):
    p = _example(profile_path)
    p["gate_profiles"]["default"].pop("review_passed", None)
    errs, _ = validate.validate_profile(p, _sdd(lib_root))
    assert any("review_passed" in e for e in errs)


def test_malformed_constitution_is_error(lib_root, profile_path):
    p = _example(profile_path)
    p["constitution"] = ["just a string, not a mapping with an id"]
    errs, _ = validate.validate_profile(p, _sdd(lib_root))
    assert any("constitution" in e for e in errs)


def test_missing_interpreter_is_warning_not_error(lib_root, profile_path):
    p = _example(profile_path)
    p.pop("interpreter", None)
    errs, warns = validate.validate_profile(p, _sdd(lib_root))
    assert errs == []
    assert any("interpreter" in w for w in warns)


def test_unknown_feature_type_warns(lib_root, profile_path):
    p = _example(profile_path)
    feats = [{"id": "F1", "type": "mystery"}]
    _, warns = validate.validate_profile(p, _sdd(lib_root), features=feats)
    assert any("mystery" in w for w in warns)


def test_non_dict_features_are_ignored(lib_root, profile_path):
    # feature_list may legitimately hold non-dict entries; don't crash on them.
    _, warns = validate.validate_profile(_example(profile_path), _sdd(lib_root),
                                         features=["a string", None])
    assert all("type" not in w for w in warns)


def test_init_rejects_invalid_profile(repo: Path):
    (repo / ".harness").mkdir()
    (repo / ".harness/profile.yaml").write_text(yaml.safe_dump({"methodology": "sdd"}))
    args = Namespace(methodology="sdd", host="claude", from_profile=None,
                     dry_run=False, force=False)
    assert cli.cmd_init(args) == cli.EX_FAIL
    assert not (repo / ".claude/agents/leader.md").exists()  # nothing installed
