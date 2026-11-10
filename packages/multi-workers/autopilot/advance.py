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
import os
import pathlib
import shlex
import subprocess
import sys
from datetime import datetime, timezone

import decision_policy


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


# ── H09 phase hard-failure recovery (T26) ──────────────────────────────────
#
# AC-009: a failed phase gate is disposed of by the automatic-decision path
# first; the phase may only advance again after that disposition and a real
# re-verification. The append-only ledger below keeps the original failure
# (rc/stdout/stderr verbatim) so "disposed of" can never mean "erased".

FAILURES_REL = pathlib.Path(".agenticdoc/_autopilot/advance-failures")
POLICY_REL = pathlib.Path(".agenticdoc/_autopilot/decision-policy.json")
#: The production decision ledger records the real dp-auto request a phase
#: failure disposition must cite. The file is read, never written, here.
LIFECYCLE_REL = pathlib.Path(".agenticdoc/_autopilot/decision-lifecycle.jsonl")
DISPOSITION_ACTIONS = frozenset(
    {"retry", "narrow", "split", "direct-exec", "escalate"}
)
#: A disposition that itself claims work was narrowed/split still needs the
#: bounded re-verification below; only these actions may ever release an edge.
RELEASABLE_ACTIONS = frozenset({"retry", "narrow", "split", "direct-exec"})


def _ledger_path(project_root: pathlib.Path, key: str) -> pathlib.Path:
    """One append-only ledger per key (never rewritten, never truncated)."""
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in str(key))
    return pathlib.Path(project_root) / FAILURES_REL / f"{safe or 'unknown'}.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def recovery_enforced(project_root: pathlib.Path) -> bool:
    """True only when the project's current policy carries a usable recovery rule.

    The enablement is the EXISTING approved policy surface
    (``recovery{allowed_origins,scope,authority_ref,observation_conditions,
    stop_conditions}``); no frozen config key and no extra policy field is
    invented for this consumer. A missing or invalid policy keeps the old
    advance behaviour byte-for-byte (default off).
    """
    try:
        loaded = decision_policy.load_policy(pathlib.Path(project_root))
    except Exception:  # noqa: BLE001 - an unreadable policy is not an opt-in
        return False
    return bool(loaded.usable and loaded.policy is not None
                and loaded.policy.recovery is not None)


def _rows(project_root: pathlib.Path, key: str) -> list[dict]:
    path = _ledger_path(project_root, key)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    rows: list[dict] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            # A corrupt row is recorded as an unreadable fact, never skipped as
            # "nothing happened" by the caller's release decision.
            rows.append({"kind": "corrupt"})
            continue
        rows.append(row if isinstance(row, dict) else {"kind": "corrupt"})
    return rows


