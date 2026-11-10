"""Separated dual/partition roots through real dispatch and conductor parsing."""
import json
import os
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import mw_common
from autopilot import conductor, dispatch, write_face

KEY = "rooted-face"


def junction(link: pathlib.Path, target: pathlib.Path) -> None:
    if os.name == "nt":
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
        assert result.returncode == 0, result.stderr
    else:
        link.symlink_to(target, target_is_directory=True)


def card(control: pathlib.Path, name: str, entries: list[str]) -> None:
    cards = control / ".agenticdoc" / KEY / "tasks"
    cards.mkdir(parents=True, exist_ok=True)
    (cards / (name + ".md")).write_text(
        "type: coding\n\n## 上下文\nContext.\n\n## 要求\nWork.\n\n## 交付格式\nReport.\n\n## 写入允许面\n"
        + "\n".join("- `" + entry + "`" for entry in entries) + "\n", encoding="utf-8")


@pytest.mark.parametrize("mode", ["dual", "partition"])
def test_separated_dispatch_identity_and_rejection(tmp_path, monkeypatch, mode):
    for key in ("MW_TARGET_GAME", "MW_TARGET_ENGINE", "MW_PARTITION_PARENT", "MW_PARTITION_ROOT"):
        monkeypatch.delenv(key, raising=False)
    control, target, extra, named = [tmp_path / name for name in ("control", "target", "extra", "sdk")]
    for root in (control, target, extra, named):
        root.mkdir()
    (control / ".agenticdoc").mkdir()
    config = (dict(mode="dual", game=str(target), engine=str(extra)) if mode == "dual" else
              dict(active="partition", partition=dict(parent=str(extra), partition=str(target), roots=dict(sdk=str(named)))))
    (control / ".agenticdoc" / "target.yml").write_text(json.dumps(config), encoding="utf-8")

    def send(name, entries):
        card(control, name, entries)
        return dispatch.dispatch(control, KEY, name, "phase-writer", "Work.", loop="rooted-test", attempt=1)

    file = str(target / "src" / "a.cpp")
    first = send("one", [file])
    assert first.ok and first.row_verified, first.reason
    queue = mw_common.workers_path(control)
    original = queue.read_bytes()
    for name, entries, code in (
        ("same", [file.replace("\\", "/")], "write-face-overlap"),
        ("outside", [str(tmp_path / "outside.cpp")], "write-face-outside-base"),
        ("escape", [str(target) + "/../outside.cpp"], "write-face-escape"),
    ):
        result = send(name, entries)
        assert not result.ok and result.reason.startswith(code), result.reason
        assert queue.read_bytes() == original
        assert not (control / ".agenticdoc" / KEY / "workers" / dispatch.task_key_for(KEY, name)).exists()
    assert send("control", ["src/a.cpp"]).ok
    assert send("extra", [str(extra / "src" / "a.cpp")]).ok
    if mode == "partition":
        assert send("named", [str(named / "sdk.h")]).ok
    parsed = conductor._declared_write_face(control, KEY, "one")
    assert isinstance(parsed, write_face.WriteFace)
    assert parsed.allow_entries == (file.replace("\\", "/"),)
    alias = control / "alias"
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    junction(alias, target)
    junction(control / "foreign", foreign)
    try:
        result = send("alias", [str(alias / "src" / "a.cpp")])
        assert not result.ok and result.reason.startswith("write-face-overlap"), result.reason
        result = send("foreign", [str(control / "foreign" / "outside.cpp")])
        assert not result.ok and result.reason.startswith("write-face-outside-base"), result.reason
        alias_face = conductor._declared_write_face(control, KEY, "alias")
        assert isinstance(alias_face, write_face.WriteFace)
        assert alias_face.allow_entries == parsed.allow_entries
    finally:
        for link in (alias, control / "foreign"):
            if os.name == "nt":
                link.rmdir()
            else:
                link.unlink()
    print(f"[VERIFY] VC-001/002/005 {mode}: real dispatch and conductor agree; rejects have zero queue/task effects")
