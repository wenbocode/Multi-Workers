"""test_worker_thinking.py - W1 policy helper (mw-worker-thinking).

Offline, hermetic regression for ``resolve_worker_thinking``: missing/no block,
default, role priority, task-type aliases, empty-type fallback, quoted off,
all seven levels, illegal shapes/levels/roles/keys, bool/null values (with the
quote hint), BOM, hot re-read (no cache), read-only (no writes), model config
untouched, and other top-level keys being irrelevant. No network, no LLM.
"""
import pathlib
import sys

import pytest
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw
import mw_common
from worker_thinking import THINKING_LEVELS, resolve_worker_thinking


# ── helpers ───────────────────────────────────────────────────────────────────


def _write(tmp_path: pathlib.Path, text: str, *, encoding: str = "utf-8") -> pathlib.Path:
    (tmp_path / ".mw").mkdir(exist_ok=True)
    path = tmp_path / ".mw" / "dispatch.yml"
    path.write_text(text, encoding=encoding)
    return path


def _resolve(tmp_path: pathlib.Path, task_type: str = "coding"):
    return resolve_worker_thinking(pathlib.Path(tmp_path), task_type)


def _assert_invalid(tmp_path: pathlib.Path, result, *, contains: str | None = None) -> None:
    level, source, error = result
    assert level is None
    assert source == "invalid"
    assert isinstance(error, str) and error
    assert str(tmp_path / ".mw" / "dispatch.yml") in error  # diagnostic includes the path
    assert "thinking" in error  # clear thinking-config diagnostic
    if contains is not None:
        assert contains in error


# ── constant / contract ───────────────────────────────────────────────────────


def test_thinking_levels_is_exact_string_tuple() -> None:
    assert THINKING_LEVELS == ("off", "minimal", "low", "medium", "high", "xhigh", "max")
    assert isinstance(THINKING_LEVELS, tuple)
    assert all(isinstance(level, str) for level in THINKING_LEVELS)


# ── unset (missing / absent block / no effective level) ───────────────────────


def test_missing_file_is_unset(tmp_path: pathlib.Path) -> None:
    # No .mw directory at all.
    assert _resolve(tmp_path) == (None, "unset", None)


def test_missing_dispatch_yml_is_unset(tmp_path: pathlib.Path) -> None:
    (tmp_path / ".mw").mkdir()
    assert _resolve(tmp_path) == (None, "unset", None)


def test_empty_and_comment_only_file_is_unset(tmp_path: pathlib.Path) -> None:
    _write(tmp_path, "")
    assert _resolve(tmp_path) == (None, "unset", None)
    _write(tmp_path, "# just a comment\n")
    assert _resolve(tmp_path) == (None, "unset", None)


def test_valid_config_without_thinking_is_unset(tmp_path: pathlib.Path) -> None:
    # Other top-level keys are legal and do not trigger a thinking diagnostic.
    _write(
        tmp_path,
        "models:\n  coding: toa/deepseek-v4.1-flash\n"
        "fallback_models:\n  coding:\n    - toa/hy4\n",
    )
    assert _resolve(tmp_path) == (None, "unset", None)


def test_empty_thinking_mapping_is_unset(tmp_path: pathlib.Path) -> None:
    _write(tmp_path, "thinking: {}\n")
    assert _resolve(tmp_path) == (None, "unset", None)


def test_empty_roles_acceptable(tmp_path: pathlib.Path) -> None:
    _write(tmp_path, "thinking:\n  roles: {}\n")
    assert _resolve(tmp_path) == (None, "unset", None)


@pytest.mark.parametrize("value", ["", "null", "~", "false", "[]"])
def test_roles_must_be_mapping(tmp_path: pathlib.Path, value: str) -> None:
    _write(tmp_path, f"thinking:\n  default: high\n  roles: {value}\n")
    _assert_invalid(tmp_path, _resolve(tmp_path), contains="thinking.roles must be a mapping")


def test_default_missing_roles_for_other_role_is_unset(tmp_path: pathlib.Path) -> None:
    # default can be missing; a role bucket that does not match the task -> unset.
    _write(tmp_path, "thinking:\n  roles:\n    review: low\n")
    assert _resolve(tmp_path, "coding") == (None, "unset", None)


# ── default / role priority / quoted off ──────────────────────────────────────