def _append(project_root: pathlib.Path, key: str, payload: dict) -> dict:
    path = _ledger_path(project_root, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = _rows(project_root, key)
    record = {
        **payload,
        "seq": len(rows) + 1,
        "recorded_at": _now_iso(),
    }
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return record


def record_failure(
    project_root: pathlib.Path,
    key: str,
    phase: str,
    code: int,
    stdout: str,
    stderr: str,
) -> dict | None:
    """Persist one failed advance verbatim. Returns None when not enforced."""
    project_root = pathlib.Path(project_root)
    if not recovery_enforced(project_root):
        return None
    return _append(project_root, key, {
        "kind": "failure", "key": str(key), "phase": str(phase),
        "rc": int(code), "stdout": str(stdout), "stderr": str(stderr),
    })


def record_disposition(
    project_root: pathlib.Path,
    key: str,
    phase: str,
    *,
    decision_ref: str,
    action: str,
    budget: str | int | float,
    end_condition: str,
) -> dict:
    """Record the automatic disposition of an unresolved failure.

    Every field is material: a disposition without a real decision reference,
    a bounded budget and a stop condition is refused instead of recorded.
    """
    missing = [
        name for name, value in (
            ("decision_ref", decision_ref), ("action", action),
            ("budget", budget), ("end_condition", end_condition),
        ) if value is None or (isinstance(value, str) and not value.strip())
    ]
    if missing:
        raise ValueError("missing disposition field(s): " + ", ".join(missing))
    if action not in DISPOSITION_ACTIONS:
        raise ValueError(f"unknown disposition action {action!r}")
    project_root = pathlib.Path(project_root)
    if not _recorded_auto_request(project_root, key, str(decision_ref)):
        raise ValueError(
            "decision_ref is not a recorded dp-auto business request for this key"
        )
    return _append(project_root, key, {
        "kind": "disposition", "key": str(key), "phase": str(phase),
        "decision_ref": str(decision_ref), "action": str(action),
        "budget": budget if isinstance(budget, (int, float)) else str(budget).strip(),
        "end_condition": str(end_condition).strip(),
    })


def _recorded_auto_request(project_root: pathlib.Path, key: str, decision_ref: str) -> bool:
    """Whether the ledger holds a real, answering dp-auto request for this key.

    A caller-supplied reference string is never enough: the row must be the
    recorded business decision (``kind=request``, one business decision,
    ``available=true``) of the same key. A damaged ledger refuses instead of
    looking like "nothing recorded".
    """
    path = project_root / LIFECYCLE_REL
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    started: set[str] = set()
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            return False
        if not isinstance(row, dict):
            return False
        logical = row.get("logical_id")
        if row.get("kind") == "record-start" and isinstance(logical, str):
            started.add(logical)
        if (row.get("kind") == "request"
                and row.get("decision_id") == decision_ref
                and row.get("key") == key
                and row.get("dp") == "dp-auto"
                and row.get("business_decisions") == 1
                and row.get("available") is True
                and isinstance(logical, str) and logical in started):
            return True
    return False


def _run_verification(project_root: pathlib.Path, verify_cmd: str) -> tuple[int, str, str]:
    """Run the bounded re-verification command and return its ACTUAL result."""
    argv = shlex.split(verify_cmd, posix=(os.name != "nt"))
    if not argv:
        raise ValueError("verification command is empty")
    try:
        proc = subprocess.run(
            argv, cwd=str(project_root), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=_ADVANCE_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return 124, "", f"[verification] timed out after {_ADVANCE_TIMEOUT_SEC}s"
    except OSError as exc:
        return 127, "", f"[verification] could not run: {exc}"
    return proc.returncode, proc.stdout, proc.stderr


def record_verification(
    project_root: pathlib.Path,
    key: str,
    phase: str,
    *,
    verify_cmd: str,
    rc: int | None = None,
    stdout: str = "",
    stderr: str = "",
) -> dict:
    """Record the bounded re-verification after a disposition.

    ``rc``/``stdout``/``stderr`` are accepted only for call-site compatibility:
    the recorded values are the ones the command actually produced just now. A
    self-reported ``rc=0`` therefore cannot release the phase edge.
    """
    del rc, stdout, stderr
    command = str(verify_cmd or "").strip()
    if not command:
        raise ValueError("verification command is missing")
    project_root = pathlib.Path(project_root)
    code, out, err = _run_verification(project_root, command)
    return _append(project_root, key, {
        "kind": "verification", "key": str(key), "phase": str(phase),
        "verify_cmd": command, "rc": int(code),
        "stdout": str(out), "stderr": str(err),
    })


def advance_allowed(
    project_root: pathlib.Path, key: str, phase: str
) -> tuple[bool, str, dict | None]:
    """Whether this (key, target phase) may run `advance_phase.py` now.

    A recorded failure stays open until a valid disposition of that same failure
    is followed by a verification record with rc=0. Anything unproven
    (corrupt row, disposition without re-verification) keeps the gate closed.
    """
    project_root = pathlib.Path(project_root)
    if not recovery_enforced(project_root):
        return True, "", None
    active_failure: dict | None = None
    disposition: dict | None = None
    for row in _rows(project_root, key):
        if row.get("kind") == "corrupt":
            return False, "advance-failure ledger is unreadable; inspect before advancing", active_failure
        if str(row.get("phase")) != str(phase):
            continue
        kind = row.get("kind")
        if kind == "failure":
            active_failure = row
            disposition = None
        elif kind == "disposition" and active_failure is not None:
            disposition = row
        elif kind == "verification" and active_failure is not None and disposition is not None:
            if row.get("rc") == 0 and disposition.get("action") in RELEASABLE_ACTIONS:
                active_failure = None
                disposition = None
    if active_failure is None:
        return True, "", None
    if disposition is None:
        return False, f"phase {phase} failed (rc={active_failure.get('rc')}) and has no automatic disposition", active_failure
    if disposition.get("action") not in RELEASABLE_ACTIONS:
        return False, f"disposition {disposition.get('action')!r} does not itself resume this phase", active_failure
    return (
        False,
        f"phase {phase} disposition {disposition.get('decision_ref')} has no passing re-verification",
        active_failure,
    )
