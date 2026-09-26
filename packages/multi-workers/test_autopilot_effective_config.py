"""test_autopilot_effective_config.py — L1 truth table for the layered
effective-config resolver (T-02, AC-007 / VC-007).

Every case isolates the environment with
``mock.patch.dict(os.environ, {...}, clear=True)`` so no real HOME/USERPROFILE
(or MW_AUTOPILOT_*) can leak in, builds its own project root under tmp_path,
and asserts value + origin + diagnostics for each field of interest. The
read-only cases additionally assert zero footprint (no ``.mw/``, no
``.agenticdoc/``, no ``.agents/`` created).
"""
import json
import os
import pathlib
import sys
from unittest import mock

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from autopilot import config as cfg
from autopilot import conductor, effective_config as ec, timeline  # noqa: E402


def _verify(tag: str, **kv) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()))


def _env(**kv: str):  # noqa: ANN201 - a context manager, type not worth importing
    """Hermetic os.environ: clear=True, then only the given keys."""
    return mock.patch.dict(os.environ, kv, clear=True)


def _machine_file(directory: pathlib.Path, payload: object) -> pathlib.Path:
    path = directory / "machine.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8", newline="\n"
    )
    return path


def _machine_text(directory: pathlib.Path, text: str) -> pathlib.Path:
    path = directory / "machine.json"
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _project_file(project_root: pathlib.Path, payload: dict) -> pathlib.Path:
    path = cfg.config_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8", newline="\n"
    )
    return path


def _home_with_machine(home: pathlib.Path, payload: object) -> pathlib.Path:
    target = home / ".agents" / "autopilot-defaults.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload), encoding="utf-8", newline="\n")
    return target


def _assert_full_view(eff: ec.EffectiveConfig) -> None:
    assert set(eff.values) == set(cfg.DEFAULT_CONFIG)
    assert len(eff.values) == 13
    assert set(eff.origins) == set(cfg.DEFAULT_CONFIG)
    assert set(eff.origins.values()) <= set(ec.ORIGINS)


# ── path resolution: 4 env combinations + no-fallback + zero footprint ───────

def test_machine_path_resolution_table(tmp_path: pathlib.Path) -> None:
    file_home = tmp_path / "file_home"
    machine_a = _home_with_machine(file_home, {})
    other_home = tmp_path / "other_home"
    machine_b = _home_with_machine(other_home, {})

    # 1. MW_AUTOPILOT_FILE wins over MW_AUTOPILOT_HOME and HOME.
    with _env(
        MW_AUTOPILOT_FILE=str(machine_a),
        MW_AUTOPILOT_HOME=str(other_home),
        HOME=str(other_home),
    ):
        assert ec.machine_config_path() == machine_a

    # 2. MW_AUTOPILOT_FILE set but missing -> None, no fallback to HOME.
    with _env(
        MW_AUTOPILOT_FILE=str(tmp_path / "gone.json"),
        MW_AUTOPILOT_HOME=str(other_home),
        HOME=str(other_home),
        USERPROFILE=str(other_home),
    ):
        assert ec.machine_config_path() is None

    # 3. MW_AUTOPILOT_HOME wins over HOME / USERPROFILE.
    with _env(MW_AUTOPILOT_HOME=str(other_home), HOME=str(file_home), USERPROFILE=str(file_home)):
        assert ec.machine_config_path() == machine_b

    # 4. HOME, then USERPROFILE fallback.
    with _env(HOME=str(other_home)):
        assert ec.machine_config_path() == machine_b
    with _env(USERPROFILE=str(other_home)):
        assert ec.machine_config_path() == machine_b

    # 5. No candidate -> None, and no directory is created.
    empty_home = tmp_path / "empty_home"
    empty_home.mkdir()
    with _env(MW_AUTOPILOT_HOME=str(empty_home), HOME=str(empty_home)):
        assert ec.machine_config_path() is None
    assert not (empty_home / ".agents").exists()
    _verify("机器层路径解析（4 种 env 组合）", file_override=1, file_missing_no_fallback=1,
            home_override=1, home_then_userprofile=1, zero_footprint="true")


# ── missing layers / defaults ───────────────────────────────────────────────

