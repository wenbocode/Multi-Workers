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

import hashlib
import json
import os
import pathlib
from datetime import datetime, timezone
from typing import Any

FAILURE_LINE_PREFIX = "   - "

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