def test_default_only(tmp_path: pathlib.Path) -> None:
    _write(tmp_path, "thinking:\n  default: high\n")
    assert _resolve(tmp_path) == ("high", "config:default", None)
    assert _resolve(tmp_path, "research") == ("high", "config:default", None)


def test_role_overrides_default(tmp_path: pathlib.Path) -> None:
    _write(
        tmp_path,
        'thinking:\n  default: high\n  roles:\n    research: "off"\n',
    )
    # role > default: research uses the quoted "off" override.
    assert _resolve(tmp_path, "research") == ("off", "config:research", None)
    # a different bucket falls back to default.
    assert _resolve(tmp_path, "coding") == ("high", "config:default", None)


@pytest.mark.parametrize("level", list(THINKING_LEVELS))
def test_all_seven_levels_as_default(tmp_path: pathlib.Path, level: str) -> None:
    _write(tmp_path, f'thinking:\n  default: "{level}"\n')
    assert _resolve(tmp_path) == (level, "config:default", None)


@pytest.mark.parametrize("level", list(THINKING_LEVELS))
def test_all_seven_levels_as_role_value(tmp_path: pathlib.Path, level: str) -> None:
    _write(tmp_path, f'thinking:\n  roles:\n    research: "{level}"\n')
    assert _resolve(tmp_path, "research") == (level, "config:research", None)


def test_quoted_off_preserved_not_dropped(tmp_path: pathlib.Path) -> None:
    # "off" is falsy-looking but must be returned verbatim, never truthiness-dropped.
    _write(tmp_path, 'thinking:\n  default: "off"\n')
    assert _resolve(tmp_path) == ("off", "config:default", None)
    _write(tmp_path, "thinking:\n  default: 'off'\n")
    assert _resolve(tmp_path) == ("off", "config:default", None)


# ── task-type aliases and empty-type fallback ─────────────────────────────────


@pytest.mark.parametrize(
    "task_type,role",
    [
        ("coding", "coding"),
        ("phase-writer", "coding"),
        ("repair", "coding"),
        ("roadmap-writer", "coding"),
        ("review", "review"),
        ("verifier", "review"),
        ("reviewer", "review"),
        ("research", "research"),
        ("rag-research", "research"),
        ("vision", "vision"),
        ("decide_prepare", "decide_prepare"),
        ("", "coding"),
        ("unknown-type", "coding"),
    ],
)
def test_aliases_map_to_role_bucket(tmp_path: pathlib.Path, task_type: str, role: str) -> None:
    # Build a roles map covering every valid role with distinct levels, plus a
    # default, so each alias must resolve through its bucket.
    _write(
        tmp_path,
        "thinking:\n  default: max\n  roles:\n"
        "    coding: minimal\n    review: low\n    research: medium\n"
        "    vision: xhigh\n    decide_prepare: high\n",
    )
    expected_level = {
        "coding": "minimal",
        "review": "low",
        "research": "medium",
        "vision": "xhigh",
        "decide_prepare": "high",
    }[role]
    assert _resolve(tmp_path, task_type) == (expected_level, f"config:{role}", None)


def test_empty_type_uses_coding_bucket_override(tmp_path: pathlib.Path) -> None:
    _write(tmp_path, "thinking:\n  default: high\n  roles:\n    coding: low\n")
    assert _resolve(tmp_path, "") == ("low", "config:coding", None)
    assert _resolve(tmp_path, "bogus") == ("low", "config:coding", None)


# ── invalid: YAML off->False / bool / null values (quote hint) ────────────────


@pytest.mark.parametrize("bare", ["off", "on", "yes", "no", "true", "false", "False"])
def test_unquoted_off_becomes_bool_is_invalid_with_quote_hint(
    tmp_path: pathlib.Path, bare: str
) -> None:
    _write(tmp_path, f"thinking:\n  default: {bare}\n")
    result = _resolve(tmp_path)
    _assert_invalid(tmp_path, result)
    _, source, error = result
    assert source == "invalid"  # NOT "unset": False is never treated as unset
    assert "quote" in error.lower()
    assert "off" in error  # hint mentions quoting "off"


