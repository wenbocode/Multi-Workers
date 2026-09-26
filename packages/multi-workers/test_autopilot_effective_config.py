"""test_autopilot_effective_config.py — L1 truth table for the layered
effective-config resolver (T-02b, AC-007 / VC-007).

Every case isolates the environment with
``mock.patch.dict(os.environ, {...}, clear=True)`` so no real HOME/USERPROFILE
(or MW_AUTOPILOT_*) can leak in, builds its own project root under tmp_path,
and asserts value + origin + diagnostics for each field of interest. The
read-only cases additionally assert zero footprint (no ``.mw/``, no
``.agenticdoc/``, no ``.agents/`` created).

Revision 2026-09-26 (T-02b): machine domain is ``xkey_verify_cmd`` +
``xkey_verify_cwd`` only, and the rule is "empty value = undecided"
(``[]`` / ``""`` defer to the machine layer) — the ``tt1``…``tt8`` cases below
pin the truth table; ``tt8`` is the core regression for the materializing
writers (``save_config`` / TS ``saveConfig``).
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


def test_machine_layer_overrides_effective_keys_only(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "proj"
    machine = _machine_file(
        tmp_path,
        {
            "xkey_verify_cmd": ["python", "-m", "pytest", "-q"],
            "xkey_verify_cwd": "partition",
        },
    )
    with _env(MW_AUTOPILOT_FILE=str(machine)):
        eff = ec.load_effective(project)
    _assert_full_view(eff)
    assert eff.machine_path == machine
    assert eff.diagnostics == []
    assert eff.values["xkey_verify_cmd"] == ["python", "-m", "pytest", "-q"]
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


def test_partial_file_raw_loader_vs_effective_full_view(
    tmp_path: pathlib.Path,
) -> None:
    """T-02c layering evidence: raw loader vs complete resolver view.

    One project file carrying a single key, one call site, both halves of the
    contract: ``config.load_config`` returns *only* the written key (D-004
    withdrawn — no default fill), while ``load_effective`` is self-sufficient
    and yields all 13 keys (hard-subscript safe for conductor-style callers).
    """
    project = tmp_path / "proj"
    _project_file(project, {"l2_read_file_cap": 3})
    with _env():
        loaded = cfg.load_config(project)
        eff = ec.load_effective(project)
    # Raw loader: exactly the one written key.
    assert set(loaded) == {"l2_read_file_cap"}
    assert loaded == {"l2_read_file_cap": 3}
    # Resolver: complete 13-key view (== default_config key set), hard-subscript safe.
    assert set(eff.values) == set(cfg.default_config())
    assert len(eff.values) == 13
    assert eff.values["l2_read_file_cap"] == 3
    assert eff.origins["l2_read_file_cap"] == "project"
    assert eff.values["l2_read_byte_cap"] == cfg.DEFAULT_CONFIG["l2_read_byte_cap"]
    assert eff.origins["l2_read_byte_cap"] == "default"
    assert eff.diagnostics == []
    _verify(
        "原始加载器 vs 完整视图",
        load_config_keys=len(loaded),
        effective_keys=len(eff.values),
        effective_key_set=len(set(eff.values) & set(cfg.default_config())),
    )


def test_project_nonempty_values_win_over_machine_per_field(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "proj"
    _project_file(project, {"xkey_verify_cmd": ["p"], "xkey_verify_cwd": "control"})
    machine = _machine_file(
        tmp_path, {"xkey_verify_cmd": ["m"], "xkey_verify_cwd": "partition"}
    )
    with _env(MW_AUTOPILOT_FILE=str(machine)):
        eff = ec.load_effective(project)
    assert eff.values["xkey_verify_cmd"] == ["p"]
    assert eff.origins["xkey_verify_cmd"] == "project"
    assert eff.values["xkey_verify_cwd"] == "control"
    assert eff.origins["xkey_verify_cwd"] == "project"
    assert eff.diagnostics == []
    _verify("逐字段 origin", project_wins=2, machine_wins=0)


# ── T-02b truth table: empty value = undecided (requested cases 1..8) ────────

def test_tt1_project_empty_machine_value_machine_wins(tmp_path: pathlib.Path) -> None:
    """(1) project ``[]`` + machine ``["m"]`` => value ``["m"]``, origin machine."""
    project = tmp_path / "proj"
    _project_file(project, {"xkey_verify_cmd": []})
    machine = _machine_file(tmp_path, {"xkey_verify_cmd": ["m"]})
    with _env(MW_AUTOPILOT_FILE=str(machine)):
        eff = ec.load_effective(project)
    assert eff.values["xkey_verify_cmd"] == ["m"]
    assert eff.origins["xkey_verify_cmd"] == "machine"
    assert eff.diagnostics == []
    _verify("空值即未决定 真值表", case=1, project="[]", machine="['m']",
            value=eff.values["xkey_verify_cmd"], origin=eff.origins["xkey_verify_cmd"])


def test_tt2_project_nonempty_machine_value_project_wins(tmp_path: pathlib.Path) -> None:
    """(2) project ``["p"]`` + machine ``["m"]`` => value ``["p"]``, origin project."""
    project = tmp_path / "proj"
    _project_file(project, {"xkey_verify_cmd": ["p"]})
    machine = _machine_file(tmp_path, {"xkey_verify_cmd": ["m"]})
    with _env(MW_AUTOPILOT_FILE=str(machine)):
        eff = ec.load_effective(project)
    assert eff.values["xkey_verify_cmd"] == ["p"]
    assert eff.origins["xkey_verify_cmd"] == "project"
    _verify("空值即未决定 真值表", case=2, project="['p']", machine="['m']",
            value=eff.values["xkey_verify_cmd"], origin=eff.origins["xkey_verify_cmd"])


def test_tt3_project_missing_machine_value_machine(tmp_path: pathlib.Path) -> None:
    """(3) project missing + machine ``["m"]`` => origin machine."""
    project = tmp_path / "proj"
    machine = _machine_file(tmp_path, {"xkey_verify_cmd": ["m"]})
    with _env(MW_AUTOPILOT_FILE=str(machine)):
        eff = ec.load_effective(project)
    assert eff.values["xkey_verify_cmd"] == ["m"]
    assert eff.origins["xkey_verify_cmd"] == "machine"
    _verify("空值即未决定 真值表", case=3, project="missing", machine="['m']",
            value=eff.values["xkey_verify_cmd"], origin=eff.origins["xkey_verify_cmd"])


def test_tt4_project_empty_machine_missing_default_empty(tmp_path: pathlib.Path) -> None:
    """(4) project ``[]`` + machine missing => origin default, value ``[]``."""
    project = tmp_path / "proj"
    _project_file(project, {"xkey_verify_cmd": []})
    with _env():
        eff = ec.load_effective(project)
    assert eff.values["xkey_verify_cmd"] == []
    assert eff.origins["xkey_verify_cmd"] == "default"
    _verify("空值即未决定 真值表", case=4, project="[]", machine="missing",
            value=eff.values["xkey_verify_cmd"], origin=eff.origins["xkey_verify_cmd"])


def test_tt5_project_empty_machine_empty_default(tmp_path: pathlib.Path) -> None:
    """(5) project ``[]`` + machine ``[]`` => origin default."""
    project = tmp_path / "proj"
    _project_file(project, {"xkey_verify_cmd": []})
    machine = _machine_file(tmp_path, {"xkey_verify_cmd": []})
    with _env(MW_AUTOPILOT_FILE=str(machine)):
        eff = ec.load_effective(project)
    assert eff.values["xkey_verify_cmd"] == []
    assert eff.origins["xkey_verify_cmd"] == "default"
    assert eff.diagnostics == []
    _verify("空值即未决定 真值表", case=5, project="[]", machine="[]",
            value=eff.values["xkey_verify_cmd"], origin=eff.origins["xkey_verify_cmd"])


def test_tt6_cwd_truth_table(tmp_path: pathlib.Path) -> None:
    """(6) cwd ``""`` + machine ``"partition"`` => machine;
    cwd ``"control"`` + machine ``"partition"`` => project."""
    empty_project = tmp_path / "empty"
    _project_file(empty_project, {"xkey_verify_cwd": ""})
    set_project = tmp_path / "set"
    _project_file(set_project, {"xkey_verify_cwd": "control"})
    machine = _machine_file(tmp_path, {"xkey_verify_cwd": "partition"})
    with _env(MW_AUTOPILOT_FILE=str(machine)):
        empty_eff = ec.load_effective(empty_project)
        set_eff = ec.load_effective(set_project)
    assert empty_eff.values["xkey_verify_cwd"] == "partition"
    assert empty_eff.origins["xkey_verify_cwd"] == "machine"
    assert set_eff.values["xkey_verify_cwd"] == "control"
    assert set_eff.origins["xkey_verify_cwd"] == "project"
    _verify("空值即未决定 真值表", case=6,
            cwd_empty_machine="partition/machine", cwd_set_machine="control/project")


def test_tt7_machine_out_of_domain_repair_timeout_ignored(tmp_path: pathlib.Path) -> None:
    """(7) machine ``xkey_repair`` / ``xkey_verify_timeout_s`` are out of domain:
    warning + ignored, origin comes from project or default."""
    # (a) no project keys: both fall back to built-in defaults.
    bare = tmp_path / "bare"
    machine = _machine_file(
        tmp_path, {"xkey_repair": True, "xkey_verify_timeout_s": 600}
    )
    with _env(MW_AUTOPILOT_FILE=str(machine)):
        bare_eff = ec.load_effective(bare)
    assert bare_eff.values["xkey_repair"] is False
    assert bare_eff.origins["xkey_repair"] == "default"
    assert bare_eff.values["xkey_verify_timeout_s"] == 1800
    assert bare_eff.origins["xkey_verify_timeout_s"] == "default"
    assert len(bare_eff.diagnostics) == 2
    assert any(
        "xkey_repair" in d and "not machine-overridable" in d
        for d in bare_eff.diagnostics
    )
    assert any(
        "xkey_verify_timeout_s" in d and "not machine-overridable" in d
        for d in bare_eff.diagnostics
    )

    # (b) project carries both explicitly: origin project, value untouched.
    declared = tmp_path / "declared"
    _project_file(declared, {"xkey_repair": True, "xkey_verify_timeout_s": 300})
    with _env(MW_AUTOPILOT_FILE=str(machine)):
        declared_eff = ec.load_effective(declared)
    assert declared_eff.values["xkey_repair"] is True
    assert declared_eff.origins["xkey_repair"] == "project"
    assert declared_eff.values["xkey_verify_timeout_s"] == 300
    assert declared_eff.origins["xkey_verify_timeout_s"] == "project"
    assert len(declared_eff.diagnostics) == 2
    _verify("越域越界告警", out_of_domain=2, default_origins=2, project_origins=2,
            diagnostics=len(bare_eff.diagnostics))


def test_tt8_materialized_project_still_takes_machine(tmp_path: pathlib.Path) -> None:
    """(8) CORE REGRESSION: a project file materialized with all 13 keys
    (``xkey_verify_cmd: []`` as written by scan/console) must still inherit the
    machine-layer command."""
    project = tmp_path / "proj"
    materialized = dict(cfg.DEFAULT_CONFIG)
    materialized["enabled"] = True
    assert materialized["xkey_verify_cmd"] == []
    assert materialized["xkey_verify_cwd"] == ""
    _project_file(project, materialized)
    machine = _machine_file(
        tmp_path,
        {"xkey_verify_cmd": ["python", "-m", "pytest", "-q"], "xkey_verify_cwd": "partition"},
    )
    with _env(MW_AUTOPILOT_FILE=str(machine)):
        eff = ec.load_effective(project)
    assert eff.values["xkey_verify_cmd"] == ["python", "-m", "pytest", "-q"]
    assert eff.origins["xkey_verify_cmd"] == "machine"
    assert eff.values["xkey_verify_cwd"] == "partition"
    assert eff.origins["xkey_verify_cwd"] == "machine"
    assert eff.values["enabled"] is True
    assert eff.origins["enabled"] == "project"
    assert eff.diagnostics == []
    _verify("材料化场景仍取机器层", project_keys=13, machine_cmd=eff.values["xkey_verify_cmd"],
            machine_cwd=eff.values["xkey_verify_cwd"], cmd_origin=eff.origins["xkey_verify_cmd"])


# ── MW_AUTOPILOT_FILE missing: no HOME fallback ─────────────────────────────

def test_machine_file_missing_does_not_fall_back_to_home(tmp_path: pathlib.Path) -> None:
    home = tmp_path / "home"
    _home_with_machine(home, {"xkey_verify_cmd": ["m"]})
    project = tmp_path / "proj"
    with _env(
        MW_AUTOPILOT_FILE=str(tmp_path / "gone.json"),
        MW_AUTOPILOT_HOME=str(home),
        HOME=str(home),
    ):
        eff = ec.load_effective(project)
    _assert_full_view(eff)
    assert eff.machine_path is None
    assert eff.values["xkey_verify_cmd"] == []
    assert all(origin == "default" for origin in eff.origins.values())
    assert eff.diagnostics == []
    _verify("机器层路径解析（4 种 env 组合）", file_missing_no_fallback="true",
            cmd=eff.values["xkey_verify_cmd"])


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
            "xkey_verify_cmd": ["ok"],
        },
    )
    with _env(MW_AUTOPILOT_FILE=str(machine)):
        eff = ec.load_effective(project)
    _assert_full_view(eff)
    assert eff.values["enabled"] is False
    assert eff.origins["enabled"] == "default"
    assert eff.values["xkey_verify_timeout_s"] == 1800
    assert eff.origins["xkey_verify_timeout_s"] == "default"
    assert eff.values["xkey_verify_cmd"] == ["ok"]
    assert eff.origins["xkey_verify_cmd"] == "machine"
    assert len(eff.diagnostics) == 3
    assert any("enabled" in d and "not machine-overridable" in d for d in eff.diagnostics)
    assert any("xkey_verify_cmds" in d and "unknown key" in d for d in eff.diagnostics)
    assert any(
        "xkey_verify_timeout_s" in d and "not machine-overridable" in d
        for d in eff.diagnostics
    )
    assert all(str(machine) in d for d in eff.diagnostics)
    _verify("fail-soft diagnostics", out_of_domain=2, unknown_key=1,
            diagnostics=len(eff.diagnostics))


def test_single_bad_field_dropped_others_apply(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "proj"
    machine = _machine_file(
        tmp_path,
        {"xkey_verify_cmd": "pytest", "xkey_verify_cwd": "partition"},
    )
    with _env(MW_AUTOPILOT_FILE=str(machine)):
        eff = ec.load_effective(project)
    # Bad field dropped -> built-in default wins; sibling field still applies.
    assert eff.values["xkey_verify_cmd"] == []
    assert eff.origins["xkey_verify_cmd"] == "default"
    assert eff.values["xkey_verify_cwd"] == "partition"
    assert eff.origins["xkey_verify_cwd"] == "machine"
    assert len(eff.diagnostics) == 1
    assert "xkey_verify_cmd" in eff.diagnostics[0]
    _verify("fail-soft diagnostics", bad_field_dropped="xkey_verify_cmd",
            sibling_applied="xkey_verify_cwd")


def test_bad_machine_field_lower_layer_wins(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "proj"
    _project_file(project, {"xkey_verify_cmd": ["p"]})
    machine = _machine_file(tmp_path, {"xkey_verify_cmd": "600"})
    with _env(MW_AUTOPILOT_FILE=str(machine)):
        eff = ec.load_effective(project)
    assert eff.values["xkey_verify_cmd"] == ["p"]
    assert eff.origins["xkey_verify_cmd"] == "project"
    assert any("xkey_verify_cmd" in d for d in eff.diagnostics)


def test_broken_machine_json_layer_empty_project_still_wins(
    tmp_path: pathlib.Path,
) -> None:
    project = tmp_path / "proj"
    _project_file(project, {"xkey_verify_cmd": ["p"]})
    machine = _machine_text(tmp_path, "{not json")
    with _env(MW_AUTOPILOT_FILE=str(machine)):
        eff = ec.load_effective(project)
    _assert_full_view(eff)
    assert eff.values["xkey_verify_cmd"] == ["p"]
    assert eff.origins["xkey_verify_cmd"] == "project"
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
        tmp_path, {"xkey_verify_cmd": None, "xkey_verify_cwd": None}
    )
    with _env(MW_AUTOPILOT_FILE=str(machine)):
        eff = ec.load_effective(project)
    assert eff.values["xkey_verify_cmd"] == []
    assert eff.origins["xkey_verify_cmd"] == "default"
    assert eff.values["xkey_verify_cwd"] == ""
    assert eff.origins["xkey_verify_cwd"] == "default"
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
    machine = _machine_file(tmp_path, {"xkey_verify_cmd": ["m"]})
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
    assert eff.values["xkey_verify_timeout_s"] == 1800  # not machine-overridable
    assert any("xkey_verify_cmds" in d for d in eff.diagnostics)
    assert any("xkey_verify_timeout_s" in d for d in eff.diagnostics)
    _verify("fail-soft diagnostics", tick_status=status, machine_command_visible="true")


# ── consolidated acceptance signal for the T-02b report ─────────────────────

def test_verify_summary(tmp_path: pathlib.Path) -> None:
    """Emit the consolidated [VERIFY] line for the T-02b report.

    Re-asserts the four required signals in one place so the evidence line is
    traceable: the 8-case truth table, the materialization regression, the
    out-of-domain warnings, and the fail-soft + zero-footprint invariants.
    """
    # Materialized project (all 13 keys, empty effective values) + machine layer
    # that also carries two out-of-domain keys.
    project = tmp_path / "proj"
    _project_file(project, dict(cfg.DEFAULT_CONFIG))
    machine = _machine_file(
        tmp_path,
        {
            "xkey_verify_cmd": ["m"],
            "xkey_verify_cwd": "partition",
            "xkey_repair": True,
            "xkey_verify_timeout_s": 600,
        },
    )
    with _env(MW_AUTOPILOT_FILE=str(machine)):
        eff = ec.load_effective(project)
    assert eff.origins["xkey_verify_cmd"] == "machine"
    assert eff.origins["xkey_verify_cwd"] == "machine"
    assert len(eff.diagnostics) == 2  # xkey_repair + xkey_verify_timeout_s

    # Fail-soft: a bad machine field is dropped, the resolver does not raise,
    # and the read path leaves no footprint.
    bare = tmp_path / "bare"
    bad_dir = tmp_path / "bad"
    bad_dir.mkdir()
    bad = _machine_file(bad_dir, {"xkey_verify_cwd": 7})
    with _env(MW_AUTOPILOT_FILE=str(bad)):
        eff_bad = ec.load_effective(bare)
    assert eff_bad.values["xkey_verify_cwd"] == ""
    assert len(eff_bad.diagnostics) == 1
    assert not (bare / ".mw").exists()
    assert not (bare / ".agenticdoc").exists()

    _verify(
        "验收汇总",
        **{
            "空值即未决定 真值表": "8 例全绿",
            "材料化场景仍取机器层": "true",
            "越域越界告警": len(eff.diagnostics),
            "fail-soft 与零足迹未回退": "true",
        },
    )
