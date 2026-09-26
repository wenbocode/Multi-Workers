"""
test_autopilot_config.py — L1 tests for autopilot config.py + advance.py
(T-02, AC-025 / VC-027 prerequisites).

All fixtures build their own project roots under tmp_path; nothing touches a
real project or the real framework install.
"""
import json
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from autopilot import advance as adv
from autopilot import config as cfg
from autopilot import effective_config as ec


def _verify(tag: str, **kv) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()))


# ── config: defaults, zero footprint, fail-closed validation ─────────────────

def test_defaults_when_file_missing(tmp_path: pathlib.Path) -> None:
    cfg.invalidate_cache()
    loaded = cfg.load_config(tmp_path)
    assert loaded == cfg.DEFAULT_CONFIG
    # Zero footprint: nothing created on the read path.
    assert not (tmp_path / ".agenticdoc" / "_autopilot").exists()
    assert cfg.cached_load(tmp_path) == cfg.DEFAULT_CONFIG
    assert not (tmp_path / ".agenticdoc").exists()
    _verify("VC-027", defaults_on_missing=true_str(True), zero_footprint=true_str(True))


def true_str(b: bool) -> str:
    return "true" if b else "false"


@pytest.mark.parametrize(
    "bad,field_hint",
    [
        ({"poll_interval_sec": 6}, "poll_interval_sec"),
        ({"poll_interval_sec": 0}, "poll_interval_sec"),
        ({"poll_interval_sec": "4"}, "poll_interval_sec"),
        ({"poll_interval_sec": True}, "poll_interval_sec"),
        ({"max_parallel_keys": 1}, "max_parallel_keys"),
        ({"max_parallel_keys": "2"}, "max_parallel_keys"),
        ({"enabled": "yes"}, "enabled"),
        ({"paused": 1}, "paused"),
        ({"round_budget": 0}, "round_budget"),
        ({"worker_timeout_min": 0}, "worker_timeout_min"),
        ({"l2_read_file_cap": 0}, "l2_read_file_cap"),
        ({"l2_read_byte_cap": 0}, "l2_read_byte_cap"),
        ({"totally_unknown": 1}, "totally_unknown"),
    ],
)
def test_invalid_values_rejected(tmp_path: pathlib.Path, bad: dict, field_hint: str) -> None:
    path = cfg.config_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**cfg.DEFAULT_CONFIG, **bad}), encoding="utf-8")
    with pytest.raises(cfg.ConfigError) as excinfo:
        cfg.load_config(tmp_path)
    assert field_hint in str(excinfo.value), f"error must name the field: {excinfo.value}"


def test_malformed_json_rejected(tmp_path: pathlib.Path) -> None:
    path = cfg.config_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(cfg.ConfigError):
        cfg.load_config(tmp_path)


def test_invalid_never_falls_back_to_defaults(tmp_path: pathlib.Path) -> None:
    """Fail-closed: a present-but-wrong config must raise, not run on defaults."""
    path = cfg.config_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"enabled": True, "poll_interval_sec": 99}), encoding="utf-8")
    with pytest.raises(cfg.ConfigError):
        cfg.load_config(tmp_path)
    _verify("VC-027", invalid_fail_closed=true_str(True))


# ── config: save/load round-trip, atomicity ──────────────────────────────────

def test_roundtrip_and_atomic_write(tmp_path: pathlib.Path) -> None:
    cfg.invalidate_cache()
    modified = cfg.default_config()
    modified.update({"enabled": True, "poll_interval_sec": 2, "round_budget": 3})
    path = cfg.save_config(tmp_path, modified)
    assert path.is_file()
    # Trailing newline, UTF-8, no tmp leftovers (atomic replace completed).
    raw = path.read_text(encoding="utf-8")
    assert raw.endswith("\n") and not raw.endswith("\n\n")
    assert not list(path.parent.glob("*.tmp"))
    assert cfg.load_config(tmp_path) == modified
    _verify("VC-027", roundtrip=true_str(True), atomic_no_tmp=true_str(True))


def test_save_rejects_invalid(tmp_path: pathlib.Path) -> None:
    with pytest.raises(cfg.ConfigError):
        cfg.save_config(tmp_path, {**cfg.default_config(), "poll_interval_sec": 9})
    assert not cfg.config_path(tmp_path).exists()


# ── config: no cache short-circuit / defaults / encoding ─────────────────────