def test_unquoted_off_role_value_is_invalid(tmp_path: pathlib.Path) -> None:
    _write(tmp_path, "thinking:\n  roles:\n    research: off\n")
    result = _resolve(tmp_path, "research")
    _assert_invalid(tmp_path, result)
    assert "quote" in result[2].lower()


@pytest.mark.parametrize("bare", ["null", "~"])
def test_null_default_is_invalid(tmp_path: pathlib.Path, bare: str) -> None:
    _write(tmp_path, f"thinking:\n  default: {bare}\n")
    _assert_invalid(tmp_path, _resolve(tmp_path))


def test_empty_default_value_is_invalid(tmp_path: pathlib.Path) -> None:
    _write(tmp_path, "thinking:\n  default:\n")
    _assert_invalid(tmp_path, _resolve(tmp_path))


def test_null_role_value_is_invalid(tmp_path: pathlib.Path) -> None:
    _write(tmp_path, "thinking:\n  roles:\n    research: null\n")
    _assert_invalid(tmp_path, _resolve(tmp_path, "research"))


# ── invalid: illegal levels / shapes / keys / roles ───────────────────────────


@pytest.mark.parametrize(
    "value",
    ["HIGH", "ultra", "none", '""', "3", "[high]", "{a: b}", "' high '"],
)
def test_illegal_default_level_is_invalid(tmp_path: pathlib.Path, value: str) -> None:
    _write(tmp_path, f"thinking:\n  default: {value}\n")
    _assert_invalid(tmp_path, _resolve(tmp_path))


@pytest.mark.parametrize(
    "config",
    [
        "thinking: high\n",                                  # scalar block
        "thinking: [high]\n",                                # list block
        "thinking: true\n",                                  # bool block
        "thinking: 42\n",                                    # int block
        "thinking:\n",                                       # null block (must be mapping)
        "thinking:\n  default: high\n  extra: 1\n",         # unknown key
        "thinking:\n  foo: high\n",                          # only unknown key
        "thinking:\n  roles: oops\n",                       # roles not a mapping
        "thinking:\n  roles: [high]\n",                     # roles is a list
        "thinking:\n  roles:\n    main: high\n",            # main excluded
        "thinking:\n  roles:\n    villain: high\n",         # unknown role
        "thinking:\n  roles:\n    research:\n      level: high\n",  # nested value
        "thinking:\n  roles:\n    research: [high]\n",      # list value
        "thinking:\n  default: high\n  roles:\n    review: ultra\n",  # bad level in role
        "- a\n- b\n",                                        # top-level list
        "just a scalar\n",                                  # top-level scalar
        "thinking: [broken\n",                              # YAML parse error
    ],
)
def test_invalid_shapes_fail_soft(tmp_path: pathlib.Path, config: str) -> None:
    _write(tmp_path, config)
    _assert_invalid(tmp_path, _resolve(tmp_path))


def test_whole_block_rejected_when_one_field_bad(tmp_path: pathlib.Path) -> None:
    # A valid default must NOT be consumed when a sibling role value is invalid.
    _write(tmp_path, "thinking:\n  default: high\n  roles:\n    research: ultra\n")
    result = _resolve(tmp_path, "coding")
    _assert_invalid(tmp_path, result)
    assert result[0] is None


# ── other top-level keys irrelevant / model config untouched ──────────────────


def test_other_top_level_keys_do_not_affect_thinking(tmp_path: pathlib.Path) -> None:
    _write(
        tmp_path,
        "models:\n  coding: toa/deepseek-v4.1-flash\n"
        "fallback_models:\n  coding:\n    - toa/hy4\n"
        "rag:\n  enabled: []\n"
        "thinking:\n  default: high\n  roles:\n    research: low\n",
    )
    assert _resolve(tmp_path, "coding") == ("high", "config:default", None)
    assert _resolve(tmp_path, "research") == ("low", "config:research", None)


