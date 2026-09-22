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
# Force UTF-8 stdio in the child interpreter: the framework prints Chinese gate
# diagnostics, and a Windows console default (cp936) decoded as UTF-8 turns the
# whole failure report into '?'.
_PYTHON_FLAGS = ("-X", "utf8")
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


def _candidates(project_root: pathlib.Path) -> list[pathlib.Path]:
    """Framework platform-dir candidates, in probe order, de-duplicated."""
    marker = _marker_repo(project_root)
    raw = [marker, pathlib.Path(project_root) / ".agents" / "skills" / "agentic-task"]
    out: list[pathlib.Path] = []
    seen: list[pathlib.Path] = []
    for candidate in raw:
        if candidate is None:
            continue
        resolved = pathlib.Path(candidate).resolve()
        if resolved in seen:
            continue
        seen.append(resolved)
        out.append(pathlib.Path(candidate))
    return out


def _probe_detect_root(
    candidate: pathlib.Path, project_root: pathlib.Path
) -> tuple[pathlib.Path | None, str]:
    """Run one candidate's ``detect_root.py --json`` (cwd = project root).

    Returns ``(platform_dir, "")`` when the candidate reports this project as
    its root, else ``(None, reason)`` for the fail-loud report."""
    detect = candidate / _SCRIPTS / "detect_root.py"
    if not detect.is_file():
        return None, f"{candidate}: no scripts/detect_root.py"
    try:
        proc = subprocess.run(
            [sys.executable, *_PYTHON_FLAGS, str(detect), "--json"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"{candidate}: detect_root.py could not run ({exc})"
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip()
        return None, f"{candidate}: detect_root.py failed (exit {proc.returncode}) {tail}"
    try:
        info = json.loads(proc.stdout)
        platform_dir = pathlib.Path(info["PLATFORM_DIR"])
        reported = pathlib.Path(info["PROJECT_ROOT"])
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        return None, f"{candidate}: detect_root.py output not parseable ({exc})"
    if reported.resolve() != pathlib.Path(project_root).resolve():
        return None, f"{candidate}: PROJECT_ROOT={reported} does not match {project_root}"
    if not (platform_dir / _SCRIPTS / "advance_phase.py").is_file():
        return None, f"{candidate}: {platform_dir} has no scripts/advance_phase.py"
    return platform_dir, ""


def locate_platform_dir(project_root: pathlib.Path) -> pathlib.Path:
    """Framework platform dir (contains scripts/advance_phase.py).

    A candidate is adopted only when its ``detect_root.py --json`` reports
    ``PROJECT_ROOT`` equal to *project_root*. The marker repo may legitimately
    live outside the project, but a framework whose own root resolution points
    at a *different* AgenticTask project must never be used: phase gates would
    silently write key state into the wrong repository (the autopilot
    phase-advance blocker, 2026-09-22).

    Raises AdvanceError when no candidate is consistent."""
    project_root = pathlib.Path(project_root)
    candidates = _candidates(project_root)
    if not any((c / _SCRIPTS / "detect_root.py").is_file() for c in candidates):
        raise AdvanceError(
            "AgenticTask framework not installed: no scripts/detect_root.py under "
            "the .agentic-framework repo path or .agents/skills/agentic-task "
            f"(project root: {project_root}). Run 'mw init' first."
        )
    problems: list[str] = []
    for candidate in candidates:
        platform_dir, problem = _probe_detect_root(candidate, project_root)
        if platform_dir is not None:
            return platform_dir
        problems.append(problem)
    raise AdvanceError(
        "no framework candidate resolves to this project's root:\n  " + "\n  ".join(problems)
    )


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
    cmd = [sys.executable, *_PYTHON_FLAGS, str(script), key, phase]
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
