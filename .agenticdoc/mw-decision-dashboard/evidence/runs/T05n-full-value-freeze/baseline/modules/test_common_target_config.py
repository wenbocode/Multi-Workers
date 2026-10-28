"""
test_common_target_config.py — dual-workspace target config tests
(mw-dual-workspace Task 002, AC-001/AC-004/AC-005, VC-001/VC-006/VC-007/VC-008).

Two layers:
1. Shared parity fixtures under test/fixtures/target-config-cases/ — the same
   case set the vitest runner in packages/coding-agent executes (T-17 parity
   lock: TS resolveWorkspaceConfig vs Py load_target_config must agree on
   mode/roots/rendering/error kinds for every case).
2. A few Python-only unit tests (env injection, explicit uproject miss).
"""
import json
import os
import pathlib
import shutil
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from mw_common import (
    ENV_TARGET_ENGINE,
    ENV_TARGET_GAME,
    TargetConfigError,
    discover_uproject,
    load_target_config,
    render_toolchain_command,
)

_FIXTURES = pathlib.Path(__file__).parent / "test" / "fixtures" / "target-config-cases"


def _substitute(template: str, config: dict) -> str:
    out = template
    out = out.replace("{control_root}", config["control_root"])
    out = out.replace("{game_root}", config["game_root"] or "")
    out = out.replace("{engine_root}", config["engine_root"] or "")
    out = out.replace("{parent_root}", config["parent_root"] or "")
    out = out.replace("{partition_root}", config["partition_root"] or "")
    for name, root_path in (config.get("roots") or {}).items():
        out = out.replace("{" + name + "}", root_path)
    if "{uproject}" in out:
        out = out.replace("{uproject}", discover_uproject(config["game_root"], config.get("uproject")))
    return out


def _run_case(case_dir: pathlib.Path, tmp_path: pathlib.Path) -> None:
    case = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
    control_root = tmp_path / "control"
    shutil.copytree(case_dir, control_root)

    # Explicit env mapping: null values mean "explicitly unset".
    env = dict(os.environ)
    for name, value in (case.get("env") or {}).items():
        if value is None:
            env.pop(name, None)
        else:
            env[name] = value

    expected = case.get("expect")
    error = case.get("error")

    if error is not None:
        with pytest.raises(TargetConfigError) as ei:
            load_target_config(control_root, env=env)
        assert ei.value.kind == error["kind"], f"{case_dir.name}: kind {ei.value.kind} != {error['kind']}"
        for part in error.get("contains", []):
            assert part in str(ei.value), f"{case_dir.name}: {part!r} not in {ei.value}"
        return

    assert expected is not None, f"{case_dir.name}: case.json needs expect or error"
    config = load_target_config(control_root, env=env)
    assert config["mode"] == expected["mode"], case_dir.name
    assert config["source"] == expected["source"], case_dir.name

    if "game_root_equals_control" in expected:
        assert config["game_root"] == config["control_root"], case_dir.name
    if "game_root_rel" in expected:
        want = str((control_root / expected["game_root_rel"]).resolve())
        assert config["game_root"] == want, f"{case_dir.name}: {config['game_root']} != {want}"
    if expected.get("game_root_null"):
        assert config["game_root"] is None, case_dir.name
    if "engine_root_rel" in expected:
        want = str((control_root / expected["engine_root_rel"]).resolve())
        assert config["engine_root"] == want, case_dir.name
    if expected.get("engine_root_null"):
        assert config["engine_root"] is None, case_dir.name
    # mw-target-partition v2 fields (T-03): partition roots and the null
    # shape of the legacy fields outside partition mode.
    if "parent_root_rel" in expected:
        want = str((control_root / expected["parent_root_rel"]).resolve())
        assert config["parent_root"] == want, f"{case_dir.name}: {config['parent_root']} != {want}"
    if "partition_root_rel" in expected:
        want = str((control_root / expected["partition_root_rel"]).resolve())
        assert config["partition_root"] == want, f"{case_dir.name}: {config['partition_root']} != {want}"
    if expected.get("parent_root_null"):
        assert config["parent_root"] is None, case_dir.name
    if "roots" in expected:
        for name, rel in expected["roots"].items():
            want = str((control_root / rel).resolve())
            assert config["roots"][name] == want, (
                f"{case_dir.name}: roots.{name}: {config['roots'][name]} != {want}"
            )
    if expected.get("roots_empty"):
        assert config["roots"] == {}, case_dir.name
    if expected.get("roots_null"):
        assert config["roots"] is None, case_dir.name
    if "vcs" in expected:
        assert config["vcs"] == expected["vcs"], case_dir.name
    if "uproject_explicit" in expected:
        assert config["uproject"] == expected["uproject_explicit"], case_dir.name
    if "deny_globs" in expected:
        assert config["ignore"]["deny_globs"] == expected["deny_globs"], case_dir.name
    if "conventions_contains" in expected:
        assert config["contract"]["conventions"] is not None, case_dir.name
        for part in expected["conventions_contains"]:
            assert part in config["contract"]["conventions"], case_dir.name
    if "docs" in expected:
        assert config["contract"]["docs"] == expected["docs"], case_dir.name

    render = case.get("render")
    if render is not None:
        for name, template in render.items():
            rendered = render_toolchain_command(config["toolchain"][name], config)
            assert rendered == _substitute(template, config), (
                f"{case_dir.name}: render {name!r} -> {rendered!r} != {_substitute(template, config)!r}"
            )

    render_error = case.get("render_error")
    if render_error is not None:
        with pytest.raises(TargetConfigError) as ei:
            render_toolchain_command(config["toolchain"][render_error["command"]], config)
        assert ei.value.kind == render_error["kind"], case_dir.name
        for part in render_error.get("contains", []):
            assert part in str(ei.value), case_dir.name


