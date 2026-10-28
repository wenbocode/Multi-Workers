"""
test_toolchain_cli.py — mw ue-toolchain (dual-mode toolchain discipline).

Covers the pure helpers (EOL-normalized hashing, UE target discovery, build
error-signature scan) and the cmd_toolchain run/targets/hash actions against
fabricated control/game roots — no real UE toolchain, everything hermetic
(python/cmd built-ins as the "toolchain" commands).
"""
import argparse
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw
import mw_common


# ── pure helpers ─────────────────────────────────────────────────────────────

class TestHelpers:
    def test_sha256_eol_normalized_crlf_lf_equivalent(self, tmp_path: pathlib.Path) -> None:
        crlf = tmp_path / "crlf.txt"
        crlf.write_bytes(b"x\r\ny\r\nz\r\n")
        lf = tmp_path / "lf.txt"
        lf.write_bytes(b"x\ny\nz\n")
        other = tmp_path / "other.txt"
        other.write_bytes(b"x\ny\nw\n")
        assert mw_common.sha256_eol_normalized(crlf) == mw_common.sha256_eol_normalized(lf)
        assert mw_common.sha256_eol_normalized(crlf) != mw_common.sha256_eol_normalized(other)

    def test_discover_build_targets(self, tmp_path: pathlib.Path) -> None:
        src = tmp_path / "game" / "Source"
        src.mkdir(parents=True)
        (src / "Proj.Target.cs").write_text("// game target", encoding="utf-8")
        (src / "ProjEditor.Target.cs").write_text("// editor target", encoding="utf-8")
        got = mw_common.discover_build_targets(tmp_path / "game")
        assert [t["name"] for t in got] == ["Proj", "ProjEditor"]
        assert {t["name"]: t["kind"] for t in got} == {"Proj": "game", "ProjEditor": "editor"}
        # no Source dir (non-UE root / missing root) → empty, no exception
        assert mw_common.discover_build_targets(tmp_path / "nogame") == []

    def test_scan_build_error_lines(self) -> None:
        text = "\n".join([
            "a.cpp(12): error C2039: 'x': is not a member of 'y'",
            "fatal error C1083: Cannot open include file",
            "Proj.cpp: LNK2001: unresolved external symbol",
            "UBT: error : Could not find definition for module 'INTLCore'",
            "Remote execution failed; Force local retry",
            "[1396/5493] Compiling foo.cpp",
            "LogAssetImportGate: [VERIFY] VC-024: gate_action=allow_all",
        ])
        got = mw_common.scan_build_error_lines(text)
        assert len(got) == 4  # both error C forms + LNK + UBT 'error :'
        joined = "\n".join(got)
        assert "Force local retry" not in joined
        assert "VC-024" not in joined


# ── cmd_toolchain ────────────────────────────────────────────────────────────

def _make_project(tmp_path: pathlib.Path, command: str) -> pathlib.Path:
    """Control root with a dual target.yml exposing one `ping` command.
    YAML single-quoted style with '' escaping (same recipe as _yml_scalar)."""
    control = tmp_path / "control"
    (control / ".agenticdoc").mkdir(parents=True)
    game = tmp_path / "game"
    game.mkdir()
    (control / ".agenticdoc" / "target.yml").write_text(
        "mode: dual\ngame: '" + str(game).replace("'", "''") + "'\n"
        "toolchain:\n  ping: '" + command.replace("'", "''") + "'\n",
        encoding="utf-8",
    )
    return control


def _run_args(control: pathlib.Path, **kw) -> argparse.Namespace:
    base = {
        "toolchain_action": "run", "project": str(control), "name": "ping",
        "out": None, "watch": None, "json": False, "args": None,
    }
    base.update(kw)
    return argparse.Namespace(**base)


def _only_run_dir(control: pathlib.Path) -> pathlib.Path:
    runs = control / ".mw" / "toolchain-runs"
    dirs = [d for d in runs.iterdir() if d.is_dir()]
    assert len(dirs) == 1
    return dirs[0]