def test_model_config_unchanged_and_load_dispatch_config_contract(tmp_path: pathlib.Path) -> None:
    config_text = (
        "models:\n  coding: toa/deepseek-v4.1-flash\n  review: timi/glm-5.3-air\n"
        "fallback_models:\n  coding:\n    - toa/hy4\n"
        "thinking:\n  default: high\n"
    )
    path = _write(tmp_path, config_text)
    before = path.read_bytes()
    # The helper resolves thinking without altering model configuration.
    assert _resolve(tmp_path) == ("high", "config:default", None)
    assert path.read_bytes() == before  # no writes
    # Shared load_dispatch_config return shape is intact; thinking is ignored.
    loaded, err = mw_common.load_dispatch_config(pathlib.Path(tmp_path))
    assert err is None
    assert loaded == {
        "models": {"coding": "toa/deepseek-v4.1-flash", "review": "timi/glm-5.3-air"}
    }
    # File still parses to the same structure (no mutation in place).
    assert yaml.safe_load(path.read_text(encoding="utf-8"))["thinking"] == {"default": "high"}


def test_helper_writes_no_files(tmp_path: pathlib.Path) -> None:
    _write(tmp_path, "thinking:\n  default: high\n")
    entries_before = sorted(p.name for p in (tmp_path / ".mw").iterdir())
    _resolve(tmp_path)
    _resolve(tmp_path, "research")
    entries_after = sorted(p.name for p in (tmp_path / ".mw").iterdir())
    assert entries_after == entries_before == ["dispatch.yml"]


@pytest.mark.parametrize("models", [{"coding": "toa/hy4"}, {}])
@pytest.mark.parametrize("fallbacks", [None, {}, {"coding": ["toa/hy4"]}])
def test_model_writer_preserves_thinking(tmp_path: pathlib.Path, models, fallbacks) -> None:
    path = _write(
        tmp_path,
        'models:\n  coding: toa/hy4\nthinking:\n  default: high\n'
        '  roles:\n    research: "off"\n',
    )
    expected = yaml.safe_load(path.read_text(encoding="utf-8"))["thinking"]
    mw._model_write(tmp_path, models, fallback_models=fallbacks)
    assert yaml.safe_load(path.read_text(encoding="utf-8"))["thinking"] == expected
    assert _resolve(tmp_path, "research") == ("off", "config:research", None)


# ── BOM tolerance ─────────────────────────────────────────────────────────────


def test_bom_written_via_utf8_sig_is_readable(tmp_path: pathlib.Path) -> None:
    _write(tmp_path, "thinking:\n  default: high\n", encoding="utf-8-sig")
    assert _resolve(tmp_path) == ("high", "config:default", None)


def test_literal_bom_character_is_readable(tmp_path: pathlib.Path) -> None:
    # A leading U+FEFF byte sequence written with plain utf-8 is also stripped.
    _write(tmp_path, "\ufeffthinking:\n  default: high\n  roles:\n    research: low\n")
    assert _resolve(tmp_path) == ("high", "config:default", None)
    assert _resolve(tmp_path, "research") == ("low", "config:research", None)


# ── read failures ─────────────────────────────────────────────────────────────


def test_dispatch_path_is_directory_fails_soft(tmp_path: pathlib.Path) -> None:
    (tmp_path / ".mw" / "dispatch.yml").mkdir(parents=True)
    _assert_invalid(tmp_path, _resolve(tmp_path), contains="unreadable")


def test_invalid_utf8_fails_soft(tmp_path: pathlib.Path) -> None:
    path = _write(tmp_path, "")
    path.write_bytes(b"thinking:\n  default: high\n\xff")
    _assert_invalid(tmp_path, _resolve(tmp_path), contains="unreadable")


# ── hot re-read (no cache) ────────────────────────────────────────────────────


def test_hot_reread_reflects_each_new_value(tmp_path: pathlib.Path) -> None:
    _write(tmp_path, "thinking:\n  default: high\n")
    assert _resolve(tmp_path) == ("high", "config:default", None)
    _write(tmp_path, "thinking:\n  default: low\n")
    assert _resolve(tmp_path) == ("low", "config:default", None)
    _write(tmp_path, "thinking:\n  roles:\n    research: minimal\n")
    assert _resolve(tmp_path, "research") == ("minimal", "config:research", None)
    assert _resolve(tmp_path, "coding") == (None, "unset", None)
    _write(tmp_path, "thinking:\n  default: off\n")  # bool -> invalid
    _assert_invalid(tmp_path, _resolve(tmp_path))
    _write(tmp_path, "models:\n  coding: x\n")  # no thinking -> unset
    assert _resolve(tmp_path) == (None, "unset", None)
    _write(tmp_path, "thinking:\n  default: max\n")
    assert _resolve(tmp_path) == ("max", "config:default", None)
