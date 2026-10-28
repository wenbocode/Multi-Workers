"""Tests for `mw review-split status|set` (claim-driven-review-orchestration T-02).

Contract (design 2.2 / AC-S1b):

* `status` resolves ``MW_REVIEW_SPLIT`` (env) > ``.mw/review-split.json`` >
  default ``off``, case-insensitively, reports the mode + its source + the
  config path, and is **strictly read-only** — it may not create the ``.mw/``
  directory or write any file (the ``stats --detail`` HTML trap).
* `set <mode>` writes ``{"v":1,"mode":...,"updated":...}`` atomically
  (``.tmp`` + ``os.replace``); an invalid mode is a pure exit-2 no-op.

Every fixture lives under ``tmp_path``; the CLI runs in a child process whose
environment has ``MW_REVIEW_SPLIT`` scrubbed, so neither the developer's real
``.mw/`` nor an ambient env value can leak in.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # noqa: E402

import mw  # noqa: E402

MW_PY = pathlib.Path(mw.__file__)
ENV_VAR = "MW_REVIEW_SPLIT"


def _project(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path.resolve()


def _config_path(project: pathlib.Path) -> pathlib.Path:
    return project / ".mw" / "review-split.json"


def _run(*argv: str, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    env = {name: value for name, value in os.environ.items() if name != ENV_VAR}
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(MW_PY), *argv],
        capture_output=True,
        encoding="utf-8",
        timeout=300,
        env=env,
    )


def _status(project: pathlib.Path, *extra: str, env_extra: dict[str, str] | None = None):
    return _run("review-split", "status", "--project", str(project), *extra, env_extra=env_extra)


def _write_config(project: pathlib.Path, mode: str, **extra: object) -> pathlib.Path:
    path = _config_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"v": 1, "mode": mode, "updated": "2026-10-22T00:00:00Z", **extra}
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8", newline="\n")
    return path


def _snapshot(root: pathlib.Path) -> dict[str, str]:
    """Path -> content hash for files, ``<dir>`` for directories.

    Directories are part of the snapshot on purpose: a read-only `status` must
    not even create `.mw/`. Sorted insertion keeps the dict comparable.
    """
    state: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        state[rel] = "<dir>" if path.is_dir() else hashlib.sha256(path.read_bytes()).hexdigest()
    return state


# -- 1: default -------------------------------------------------------------


def test_status_default_is_off(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    proc = _status(project)
    assert proc.returncode == 0, proc.stderr
    expected = (
        f"review-split: mode=off source=default config={_config_path(project)}"
    )
    assert proc.stdout.strip() == expected
    assert "invalid_env" not in proc.stdout
    # Bare status on an unconfigured project never materializes `.mw/`.
    assert not (project / ".mw").exists()

    proc = _status(project, "--json")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == {
        "mode": "off",
        "source": "default",
        "config_path": str(_config_path(project)),
        "invalid_env": None,
        "invalid": None,
        "wired": True,
    }


# -- 2: config --------------------------------------------------------------


def test_status_reads_config_plan(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    _write_config(project, "plan")
    proc = _status(project)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == (
        f"review-split: mode=plan source=config config={_config_path(project)}"
    )

    doc = json.loads(_status(project, "--json").stdout)
    assert doc["mode"] == "plan"
    assert doc["source"] == "config"
    assert doc["invalid_env"] is None


# -- 3: env beats config ----------------------------------------------------


def test_env_overrides_config(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    _write_config(project, "plan")
    # Upper-case proves the resolution is case-insensitive (T-01 rule 3).
    # `on` is legal but unwired, so the line says so instead of looking active.
    proc = _status(project, env_extra={ENV_VAR: "ON"})
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == (
        f"review-split: mode=on source=env config={_config_path(project)} wired=no"
    )
    doc = json.loads(_status(project, "--json", env_extra={ENV_VAR: "On"}).stdout)
    assert (doc["mode"], doc["source"], doc["invalid_env"]) == ("on", "env", None)
    assert doc["wired"] is False


# -- 4: illegal env degrades ------------------------------------------------


def test_invalid_env_degrades_and_is_reported(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    _write_config(project, "plan")
    proc = _status(project, env_extra={ENV_VAR: "sideways"})
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == (
        f"review-split: mode=plan source=config config={_config_path(project)}"
        " invalid_env=sideways"
    )
    doc = json.loads(_status(project, "--json", env_extra={ENV_VAR: "sideways"}).stdout)
    assert (doc["mode"], doc["source"], doc["invalid_env"]) == ("plan", "config", "sideways")

    # The chain keeps degrading past a bad config too: all the way to `off`.
    _config_path(project).unlink()
    proc = _status(project, env_extra={ENV_VAR: "true"})
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == (
        f"review-split: mode=off source=default config={_config_path(project)}"
        " invalid_env=true"
    )


# -- 5: set writes the versioned config -------------------------------------


def test_set_writes_atomic_versioned_config(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    proc = _run("review-split", "set", "plan", "--project", str(project))
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == f"review-split: mode=plan wrote {_config_path(project)}"

    path = _config_path(project)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["v"] == 1
    assert payload["mode"] == "plan"
    # `<iso8601 UTC>`: seconds precision, Z-suffixed.
    assert payload["updated"].endswith("Z") and len(payload["updated"]) == 20
    assert not path.with_name(path.name + ".tmp").exists()

    # The written file is what `status` then reports.
    doc = json.loads(_status(project, "--json").stdout)
    assert (doc["mode"], doc["source"]) == ("plan", "config")
    assert doc["wired"] is True


# -- 6: illegal mode = exit 2 with zero side effects ------------------------


def test_set_invalid_mode_exits_2_without_writes(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    (project / "a.txt").write_text("keep\n", encoding="utf-8")
    before = _snapshot(project)

    proc = _run("review-split", "set", "maybe", "--project", str(project))
    assert proc.returncode == 2
    assert proc.stdout == ""
    stderr_lines = [line for line in proc.stderr.splitlines() if line.strip()]
    assert len(stderr_lines) == 1, proc.stderr
    assert "invalid mode" in stderr_lines[0]

    assert _snapshot(project) == before
    assert not (project / ".mw").exists()


# -- 6b: the unwired `on` tier is refused, not silently persisted -----------


def test_set_on_is_refused_as_unwired(tmp_path: pathlib.Path) -> None:
    """`on` is legal contract-wise but has no implementation (M3 cancelled).

    Persisting it would make `status` claim a feature that does nothing, so the
    setter refuses before touching the filesystem — same zero-side-effect shape
    as an illegal value, but with a reason the operator can act on.
    """
    project = _project(tmp_path)
    (project / "a.txt").write_text("keep\n", encoding="utf-8")
    before = _snapshot(project)

    proc = _run("review-split", "set", "on", "--project", str(project))
    assert proc.returncode == 2
    assert proc.stdout == ""
    stderr_lines = [line for line in proc.stderr.splitlines() if line.strip()]
    assert len(stderr_lines) == 1, proc.stderr
    assert "not wired" in stderr_lines[0]
    assert "plan" in stderr_lines[0]

    assert _snapshot(project) == before
    assert not (project / ".mw").exists()


def test_status_flags_a_preexisting_on_config(tmp_path: pathlib.Path) -> None:
    """A config file written before the refusal existed must not look active."""
    project = _project(tmp_path)
    _write_config(project, "on")
    proc = _status(project)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == (
        f"review-split: mode=on source=config config={_config_path(project)} wired=no"
    )
    doc = json.loads(_status(project, "--json").stdout)
    assert (doc["mode"], doc["source"], doc["wired"]) == ("on", "config", False)


# -- 7: status is read-only over the whole tree -----------------------------

def test_status_leaves_project_file_hashes_unchanged(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    (project / "docs").mkdir()
    (project / "docs" / "note.md").write_text("# note\n", encoding="utf-8")
    (project / "top.txt").write_text("top\n", encoding="utf-8")
    _write_config(project, "plan")
    before = _snapshot(project)

    probes = (
        _status(project),
        _status(project, "--json"),
        _status(project, env_extra={ENV_VAR: "on"}),
        _status(project, "--json", env_extra={ENV_VAR: "not-a-mode"}),
    )
    for proc in probes:
        assert proc.returncode == 0, proc.stderr

    assert _snapshot(project) == before
    # No stray report/cache entries either (the `stats --detail` lesson).
    assert sorted(p.name for p in project.iterdir()) == [".mw", "docs", "top.txt"]
