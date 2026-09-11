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