def test_both_layers_missing_all_defaults_zero_footprint(tmp_path: pathlib.Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    project = tmp_path / "proj"
    with _env(MW_AUTOPILOT_HOME=str(home), HOME=str(home)):
        eff = ec.load_effective(project)
    _assert_full_view(eff)
    assert eff.values == cfg.DEFAULT_CONFIG
    assert all(origin == "default" for origin in eff.origins.values())
    assert eff.diagnostics == []
    assert eff.machine_path is None
    # Read-only: no project file tree, no lock dir, no machine dir created.
    assert not (project / ".agenticdoc").exists()
    assert not (project / ".mw").exists()
    assert not (project / ".agents").exists()
    assert not (home / ".agents").exists()
    _verify("只读零足迹", mw_dir="false", agenticdoc_dir="false", agents_dir="false")


def test_machine_layer_overrides_only_effective_keys(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "proj"
    machine = _machine_file(
        tmp_path,
        {
            "xkey_repair": True,
            "xkey_verify_cmd": ["python", "-m", "pytest", "-q"],
            "xkey_verify_timeout_s": 120,
            "xkey_verify_cwd": "partition",
        },
    )
    with _env(MW_AUTOPILOT_FILE=str(machine)):
        eff = ec.load_effective(project)
    _assert_full_view(eff)
    assert eff.machine_path == machine
    assert eff.diagnostics == []
    assert eff.values["xkey_repair"] is True
    assert eff.values["xkey_verify_cmd"] == ["python", "-m", "pytest", "-q"]
    assert eff.values["xkey_verify_timeout_s"] == 120
    assert eff.values["xkey_verify_cwd"] == "partition"
    assert eff.values["enabled"] is False  # machine layer never touches run state
    assert eff.origins["enabled"] == "default"
    for key in ec.EFFECTIVE_KEYS:
        assert eff.origins[key] == "machine", key
    assert all(
        eff.origins[key] == "default"
        for key in cfg.DEFAULT_CONFIG
        if key not in ec.EFFECTIVE_KEYS
    )
    _verify("逐字段 origin", machine_keys=len(ec.EFFECTIVE_KEYS), run_state="default")


def test_project_partial_file_completed_and_origin_project(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "proj"
    _project_file(project, {"xkey_verify_cmd": ["pytest"]})
    with _env():
        eff = ec.load_effective(project)
    _assert_full_view(eff)
    assert eff.values["xkey_verify_cmd"] == ["pytest"]
    assert eff.origins["xkey_verify_cmd"] == "project"
    assert eff.values["enabled"] is False
    assert eff.origins["enabled"] == "default"
    assert eff.diagnostics == []
    _verify("逐字段 origin", partial_project_keys=13, project_origin="project")


def test_project_beats_machine_per_field(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "proj"
    _project_file(project, {"xkey_verify_timeout_s": 90})
    machine = _machine_file(
        tmp_path,
        {
            "xkey_repair": True,
            "xkey_verify_cmd": ["machine-cmd"],
            "xkey_verify_timeout_s": 600,
            "xkey_verify_cwd": "control",
        },
    )
    with _env(MW_AUTOPILOT_FILE=str(machine)):
        eff = ec.load_effective(project)
    assert eff.values["xkey_verify_timeout_s"] == 90
    assert eff.origins["xkey_verify_timeout_s"] == "project"
    assert eff.values["xkey_verify_cmd"] == ["machine-cmd"]
    assert eff.origins["xkey_verify_cmd"] == "machine"
    assert eff.origins["xkey_repair"] == "machine"
    assert eff.origins["xkey_verify_cwd"] == "machine"
    _verify("逐字段 origin", project_wins="xkey_verify_timeout_s",
            machine_wins=3, timeout=eff.values["xkey_verify_timeout_s"])


def test_project_explicit_default_value_still_beats_machine(tmp_path: pathlib.Path) -> None:
    """An explicit project value equal to the built-in default is still 'project'."""
    project = tmp_path / "proj"
    _project_file(project, {"xkey_verify_timeout_s": 1800})
    machine = _machine_file(tmp_path, {"xkey_verify_timeout_s": 600})
    with _env(MW_AUTOPILOT_FILE=str(machine)):
        eff = ec.load_effective(project)
    assert eff.values["xkey_verify_timeout_s"] == 1800
    assert eff.origins["xkey_verify_timeout_s"] == "project"


# ── MW_AUTOPILOT_FILE missing: no HOME fallback ─────────────────────────────

def test_machine_file_missing_does_not_fall_back_to_home(tmp_path: pathlib.Path) -> None:
    home = tmp_path / "home"
    _home_with_machine(home, {"xkey_verify_timeout_s": 600})
    project = tmp_path / "proj"
    with _env(
        MW_AUTOPILOT_FILE=str(tmp_path / "gone.json"),
        MW_AUTOPILOT_HOME=str(home),
        HOME=str(home),
    ):
        eff = ec.load_effective(project)
    _assert_full_view(eff)
    assert eff.machine_path is None
    assert eff.values["xkey_verify_timeout_s"] == 1800
    assert all(origin == "default" for origin in eff.origins.values())
    assert eff.diagnostics == []
    _verify("机器层路径解析（4 种 env 组合）", file_missing_no_fallback="true",
            timeout=eff.values["xkey_verify_timeout_s"])


# ── fail-soft machine layer: per-field diagnostics ──────────────────────────

def test_out_of_domain_and_unknown_keys_ignored_with_diagnostics(
    tmp_path: pathlib.Path,
) -> None:
    project = tmp_path / "proj"
    machine = _machine_file(
        tmp_path,
        {
            "enabled": True,
            "xkey_verify_cmds": ["typo"],
            "xkey_verify_timeout_s": 300,
        },
    )
    with _env(MW_AUTOPILOT_FILE=str(machine)):
        eff = ec.load_effective(project)
    _assert_full_view(eff)
    assert eff.values["enabled"] is False
    assert eff.origins["enabled"] == "default"
    assert eff.values["xkey_verify_timeout_s"] == 300
    assert eff.origins["xkey_verify_timeout_s"] == "machine"
    assert len(eff.diagnostics) == 2
    assert any("enabled" in d and "not machine-overridable" in d for d in eff.diagnostics)
    assert any("xkey_verify_cmds" in d and "unknown key" in d for d in eff.diagnostics)
    assert all(str(machine) in d for d in eff.diagnostics)
    _verify("fail-soft diagnostics", out_of_domain=1, unknown_key=1,
            diagnostics=len(eff.diagnostics))


def test_single_bad_field_dropped_others_apply(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "proj"
    machine = _machine_file(
        tmp_path,
        {"xkey_verify_timeout_s": "600", "xkey_repair": True},
    )
    with _env(MW_AUTOPILOT_FILE=str(machine)):
        eff = ec.load_effective(project)
    # Bad field dropped -> built-in default wins; sibling field still applies.
    assert eff.values["xkey_verify_timeout_s"] == 1800
    assert eff.origins["xkey_verify_timeout_s"] == "default"
    assert eff.values["xkey_repair"] is True
    assert eff.origins["xkey_repair"] == "machine"
    assert len(eff.diagnostics) == 1
    assert "xkey_verify_timeout_s" in eff.diagnostics[0]
    _verify("fail-soft diagnostics", bad_field_dropped="xkey_verify_timeout_s",
            sibling_applied="xkey_repair")


def test_bad_machine_field_lower_layer_wins(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "proj"
    _project_file(project, {"xkey_verify_timeout_s": 90})
    machine = _machine_file(tmp_path, {"xkey_verify_timeout_s": "600"})
    with _env(MW_AUTOPILOT_FILE=str(machine)):
        eff = ec.load_effective(project)
    assert eff.values["xkey_verify_timeout_s"] == 90
    assert eff.origins["xkey_verify_timeout_s"] == "project"
    assert any("xkey_verify_timeout_s" in d for d in eff.diagnostics)


def test_broken_machine_json_layer_empty_project_still_wins(
    tmp_path: pathlib.Path,
) -> None:
    project = tmp_path / "proj"
    _project_file(project, {"xkey_verify_timeout_s": 90})
    machine = _machine_text(tmp_path, "{not json")
    with _env(MW_AUTOPILOT_FILE=str(machine)):
        eff = ec.load_effective(project)
    _assert_full_view(eff)
    assert eff.values["xkey_verify_timeout_s"] == 90
    assert eff.origins["xkey_verify_timeout_s"] == "project"
    assert eff.values["enabled"] is False
    assert len(eff.diagnostics) == 1
    assert str(machine) in eff.diagnostics[0]
    _verify("fail-soft diagnostics", broken_json=1, project_layer_intact="true")


def test_machine_top_level_not_object_layer_empty(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "proj"
    machine = _machine_text(tmp_path, "[1, 2, 3]")
    with _env(MW_AUTOPILOT_FILE=str(machine)):
        eff = ec.load_effective(project)
    assert eff.values == cfg.DEFAULT_CONFIG
    assert all(origin == "default" for origin in eff.origins.values())
    assert len(eff.diagnostics) == 1
    assert "JSON object" in eff.diagnostics[0]


def test_machine_null_is_noop(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "proj"
    machine = _machine_file(
        tmp_path, {"xkey_verify_cmd": None, "xkey_repair": None}
    )
    with _env(MW_AUTOPILOT_FILE=str(machine)):
        eff = ec.load_effective(project)
    assert eff.values["xkey_verify_cmd"] == []
    assert eff.origins["xkey_verify_cmd"] == "default"
    assert eff.values["xkey_repair"] is False
    assert eff.origins["xkey_repair"] == "default"
    assert eff.diagnostics == []
    _verify("逐字段 origin", machine_null_noop="true", diagnostics=0)


def test_machine_non_ascii_command_preserved(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "proj"
    machine = _machine_file(tmp_path, {"xkey_verify_cmd": ["echo", "中文-命令"]})
    with _env(MW_AUTOPILOT_FILE=str(machine)):
        eff = ec.load_effective(project)
    assert eff.values["xkey_verify_cmd"] == ["echo", "中文-命令"]
    assert eff.origins["xkey_verify_cmd"] == "machine"
    assert eff.diagnostics == []


# ── project layer stays fail-closed: machine cannot rescue it ───────────────

@pytest.mark.parametrize(
    "bad_project",
    [
        {"totally_unknown": 1},
        {"xkey_verify_timeout_s": "90"},
        {"enabled": "yes"},
        {"xkey_verify_cwd": ["control"]},
    ],
)
def test_invalid_project_raises_config_error_before_merge(
    tmp_path: pathlib.Path, bad_project: dict
) -> None:
    project = tmp_path / "proj"
    _project_file(project, bad_project)
    machine = _machine_file(tmp_path, {"xkey_verify_timeout_s": 600})
    with _env(MW_AUTOPILOT_FILE=str(machine)):
        with pytest.raises(cfg.ConfigError):
            ec.load_effective(project)
    _verify("fail-soft diagnostics", project_fail_closed="true",
            machine_rescue="false")


# ── consumer side: fail-soft machine layer must not poison the conductor ────

def test_consumer_conductor_tick_ok_with_machine_layer(tmp_path: pathlib.Path) -> None:
    """The conductor keeps ticking ("ok", never "error") while a machine layer
    is present; the same scenario resolves through load_effective.

    Note: conductor.tick still reads the project layer via config.cached_load
    (the switch to load_effective is T-06); this case pins the fail-soft
    contract that a machine-layer typo cannot surface as a tick error, and
    that the resolver view is coherent with the machine file.
    """
    project = tmp_path / "proj"
    (project / ".agenticdoc").mkdir(parents=True)
    (project / ".agenticdoc" / "goal.md").write_text("# Goal\n", encoding="utf-8")
    # Minimal project file: only `enabled`, so the machine xkey command is visible.
    cfg.save_config(project, {"enabled": True})

    machine = _machine_file(
        tmp_path,
        {
            "xkey_verify_cmd": ["python", "-m", "pytest", "-q"],
            "xkey_verify_cmds": ["typo"],
            "xkey_verify_timeout_s": "600",
        },
    )
    with _env(MW_AUTOPILOT_FILE=str(machine)):
        eff = ec.load_effective(project)
        st = conductor.ConductorState(
            timeline.Timeline(timeline.timeline_path(project)),
            conductor.goal_mtime_ns(project),
        )
        status = conductor.tick(project, st)

    assert status == "ok"
    assert eff.values["xkey_verify_cmd"] == ["python", "-m", "pytest", "-q"]
    assert eff.origins["xkey_verify_cmd"] == "machine"
    assert eff.values["xkey_verify_timeout_s"] == 1800  # bad machine field dropped
    assert any("xkey_verify_cmds" in d for d in eff.diagnostics)
    assert any("xkey_verify_timeout_s" in d for d in eff.diagnostics)
    _verify("fail-soft diagnostics", tick_status=status, machine_command_visible="true")
