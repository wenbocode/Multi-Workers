"""
test_serve_meta.py — `.mw/serve.meta` stamp (stale-serve fix).

mw serve writes pid + started_at_ms at startup; the agent-team-loop extension
compares started_at_ms against the mw source tree's newest mtime to detect
serves that predate the current code (they silently miss features — e.g. the
conductor supervision — and /autopilot enable would promise a conductor that
never spawns). The stamp is removed on serve exit alongside the PID file.
"""
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw
import mw_common


def test_write_serve_meta_shape(tmp_path):
    mw._write_serve_meta(tmp_path)
    p = tmp_path / ".mw" / "serve.meta"
    assert p.is_file()
    meta = json.loads(p.read_text(encoding="utf-8"))
    assert meta["pid"] == mw.os.getpid()
    # started_at_ms: epoch ms, within 5s of now
    assert isinstance(meta["started_at_ms"], int)
    assert abs(meta["started_at_ms"] - int(time.time() * 1000)) < 5000
    assert meta["code_dir"] == str(mw._SCRIPT_DIR)


def test_remove_serve_meta_tolerates_absence(tmp_path):
    # No .mw dir at all — must not raise.
    mw._remove_serve_meta(tmp_path)
    mw._write_serve_meta(tmp_path)
    mw._remove_serve_meta(tmp_path)
    assert not (tmp_path / ".mw" / "serve.meta").exists()


def test_serve_meta_path_layout(tmp_path):
    assert mw._serve_meta_path(tmp_path) == tmp_path / ".mw" / "serve.meta"


# ── Dual-workspace root binding (mw-dual-workspace Task 010, AC-009/VC-015) ───

def test_serve_paths_anchor_control_root_in_dual_mode(tmp_path, monkeypatch):
    """VC-015: with a dual target.yml (game root elsewhere), every serve-side
    path — PID file, serve.meta, stop request, queue/lock — anchors the
    CONTROL workspace, never the game tree. Serve paths derive from
    --project (control root); dual mode only moves the WORKER cwd, so this
    locks the invariant against future drift (expected zero code change)."""
    monkeypatch.delenv("MW_TARGET_GAME", raising=False)
    monkeypatch.delenv("MW_TARGET_ENGINE", raising=False)
    game = tmp_path / "game"
    game.mkdir()
    agentic = tmp_path / ".agenticdoc"
    agentic.mkdir()
    (agentic / "target.yml").write_text(f"mode: dual\ngame: '{game}'\n", encoding="utf-8")

    assert mw._pid_path(tmp_path) == tmp_path / ".mw" / "mw.pid"
    assert mw._serve_meta_path(tmp_path) == tmp_path / ".mw" / "serve.meta"
    assert mw._stop_request_path(tmp_path) == tmp_path / ".mw" / "mw.stop"
    assert mw_common.workers_path(tmp_path) == tmp_path / ".agenticdoc" / "_workers.parallel"
    assert mw_common.lock_path(tmp_path) == tmp_path / ".mw" / "workers.lock"
    # None of them may drift into the game tree.
    for p in (
        mw._pid_path(tmp_path),
        mw._serve_meta_path(tmp_path),
        mw._stop_request_path(tmp_path),
        mw_common.workers_path(tmp_path),
    ):
        assert not str(p).startswith(str(game))

    mw._write_serve_meta(tmp_path)
    meta = json.loads((tmp_path / ".mw" / "serve.meta").read_text(encoding="utf-8"))
    # code_dir points at the control-side mw source, not the game tree.
    assert meta["code_dir"] == str(mw._SCRIPT_DIR)
    assert not meta["code_dir"].startswith(str(game))
    # The game tree received nothing.
    assert list(game.iterdir()) == []
    print("[VERIFY] VC-015: serve-meta-prefix=control-mw")
