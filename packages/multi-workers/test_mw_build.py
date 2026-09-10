"""
test_mw_build.py — `mw build --install` dist-sync behavior.

The npm global `pi` links to packages/coding-agent, so the runtime executes the
repo's dist. `--install` must therefore also rebuild dist (opt out: --no-dist);
a failing dist rebuild fails the whole build so the operator notices the drift.
"""
import pathlib
import sys
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw


def _args(install: bool, no_dist: bool = False) -> SimpleNamespace:
	return SimpleNamespace(install=install, no_dist=no_dist)


def _patch_build_env(tmp_path, monkeypatch, dist_result=(True, "dist rebuilt")):
	"""Point the bundle/install plumbing at a tmp dir; record dist rebuilds."""
	bundle = tmp_path / "agent-team-loop.js"
	bundle.write_text("export default function activate() {}\n", encoding="utf-8")
	monkeypatch.setattr(mw, "_build_bundle", lambda: (True, "built ok"))
	monkeypatch.setattr(mw, "_bundle_path", lambda: bundle)
	monkeypatch.setattr(mw, "_global_ext_dir", lambda: tmp_path / "ext")
	monkeypatch.setattr(mw, "_write_mw_py_path", lambda: None)
	rebuilt: list[int] = []

	def fake_rebuild():
		rebuilt.append(1)
		return dist_result

	monkeypatch.setattr(mw, "_rebuild_pi_dist", fake_rebuild)
	return rebuilt


def test_install_rebuilds_dist(tmp_path, monkeypatch, capsys):
	rebuilt = _patch_build_env(tmp_path, monkeypatch)
	assert mw.cmd_build(_args(install=True)) == 0
	assert rebuilt == [1]
	out = capsys.readouterr().out
	assert "dist rebuilt" in out
	assert (tmp_path / "ext" / "agent-team-loop.js").exists()


def test_install_dist_failure_fails_the_build(tmp_path, monkeypatch, capsys):
	_patch_build_env(tmp_path, monkeypatch, dist_result=(False, "boom: tsgo failed"))
	assert mw.cmd_build(_args(install=True)) == 1
	assert "boom: tsgo failed" in capsys.readouterr().err


def test_no_dist_skips_rebuild(tmp_path, monkeypatch, capsys):
	rebuilt = _patch_build_env(tmp_path, monkeypatch)
	assert mw.cmd_build(_args(install=True, no_dist=True)) == 0
	assert rebuilt == []
	assert "--no-dist" in capsys.readouterr().out


def test_plain_build_never_touches_dist(tmp_path, monkeypatch):
	monkeypatch.setattr(mw, "_build_bundle", lambda: (True, "built ok"))
	monkeypatch.setattr(mw, "_bundle_path", lambda: tmp_path / "b.js")

	def boom():
		raise AssertionError("dist rebuild must not run without --install")

	monkeypatch.setattr(mw, "_rebuild_pi_dist", boom)
	assert mw.cmd_build(_args(install=False)) == 0