def test_default_config_has_13_keys_in_order() -> None:
    assert len(cfg.DEFAULT_CONFIG) == 13
    assert list(cfg.DEFAULT_CONFIG)[-1] == "xkey_verify_cwd"
    assert list(cfg.DEFAULT_CONFIG)[-2] == "xkey_verify_timeout_s"
    assert cfg.default_config()["xkey_verify_cwd"] == ""
    _verify("VC-016", default_config_keys=len(cfg.DEFAULT_CONFIG),
            xkey_verify_cwd_default=repr(cfg.DEFAULT_CONFIG["xkey_verify_cwd"]))


def test_partial_file_returns_only_written_keys(tmp_path: pathlib.Path) -> None:
    """load_config never fills defaults: a partial config.json yields exactly
    the keys it carries. The complete 13-key view has its own sources
    (default_config() / effective_config.load_effective)."""
    cfg.invalidate_cache()
    path = cfg.config_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"advance_stall_ticks": 7}), encoding="utf-8")
    loaded = cfg.load_config(tmp_path)
    assert set(loaded) == {"advance_stall_ticks"}
    assert loaded["advance_stall_ticks"] == 7
    assert "poll_interval_sec" not in loaded  # no default fill
    # The complete 13-key view has its own sources.
    assert len(cfg.default_config()) == 13
    assert len(ec.load_effective(tmp_path).values) == 13
    _verify("VC-016", partial_keys=len(loaded), default_keys=len(cfg.default_config()),
            effective_keys=len(ec.load_effective(tmp_path).values),
            explicit_wins=loaded["advance_stall_ticks"])


def test_xkey_verify_cwd_schema_is_string_only(tmp_path: pathlib.Path) -> None:
    """Schema accepts any string; root-name validity is a parse-time concern."""
    path = cfg.config_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    for bad in (5, True, ["control"], {"root": "control"}):
        path.write_text(json.dumps({"xkey_verify_cwd": bad}), encoding="utf-8")
        with pytest.raises(cfg.ConfigError) as excinfo:
            cfg.load_config(tmp_path)
        assert "xkey_verify_cwd" in str(excinfo.value), excinfo.value
    path.write_text(json.dumps({"xkey_verify_cwd": "some-root"}), encoding="utf-8")
    assert cfg.load_config(tmp_path)["xkey_verify_cwd"] == "some-root"


def test_save_config_writes_non_ascii_verbatim(tmp_path: pathlib.Path) -> None:
    cfg.invalidate_cache()
    conf = cfg.default_config()
    conf["xkey_verify_cmd"] = ["echo", "中文-命令"]
    path = cfg.save_config(tmp_path, conf)
    raw = path.read_bytes()
    expected = json.dumps(conf, indent=2, ensure_ascii=False) + "\n"
    assert raw == expected.encode("utf-8")
    assert "中文-命令".encode("utf-8") in raw
    assert b"\\u4e2d" not in raw  # ensure_ascii=False: no \uXXXX escapes
    assert cfg.load_config(tmp_path)["xkey_verify_cmd"] == ["echo", "中文-命令"]
    _verify("VC-003", non_ascii_bytes=len(raw), verbatim=true_str(True))


