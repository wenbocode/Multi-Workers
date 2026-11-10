"""closure.py - done-gate closure primitives (key mw-done-closure-repair, T-02).

Pure logic plus minimal file IO for the ``achieved.md`` closure loop
(design D-002/D-003/D-004). This module never imports ``conductor``; the
dependency is one-way (``conductor -> closure``).

Contract surface (T-02 task card, design 2.2):

  - ``FAILURE_LINE_PREFIX``  stable advance_phase.py stderr line prefix.
  - ``failure_lines(err)``   extract every failure line, verbatim remainder.
  - ``has_achieved_failure(lines)``  trigger predicate for the closure loop.
  - ``REPROMPT_INSTRUCTION`` fixed generic directive appended to a reprompt.
  - ``compose_reprompt_prompt(base, lines)``  base + instruction + lines.
  - ``read_bad_draft_marker(key_dir)``   marker JSON or None (never raises).
  - ``write_bad_draft_marker(key_dir, failures)``  atomic tmp + os.replace.
  - ``delete_bad_draft_marker(key_dir)``  idempotent unlink.
  - ``overwrite_authorized(marker, current_bytes, failure_lines)``  pure
    three-condition authorization for replacing a bad draft.

The marker is content addressed: ``sha256`` is ``hashlib.sha256`` over the
exact ``achieved.md`` bytes (no EOL normalization), so any external edit -
including a newline-only human repair - invalidates the authorization.

The module must not hardcode engineering vocabulary literals (VC-003 scans
``autopilot/*.py`` for zero hits). The banned-literal tests live at the
package root.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import pathlib
from datetime import datetime, timezone
from typing import Any

import decision_signoff_result

FAILURE_LINE_PREFIX = "   - "

# ── H13 stage-close sign-off consumer (T26) ─────────────────────────────────
#
# The stage-close gate may only be opened from a PM's CURRENT stage submission
# (`source` below), never from a historical `record.material` copy, and every
# key for which the original rule requires a sign-off must still validate with
# `validate_key_signoff` against the matter and evidence submitted now. A
# passing sign-off still does not close the stage and never approves the next
# one (that is the gate consumer's separate job).

STAGE_CLOSE_MATERIAL_SOURCE = "pm-current"
STAGE_CLOSE_MATERIAL_SCHEMA = 1
_MATERIAL_NAME = "stage-{number}-close.material.json"
_KEYS = ("delivery_goal", "actual_completion", "verification_evidence", "unfinished_impact")


@dataclasses.dataclass(frozen=True)
class StageCloseCheck:
    ok: bool
    issues: tuple[str, ...]
    signed: tuple[str, ...]
    skipped: tuple[str, ...]
    material: pathlib.Path


def stage_close_material_path(project_root: pathlib.Path, number: int) -> pathlib.Path:
    return (
        pathlib.Path(project_root) / ".agenticdoc" / "_autopilot" / "stages"
        / _MATERIAL_NAME.format(number=int(number))
    )


def _signoff_required(key_dir: pathlib.Path) -> bool:
    """Original applicability rule (T25): `signoff: disable` or no decide row skips."""
    try:
        cfg = json.loads((key_dir.parent.parent / ".mw" / "decide.json").read_text(encoding="utf-8"))
        if isinstance(cfg, dict) and cfg.get("signoff") == "disable":
            return False
    except (OSError, ValueError):
        pass
    archive = key_dir.parent / "_autopilot" / "decisions.jsonl"
    try:
        text = archive.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False
    except (OSError, UnicodeDecodeError):
        return True  # unreadable is not "no requirement"
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict) or row.get("kind") != "decide":
            continue
        decision_id = row.get("decision_id")
        if row.get("key") == key_dir.name or (
            isinstance(decision_id, str) and decision_id.endswith(":" + key_dir.name)
        ):
            return True
    return False


def _current_material_issue(project_root: pathlib.Path, number: int) -> tuple[dict | None, list[str]]:
    path = stage_close_material_path(project_root, number)
    issues: list[str] = []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [f"MISSING: {path.name} — PM must submit the current stage-close material"]
    except (OSError, ValueError) as exc:
        return None, [f"UNREADABLE: {path.name} ({exc})"]
    if not isinstance(raw, dict):
        return None, [f"INVALID: {path.name} is not an object"]
    return raw, []


def _material_structure_issues(number: int, raw: dict) -> list[str]:
    issues: list[str] = []
    name = _MATERIAL_NAME.format(number=int(number))
    if raw.get("schema") != STAGE_CLOSE_MATERIAL_SCHEMA:
        issues.append(f"INVALID: {name} schema")
    if raw.get("stage") != int(number):
        issues.append(f"INVALID: {name} stage mismatch")
    if raw.get("source") != STAGE_CLOSE_MATERIAL_SOURCE:
        issues.append(
            f"STALE: {name} source={raw.get('source')!r} is not the current PM submission"
        )
    if not isinstance(raw.get("submitted_at"), str) or not raw["submitted_at"].strip():
        issues.append(f"INVALID: {name} has no submitted_at")
    if not isinstance(raw.get("key_signoffs"), dict):
        issues.append(f"INVALID: {name} key_signoffs")
    return issues


def stage_close_material_issues(
    project_root: pathlib.Path, number: int, raw: object, keys: list[str] | tuple[str, ...]
) -> list[str]:
    """Validate one PM stage-close submission without writing it.

    Used both by the read-only close check and by the production submission
    entry, so an invalid submission can never become the current material.
    """
    if not isinstance(raw, dict):
        return [f"INVALID: {_MATERIAL_NAME.format(number=int(number))} is not an object"]
    issues = _material_structure_issues(int(number), raw)
    required = [key for key in keys if _signoff_required(pathlib.Path(project_root) / ".agenticdoc" / key)]
    if not required:
        return issues
    signoffs = raw.get("key_signoffs") if isinstance(raw.get("key_signoffs"), dict) else {}
    issues.extend(_acceptance_issue(raw))
    for key in required:
        entry = signoffs.get(key)
        if not isinstance(entry, dict):
            issues.append(f"MISSING: {key} has no current sign-off material")
            continue
        matter = entry.get("matter")
        evidence = entry.get("evidence")
        if not isinstance(matter, dict) or set(matter) != set(_KEYS):
            issues.append(f"INVALID: {key} sign-off matter is not the four-part submission")
            continue
        if evidence is None:
            issues.append(f"MISSING: {key} current evidence")
            continue
        validation = decision_signoff_result.validate_key_signoff(
            pathlib.Path(project_root) / ".agenticdoc" / key, key, matter, evidence
        )
        if not validation.valid or validation.conclusion != "finalize":
            issues.append(f"SIGNOFF: {key} - {validation.reason}")
    return issues


def write_stage_close_material(project_root: pathlib.Path, number: int, raw: dict) -> pathlib.Path:
    """Atomically install one already-validated current PM submission."""
    path = stage_close_material_path(project_root, number)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(raw, ensure_ascii=False, indent=2) + "\n"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8", newline="\n")
    os.replace(tmp, path)
    return path


def _acceptance_issue(project_root_material: dict) -> list[str]:
    """Disclosed risks that need explicit user acceptance must carry it."""
    risks = project_root_material.get("user_risks")
    if risks is None:
        return []
    if not isinstance(risks, list):
        return ["INVALID: user_risks must be a list"]
    issues: list[str] = []
    for index, item in enumerate(risks):
        if not isinstance(item, dict):
            issues.append(f"RISK: entry {index} is not an object")
            continue
        if not str(item.get("risk") or "").strip():
            issues.append(f"RISK: entry {index} has no risk")
        if not str(item.get("accepted_by") or "").strip():
            issues.append(f"RISK: entry {index} needs explicit user acceptance")
    return issues


def stage_close_check(
    project_root: pathlib.Path, number: int, keys: list[str] | tuple[str, ...]
) -> StageCloseCheck:
    """Read-only H13 eligibility for opening one stage-close gate.

    Only keys for which the original rule requires a sign-off are checked; a
    stage with no such key is eligible (no forced scope expansion)."""
    project_root = pathlib.Path(project_root)
    path = stage_close_material_path(project_root, number)
    required = [key for key in keys if _signoff_required(project_root / ".agenticdoc" / key)]
    skipped = tuple(key for key in keys if key not in required)
    if not required:
        return StageCloseCheck(True, (), (), skipped, path)
    raw, issues = _current_material_issue(project_root, number)
    if raw is None:
        return StageCloseCheck(False, tuple(issues), (), skipped, path)
    issues.extend(stage_close_material_issues(project_root, number, raw, required))
    signoffs = raw.get("key_signoffs") if isinstance(raw.get("key_signoffs"), dict) else {}
    signed = tuple(
        key for key in required
        if isinstance(key, str) and key in signoffs
        and not any(issue.startswith(f"SIGNOFF: {key}") or issue.startswith(f"INVALID: {key} ")
                    or issue.startswith(f"MISSING: {key} ") for issue in issues)
    )
    return StageCloseCheck(not issues, tuple(issues), signed, skipped, path)

ACHIEVED_FILE_NAME = "achieved.md"
BAD_DRAFT_MARKER_NAME = ".mw-achieved-baddraft.json"
BAD_DRAFT_TMP_NAME = ".mw-achieved-baddraft.json.tmp"

# Fixed generic directive for an L3 reprompt. It explains that the lines below
# are the verbatim done-gate rejection, tells the reviewer how to reorganize
# the `## Achieved` section, and forbids touching any verdict or quality-gate
# assertion. Deliberately free of engineering vocabulary and of any concrete
# file name other than the sanctioned evidence file.
REPROMPT_INSTRUCTION = (
    "\n\n"
    "The lines below are the verbatim rejection output of the engineering\n"
    "done gate for the evidence file achieved.md. In the '## Achieved'\n"
    "section of your report, organize one sub-section per listed rule and\n"
    "quote each rule text verbatim, so every rejected rule is visibly\n"
    "covered. Keep every sub-section heading strictly below the '##' level\n"
    "(for example '###' lines): the '## Achieved' section is transcribed\n"
    "only up to the next '##' heading, so a '## ' line inside the section\n"
    "would be cut from the evidence file. Do not change any PASS/FAIL\n"
    "verdict, and do not alter any assertion in the\n"
    "'## Quality Gate Report' section.\n"
    "\n"
    "Rejected lines:\n"
)


def failure_lines(err: str) -> list[str]:
    """Return the failure lines of an ``advance_phase.py`` stderr payload.

    A failure line starts with ``FAILURE_LINE_PREFIX`` (3 spaces + dash +
    space) after optional ``\\r`` stripping. That prefix is structural and is
    removed; the remainder of the line - including any further leading
    whitespace - is preserved byte-for-byte. Lines are split on ``\\n``, so a
    trailing ``\\r`` from CRLF input is dropped (line-internal bytes, e.g. a
    stray ``\\r``, are kept). Order is source order.
    """
    lines: list[str] = []
    for raw in err.split("\n"):
        if raw.endswith("\r"):
            raw = raw[:-1]
        if raw.startswith(FAILURE_LINE_PREFIX):
            lines.append(raw[len(FAILURE_LINE_PREFIX) :])
    return lines


def has_achieved_failure(lines: list[str]) -> bool:
    """True when any line mentions the evidence file by literal name."""
    return any(
        isinstance(line, str) and ACHIEVED_FILE_NAME in line for line in lines
    )


def compose_reprompt_prompt(base_prompt: str, lines: list[str]) -> str:
    """Compose the reprompt prompt as ``base + instruction + lines``.

    Deterministic, byte-exact contract: the instruction constant is inserted
    verbatim, then each failure line verbatim followed by ``\\n``. No other
    characters are added (callers assert the full string equality).
    """
    return base_prompt + REPROMPT_INSTRUCTION + "".join(f"{line}\n" for line in lines)


def _marker_path(key_dir: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(key_dir) / BAD_DRAFT_MARKER_NAME


def read_bad_draft_marker(key_dir: pathlib.Path) -> dict[str, Any] | None:
    """Read the bad-draft marker; return None when absent or not a JSON object.

    Corrupt content (bad JSON, bad encoding, unreadable path, non-object JSON)
    is reported as None instead of raising: the caller treats "no usable
    marker" and "no marker" identically (fail-closed).
    """
    try:
        raw = _marker_path(key_dir).read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def write_bad_draft_marker(key_dir: pathlib.Path, failures: list[str]) -> None:
    """Atomically record a rejected draft and the gate failures behind it.

    The hash is computed over the exact current ``achieved.md`` bytes, so the
    file must exist (``FileNotFoundError`` propagates otherwise). The JSON is
    written as UTF-8 with ``ensure_ascii=False`` and LF endings to a fixed-name
    temp file, then moved into place with ``os.replace`` (no visible partial
    file, no leftover temp file). Repeated failures over the same key keep a
    single marker file.
    """
    key_dir = pathlib.Path(key_dir)
    achieved = key_dir / ACHIEVED_FILE_NAME
    digest = hashlib.sha256(achieved.read_bytes()).hexdigest()

    payload = {
        "file": ACHIEVED_FILE_NAME,
        "sha256": digest,
        "declared_at": datetime.now(timezone.utc).isoformat(),
        "failures": list(failures),
    }
    content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

    key_dir.mkdir(parents=True, exist_ok=True)
    tmp = key_dir / BAD_DRAFT_TMP_NAME
    tmp.write_text(content, encoding="utf-8", newline="\n")
    os.replace(tmp, _marker_path(key_dir))


def delete_bad_draft_marker(key_dir: pathlib.Path) -> None:
    """Remove the bad-draft marker; missing marker is a silent no-op."""
    try:
        _marker_path(key_dir).unlink()
    except FileNotFoundError:
        pass


def overwrite_authorized(
    marker: dict[str, Any] | None,
    current_bytes: bytes,
    failure_lines: list[str],
) -> bool:
    """Decide whether a rejected draft may be replaced (pure, no IO).

    All three conditions must hold:
      1. a marker exists (and is a JSON object with usable fields),
      2. the marker hash equals ``sha256(current_bytes)`` - the on-disk draft
         is still exactly the rejected one, and
      3. the marker's *recorded* failure lines mention the evidence file.

    ``failure_lines`` is the caller's current-round parse; it is deliberately
    not part of the decision (kept for future extension/assertions), so the
    anchor stays on the persisted marker state. Every check fails closed for
    malformed markers.
    """
    if not isinstance(marker, dict):
        return False
    recorded_sha = marker.get("sha256")
    if not isinstance(recorded_sha, str):
        return False
    if recorded_sha != hashlib.sha256(current_bytes).hexdigest():
        return False
    recorded_failures = marker.get("failures")
    if not isinstance(recorded_failures, list):
        return False
    return has_achieved_failure(recorded_failures)
