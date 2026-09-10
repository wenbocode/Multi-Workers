"""autopilot/advance.py — subprocess wrapper around the framework's
advance_phase.py (AC-005/D-107: the only phase-advance channel).

Framework location reuses the existing detection protocol instead of
hardcoding paths:

1. bootstrap pointer: the project's ``.agentic-framework`` marker (written by
   ``mw init``) names the framework repo via its ``repo=`` line; the standard
   install layout ``<project>/.agents/skills/agentic-task`` is the fallback
2. authority: run that framework's ``scripts/detect_root.py --json`` with
   cwd = project root and use its ``PLATFORM_DIR`` output — the path the
   canonical detector reports, never one derived here

A missing framework (no marker, no skill dir, no scripts) raises
:class:`AdvanceError`; the conductor startup path turns that into a refusal
to start. ``advance()`` itself returns ``(1, "", reason)`` for a missing
framework so callers can treat it like any failed advance without
special-casing exceptions mid-loop.

The wrapper spawns and reports only — no business semantics; those stay in
the framework script. argv is always list-form (never ``shell=True``).
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys


class AdvanceError(Exception):
    """Framework scripts unavailable or detection failed."""


_ADVANCE_TIMEOUT_SEC = 120
_SCRIPTS = pathlib.Path("scripts")
# project root (resolved) -> advance_phase.py path. Only successes are cached;
# a deleted script is re-detected on the next call.
_script_cache: dict[str, pathlib.Path] = {}


def _marker_repo(project_root: pathlib.Path) -> pathlib.Path | None:
    """Framework repo path from the ``.agentic-framework`` marker, if valid."""
    marker = pathlib.Path(project_root) / ".agentic-framework"
    if not marker.is_file():
        return None
    try:
        lines = marker.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        if line.startswith("repo="):
            candidate = pathlib.Path(line[len("repo="):].strip())
            if candidate.is_dir():
                return candidate
    return None


def locate_platform_dir(project_root: pathlib.Path) -> pathlib.Path:
    """Framework platform dir (contains scripts/advance_phase.py).

    Raises AdvanceError when the framework is not installed for this project."""
    project_root = pathlib.Path(project_root)
    candidates: list[pathlib.Path] = []
    marker = _marker_repo(project_root)
    if marker is not None:
        candidates.append(marker)
    candidates.append(project_root / ".agents" / "skills" / "agentic-task")
    detect: pathlib.Path | None = None
    for candidate in candidates:
        script = candidate / _SCRIPTS / "detect_root.py"
        if script.is_file():
            detect = script
            break
    if detect is None:
        raise AdvanceError(
            "AgenticTask framework not installed: no scripts/detect_root.py under "
            "the .agentic-framework repo path or .agents/skills/agentic-task "
            f"(project root: {project_root}). Run 'mw init' first."
        )
    try:
        proc = subprocess.run(
            [sys.executable, str(detect), "--json"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AdvanceError(f"detect_root.py could not run: {exc}") from exc
    if proc.returncode != 0:
        raise AdvanceError(
            f"detect_root.py failed (exit {proc.returncode}): {(proc.stderr or '').strip()}"
        )
    try:
        platform_dir = pathlib.Path(json.loads(proc.stdout)["PLATFORM_DIR"])
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise AdvanceError(f"detect_root.py output not parseable: {exc}") from exc
    if not (platform_dir / _SCRIPTS / "advance_phase.py").is_file():
        raise AdvanceError(f"advance_phase.py not found under platform dir {platform_dir}")
    return platform_dir


def advance_script(project_root: pathlib.Path) -> pathlib.Path:
    """Cached advance_phase.py path (the framework does not move mid-run)."""
    key = str(pathlib.Path(project_root).resolve())
    script = _script_cache.get(key)
    if script is None or not script.is_file():
        script = locate_platform_dir(project_root) / _SCRIPTS / "advance_phase.py"
        _script_cache[key] = script
    return script


def invalidate_script_cache() -> None:
    """Forget cached framework locations (tests and manual refresh)."""
    _script_cache.clear()


def advance(
    key: str,
    phase: str,
    project_root: pathlib.Path,
    summary: str | None = None,
) -> tuple[int, str, str]:
    """Run ``advance_phase.py <key> <phase>`` in a subprocess; return
    ``(exit_code, stdout, stderr)``. Missing framework -> ``(1, "", reason)``.
    Exit codes pass through untouched — interpretation is the caller's."""
    try:
        script = advance_script(project_root)
    except AdvanceError as exc:
        return 1, "", f"[advance] {exc}"
    cmd = [sys.executable, str(script), key, phase]
    if summary is not None:
        cmd += ["--summary", summary]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(pathlib.Path(project_root)),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_ADVANCE_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return 124, "", f"[advance] advance_phase.py timed out after {_ADVANCE_TIMEOUT_SEC}s"
    return proc.returncode, proc.stdout, proc.stderr
