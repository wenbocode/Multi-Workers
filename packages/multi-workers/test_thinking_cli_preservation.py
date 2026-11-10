"""PM regressions for independent review: alias preservation and null refusal."""
from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest
import yaml

PACKAGE = pathlib.Path(__file__).parent
sys.path.insert(0, str(PACKAGE))

from worker_thinking import resolve_worker_thinking


def _cli(project: pathlib.Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(PACKAGE / "mw.py"), "thinking", *arguments, "--project", str(project)],
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )


@pytest.mark.parametrize("target", ["default", "coding"])
@pytest.mark.parametrize("action", ["set", "clear"])
def test_mutation_detaches_alias_shared_with_other_top_level_fields(
    tmp_path: pathlib.Path, action: str, target: str,
) -> None:
    text = (
        "metadata: &shared {default: high}\nthinking: *shared\n"
        if target == "default" else
        "metadata: &shared {coding: high}\nthinking: {roles: *shared}\n"
    )
    config = tmp_path / ".mw/dispatch.yml"
    config.parent.mkdir()
    config.write_text(text, encoding="utf-8")
    original = yaml.safe_load(text)
    args = [action, target, "low"] if action == "set" else [action, target]
    result = _cli(tmp_path, *args)
    assert result.returncode == 0, result.stderr
    written = yaml.safe_load(config.read_text(encoding="utf-8"))
    assert written["metadata"] == original["metadata"]
    expected = ("low", "config:default" if target == "default" else "config:coding", None)
    assert resolve_worker_thinking(tmp_path, "coding") == (expected if action == "set" else (None, "unset", None))


@pytest.mark.parametrize("text", ["null\n", "~\n", "---\nnull\n", "\ufeffnull # explicit value\n"])
@pytest.mark.parametrize("args", [("show",), ("set", "default", "high"), ("clear", "all")])
def test_explicit_null_root_is_rejected_without_writes(
    tmp_path: pathlib.Path, text: str, args: tuple[str, ...],
) -> None:
    config = tmp_path / ".mw/dispatch.yml"
    config.parent.mkdir()
    config.write_text(text, encoding="utf-8")
    before = config.read_bytes()
    stamp = config.stat().st_mtime_ns
    result = _cli(tmp_path, *args)
    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    assert config.read_bytes() == before
    assert config.stat().st_mtime_ns == stamp
    assert sorted(p.name for p in config.parent.iterdir()) == ["dispatch.yml"]


@pytest.mark.parametrize("text", ["", "# comment only\n", "\ufeff# BOM comment\n", "---\n# empty document\n"])
def test_truly_empty_documents_remain_writable(tmp_path: pathlib.Path, text: str) -> None:
    config = tmp_path / ".mw/dispatch.yml"
    config.parent.mkdir()
    config.write_text(text, encoding="utf-8")
    result = _cli(tmp_path, "set", "default", "off")
    assert result.returncode == 0, result.stderr
    assert yaml.safe_load(config.read_text(encoding="utf-8"))["thinking"]["default"] == "off"
    assert resolve_worker_thinking(tmp_path, "coding") == ("off", "config:default", None)