class TestToolchainRun:
    def test_ok_run_artifacts_and_verdict(self, tmp_path: pathlib.Path) -> None:
        control = _make_project(tmp_path, "python -c \"print('toolchain-ok')\"")
        watched = tmp_path / "w.txt"
        watched.write_bytes(b"v1\r\n")
        rc = mw.cmd_toolchain(_run_args(control, watch=[str(watched)]))
        assert rc == 0
        run_dir = _only_run_dir(control)
        assert (run_dir / "cmd.txt").read_text(encoding="utf-8").startswith("python -c")
        log = (run_dir / "run.log").read_text(encoding="utf-8")
        assert "toolchain-ok" in log
        assert (run_dir / "exit.txt").read_text(encoding="utf-8").strip() == "0"
        assert (run_dir / "errors.txt").read_text(encoding="utf-8") == ""
        meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
        assert meta["exit_code"] == 0
        assert meta["error_line_count"] == 0
        assert meta["watched_drift_count"] == 0
        assert meta["watched"][0]["drift"] is False
        assert meta["ok"] is True
        assert meta["watched"][0]["before"] == meta["watched"][0]["after"]

    def test_error_signature_and_bad_exit_fail(self, tmp_path: pathlib.Path) -> None:
        control = _make_project(
            tmp_path,
            "python -c \"import sys; print('x.cpp(1): error C2039: boom'); sys.exit(2)\"",
        )
        rc = mw.cmd_toolchain(_run_args(control))
        assert rc == 1
        run_dir = _only_run_dir(control)
        errors = (run_dir / "errors.txt").read_text(encoding="utf-8")
        assert "error C2039" in errors
        meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
        assert meta["exit_code"] == 2
        assert meta["error_line_count"] == 1
        assert meta["ok"] is False

    def test_watch_drift_fails_even_on_exit_zero(self, tmp_path: pathlib.Path) -> None:
        # the command appends to the watched file via the {game} placeholder —
        # exit 0 but the source drifted while the command ran
        game = tmp_path / "game"
        watched = game / "w.txt"
        control = _make_project(
            tmp_path, "python -c \"open(r'{game}\\\\w.txt','a').write('x')\""
        )
        watched.write_bytes(b"base\r\n")
        rc = mw.cmd_toolchain(_run_args(control, watch=[str(watched)]))
        assert rc == 1
        meta = json.loads((_only_run_dir(control) / "meta.json").read_text(encoding="utf-8"))
        assert meta["exit_code"] == 0
        assert meta["watched_drift_count"] == 1
        assert meta["watched"][0]["drift"] is True

    def test_extra_args_forwarded_verbatim(self, tmp_path: pathlib.Path) -> None:
        control = _make_project(tmp_path, "python -c \"import sys; print(sys.argv[1])\"")
        rc = mw.cmd_toolchain(_run_args(control, args="forwarded-arg"))
        assert rc == 0
        run_dir = _only_run_dir(control)
        cmd = (run_dir / "cmd.txt").read_text(encoding="utf-8")
        assert cmd.rstrip("\n").endswith("forwarded-arg")
        assert "forwarded-arg" in (run_dir / "run.log").read_text(encoding="utf-8")

    def test_out_override_places_run_dir(self, tmp_path: pathlib.Path) -> None:
        control = _make_project(tmp_path, "python -c \"print('ok')\"")
        out_parent = tmp_path / "evidence" / "runs"
        rc = mw.cmd_toolchain(_run_args(control, out=str(out_parent)))
        assert rc == 0
        assert not (control / ".mw" / "toolchain-runs").exists()
        dirs = [d for d in out_parent.iterdir() if d.is_dir()]
        assert len(dirs) == 1
        assert (dirs[0] / "run.log").is_file()

    def test_unknown_name_fails(self, tmp_path: pathlib.Path, capsys) -> None:
        control = _make_project(tmp_path, "python -c \"print('ok')\"")
        rc = mw.cmd_toolchain(_run_args(control, name="nope"))
        assert rc == 1
        assert "no toolchain command named 'nope'" in capsys.readouterr().err

    def test_missing_engine_placeholder_fails_closed(self, tmp_path: pathlib.Path, capsys) -> None:
        control = _make_project(tmp_path, "\"{engine}/Build.bat\" x")
        rc = mw.cmd_toolchain(_run_args(control))
        assert rc == 1
        assert "missing-field" in capsys.readouterr().err


class TestToolchainTargetsAndHash:
    def test_targets_lists_editor_and_game(self, tmp_path: pathlib.Path, capsys) -> None:
        control = _make_project(tmp_path, "python -c \"print('ok')\"")
        src = tmp_path / "game" / "Source"
        src.mkdir(parents=True)
        (src / "ProjEditor.Target.cs").write_text("// editor", encoding="utf-8")
        (src / "Proj.Target.cs").write_text("// game", encoding="utf-8")
        rc = mw.cmd_toolchain(argparse.Namespace(
            toolchain_action="targets", project=str(control)))
        assert rc == 0
        out = capsys.readouterr().out
        assert "ProjEditor (editor)" in out
        assert "Proj (game)" in out

    def test_targets_no_source_dir(self, tmp_path: pathlib.Path, capsys) -> None:
        control = _make_project(tmp_path, "python -c \"print('ok')\"")
        rc = mw.cmd_toolchain(argparse.Namespace(
            toolchain_action="targets", project=str(control)))
        assert rc == 0
        assert "no *.Target.cs" in capsys.readouterr().out

    def test_hash_prints_eol_normalized(self, tmp_path: pathlib.Path, capsys) -> None:
        crlf = tmp_path / "a.txt"
        crlf.write_bytes(b"x\r\n")
        lf = tmp_path / "b.txt"
        lf.write_bytes(b"x\n")
        rc = mw.cmd_toolchain(argparse.Namespace(
            toolchain_action="hash", files=[str(crlf), str(lf)]))
        assert rc == 0
        lines = [l for l in capsys.readouterr().out.splitlines() if l.strip()]
        assert len(lines) == 2
        assert lines[0].split()[0] == lines[1].split()[0]

    def test_hash_missing_file_fails(self, tmp_path: pathlib.Path) -> None:
        rc = mw.cmd_toolchain(argparse.Namespace(
            toolchain_action="hash", files=[str(tmp_path / "nope.txt")]))
        assert rc == 1