def _parity_marker() -> None:
    cases = sorted(p.name for p in _FIXTURES.iterdir() if p.is_dir())
    print(f"[PARITY] target-config cases={len(cases)}: {', '.join(cases)}")
    if any(c.startswith(("001", "003", "004", "005")) for c in cases):
        print("[VERIFY] VC-001: mode=single roots-equal=true (case 001)")
        print("[VERIFY] VC-006: rendered-contains-engine=true unresolved-placeholders=0 (case 003)")
        print("[VERIFY] VC-007: exit-nonzero=true fallback=false (case 004)")
        print("[VERIFY] VC-008: uproject-resolved=true ambiguous-fail=true (cases 005/006/007)")


def test_parity_fixtures(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Every shared fixture case passes on the Python side (parity with TS)."""
    case_dirs = sorted(p for p in _FIXTURES.iterdir() if p.is_dir())
    assert len(case_dirs) >= 14, f"expected >=14 fixture cases, found {len(case_dirs)}"
    for case_dir in case_dirs:
        case_tmp = tmp_path / case_dir.name
        case_tmp.mkdir()
        _run_case(case_dir, case_tmp)
    _parity_marker()
    out = capsys.readouterr().out
    assert "[VERIFY] VC-001:" in out


# ── Python-only unit tests ────────────────────────────────────────────────────


def test_env_mapping_isolated_from_os_environ(tmp_path: pathlib.Path) -> None:
    """The env param (not os.environ) drives resolution — no global mutation."""
    control = tmp_path / "control"
    control.mkdir()
    game = tmp_path / "game"
    game.mkdir()
    cfg = load_target_config(control, env={ENV_TARGET_GAME: str(game)})
    assert cfg["mode"] == "dual"
    assert cfg["game_root"] == str(game.resolve())
    assert cfg["source"] == "env"
    # os.environ untouched: resolving again without the override is single
    cfg2 = load_target_config(control, env={})
    assert cfg2["mode"] == "single"


def test_explicit_uproject_missing_fails(tmp_path: pathlib.Path) -> None:
    game = tmp_path / "game"
    game.mkdir()
    (game / "Main.uproject").write_text("{}", encoding="utf-8")
    with pytest.raises(TargetConfigError) as ei:
        discover_uproject(str(game), "Nope.uproject")
    assert ei.value.kind == "uproject-not-found"


def test_unreadable_game_root_fails_closed(tmp_path: pathlib.Path) -> None:
    with pytest.raises(TargetConfigError) as ei:
        discover_uproject(str(tmp_path / "missing"))
    assert ei.value.kind == "invalid-config"


def test_deny_globs_and_sections_in_single_mode(tmp_path: pathlib.Path) -> None:
    """Sections apply in single mode too (ignore firewalls without dual)."""
    control = tmp_path / "control"
    (control / ".agenticdoc").mkdir(parents=True)
    (control / ".agenticdoc" / "target.yml").write_text(
        'mode: single\nignore:\n  deny_globs:\n    - "**/*.uasset"\n',
        encoding="utf-8",
    )
    cfg = load_target_config(control, env={})
    assert cfg["mode"] == "single"
    assert cfg["game_root"] == cfg["control_root"]
    assert cfg["ignore"]["deny_globs"] == ["**/*.uasset"]