def test_same_length_rewrite_seen_without_cache_clear(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No stat short-circuit: an external, same-byte-length rewrite must be
    visible on the next cached_load even though the cache was never cleared.

    The file's stat is frozen so (mtime_ns, size) cannot change; any
    mtime/size-keyed cache would serve a stale value, making this the
    non-hollow counter-proof for the removal of the stat shortcut."""
    cfg.invalidate_cache()
    path = cfg.config_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    before = json.dumps({"round_budget": 2}, indent=2) + "\n"
    after = json.dumps({"round_budget": 9}, indent=2) + "\n"
    assert len(before) == len(after), "rewrite must keep the byte length"
    path.write_text(before, encoding="utf-8", newline="\n")
    assert cfg.cached_load(tmp_path)["round_budget"] == 2

    frozen = path.stat()
    real_stat = pathlib.Path.stat

    def frozen_stat(self: pathlib.Path, *args, **kwargs):  # type: ignore[no-untyped-def]
        return frozen if self == path else real_stat(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "stat", frozen_stat)
    path.write_text(after, encoding="utf-8", newline="\n")  # bare bytes write
    got = cfg.cached_load(tmp_path)["round_budget"]
    assert got == 9, f"same-length rewrite ignored (stale cache): got {got}"
    _verify("VC-003", same_length_rewrite=9, cache_cleared=true_str(False))


def test_cached_load_defensive_copy_and_write_coherence(tmp_path: pathlib.Path) -> None:
    cfg.invalidate_cache()
    a = cfg.default_config()
    a["round_budget"] = 9
    cfg.save_config(tmp_path, a)
    got = cfg.cached_load(tmp_path)
    got["round_budget"] = 123
    assert cfg.cached_load(tmp_path)["round_budget"] == 9  # defensive copy
    c = cfg.default_config()
    c["round_budget"] = 5
    cfg.save_config(tmp_path, c)
    assert cfg.cached_load(tmp_path)["round_budget"] == 5  # write coherent
    _verify("VC-003", defensive_copy=true_str(True), cache_write_coherent=true_str(True))


def test_cache_absent_then_created(tmp_path: pathlib.Path) -> None:
    cfg.invalidate_cache()
    assert cfg.cached_load(tmp_path) == cfg.DEFAULT_CONFIG  # absent -> defaults
    d = cfg.default_config()
    d["enabled"] = True
    cfg.save_config(tmp_path, d)
    assert cfg.cached_load(tmp_path)["enabled"] is True  # absent -> present
    cfg.invalidate_cache()


# ── advance: framework location ──────────────────────────────────────────────

def test_missing_framework_refused(tmp_path: pathlib.Path) -> None:
    adv.invalidate_script_cache()
    (tmp_path / ".agenticdoc").mkdir()
    with pytest.raises(adv.AdvanceError) as excinfo:
        adv.locate_platform_dir(tmp_path)
    assert "framework not installed" in str(excinfo.value)
    code, out, err = adv.advance("some-key", "verify", tmp_path)
    assert code == 1 and out == "" and "framework not installed" in err
    _verify("VC-027", advance_missing_framework=1, missing_framework_stderr=true_str(True))


def _stub_framework(project_root: pathlib.Path, *, via_marker: bool) -> pathlib.Path:
    """Lay down a fake framework with detect_root.py + advance_phase.py stubs.

    via_marker=True anchors it through .agentic-framework (repo= line);
    otherwise through the standard .agents/skills/agentic-task layout."""
    if via_marker:
        plat = project_root / "plat" / "agentic-task"
        plat.mkdir(parents=True, exist_ok=True)
        (project_root / ".agentic-framework").write_text(
            f"framework=AgenticTask\nrepo={plat}\n", encoding="utf-8"
        )
    else:
        plat = project_root / ".agents" / "skills" / "agentic-task"
        plat.mkdir(parents=True, exist_ok=True)
    scripts = plat / "scripts"
    scripts.mkdir(exist_ok=True)
    (scripts / "detect_root.py").write_text(
        "import json, sys\n"
        f"print(json.dumps({{'PLATFORM_DIR': {str(plat)!r}, "
        f"'PROJECT_ROOT': {str(project_root)!r}, 'method': 'stub'}}))\n",
        encoding="utf-8",
    )
    # Stub advance: echoes argv as repr (proves list-form args, no shell
    # re-splitting) and honors a trailing exit:<N> control arg.
    (scripts / "advance_phase.py").write_text(
        "import sys\n"
        "args = sys.argv[1:]\n"
        "code = 0\n"
        "if args and args[-1].startswith('exit:'):\n"
        "    code = int(args[-1][5:]); args = args[:-1]\n"
        "print('ARGV=' + repr(args))\n"
        "sys.exit(code)\n",
        encoding="utf-8",
    )
    return plat


def test_advance_stub_framework_marker_path(tmp_path: pathlib.Path) -> None:
    adv.invalidate_script_cache()
    (tmp_path / ".agenticdoc").mkdir()
    _stub_framework(tmp_path, via_marker=True)
    platform = adv.locate_platform_dir(tmp_path)
    assert (platform / "scripts" / "advance_phase.py").is_file()
    code, out, err = adv.advance("my key", "verify", tmp_path)
    assert code == 0
    assert "ARGV=['my key', 'verify']" in out  # space survives: no shell=True
    _verify("VC-027", advance_stub_exit=0, advance_no_shell=true_str(True))


def test_advance_stub_framework_standard_layout(tmp_path: pathlib.Path) -> None:
    adv.invalidate_script_cache()
    (tmp_path / ".agenticdoc").mkdir()
    _stub_framework(tmp_path, via_marker=False)
    code, out, err = adv.advance("k", "verify", tmp_path, summary="done stuff")
    assert code == 0
    assert "'--summary'" in out and "done stuff" in out
    _verify("VC-027", advance_summary_passthrough=true_str(True))


def test_advance_exit_code_passthrough(tmp_path: pathlib.Path) -> None:
    adv.invalidate_script_cache()
    (tmp_path / ".agenticdoc").mkdir()
    _stub_framework(tmp_path, via_marker=False)
    code, out, err = adv.advance("k", "exit:3", tmp_path)
    assert code == 3  # untouched: interpretation is the caller's
    _verify("VC-027", advance_exit_code_passthrough=true_str(True))


def test_advance_timeout_returns_not_raises(tmp_path: pathlib.Path, monkeypatch) -> None:
    adv.invalidate_script_cache()
    (tmp_path / ".agenticdoc").mkdir()
    plat = _stub_framework(tmp_path, via_marker=False)
    (plat / "scripts" / "advance_phase.py").write_text(
        "import time\ntime.sleep(30)\n", encoding="utf-8"
    )
    monkeypatch.setattr(adv, "_ADVANCE_TIMEOUT_SEC", 1)
    code, out, err = adv.advance("k", "verify", tmp_path)
    assert code == 124 and "timed out" in err
    _verify("VC-027", advance_timeout=124)


def test_marker_pointing_at_missing_repo_falls_back(tmp_path: pathlib.Path) -> None:
    """A stale marker (repo path gone) must not brick the project: the
    standard .agents layout still resolves."""
    adv.invalidate_script_cache()
    (tmp_path / ".agenticdoc").mkdir()
    (tmp_path / ".agentic-framework").write_text(
        "framework=AgenticTask\nrepo=C:\\definitely\\not\\here\n", encoding="utf-8"
    )
    _stub_framework(tmp_path, via_marker=False)
    platform = adv.locate_platform_dir(tmp_path)
    assert platform == tmp_path / ".agents" / "skills" / "agentic-task"


def _bad_framework(project_root: pathlib.Path) -> pathlib.Path:
    """A framework whose detect_root reports a *different* project root."""
    bad = project_root / "badfw"
    (bad / "scripts").mkdir(parents=True, exist_ok=True)
    (bad / "scripts" / "advance_phase.py").write_text("", encoding="utf-8")
    (bad / "scripts" / "detect_root.py").write_text(
        "import json\n"
        "print(json.dumps({'PLATFORM_DIR': %r, 'PROJECT_ROOT': %r}))\n"
        % (str(bad), str(project_root / "somewhere-else")),
        encoding="utf-8",
    )
    return bad


def test_inconsistent_marker_candidate_falls_back_to_consistent_layout(
    tmp_path: pathlib.Path,
) -> None:
    """Marker repo that resolves to another project must be skipped; the
    standard in-project layout still resolves."""
    adv.invalidate_script_cache()
    (tmp_path / ".agenticdoc").mkdir()
    bad = _bad_framework(tmp_path)
    (tmp_path / ".agentic-framework").write_text(f"repo={bad}\n", encoding="utf-8")
    good = _stub_framework(tmp_path, via_marker=False)
    assert adv.locate_platform_dir(tmp_path) == good
    _verify("VC-027", inconsistent_marker_skipped=true_str(True))


def test_no_consistent_candidate_fails_loud(tmp_path: pathlib.Path) -> None:
    """No candidate resolves to this project -> AdvanceError, never a silent
    wrong-repo write (the 2026-09-22 autopilot blocker)."""
    adv.invalidate_script_cache()
    (tmp_path / ".agenticdoc").mkdir()
    bad = _bad_framework(tmp_path)
    (tmp_path / ".agentic-framework").write_text(f"repo={bad}\n", encoding="utf-8")
    with pytest.raises(adv.AdvanceError) as excinfo:
        adv.locate_platform_dir(tmp_path)
    assert "resolves to this project's root" in str(excinfo.value)
    code, out, err = adv.advance("k", "design", tmp_path)
    assert code == 1 and out == ""
    assert "resolves to this project's root" in err
    _verify("VC-027", fail_loud=1, readable=true_str("?" not in err))


def test_python_utf8_flag_passed_to_children(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both the detect_root probe and the advance call force UTF-8 stdio
    (cp936 Chinese diagnostics otherwise decode to '?')."""
    adv.invalidate_script_cache()
    (tmp_path / ".agenticdoc").mkdir()
    _stub_framework(tmp_path, via_marker=False)
    calls: list[list[str]] = []
    real_run = subprocess.run

    def spy(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(list(cmd))
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(adv.subprocess, "run", spy)
    code, _out, _err = adv.advance("k", "verify", tmp_path)
    assert code == 0
    assert calls, "expected detect_root + advance subprocess calls"
    for cmd in calls:
        assert cmd[1:3] == ["-X", "utf8"], cmd
    _verify("VC-027", utf8_flags=len(calls), argv_flags=true_str(True))
