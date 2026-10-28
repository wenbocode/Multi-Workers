"""test_autopilot_closure.py - L0/L1 tests for the done-gate closure primitives.

Key mw-done-closure-repair, task T-02 (design D-002/D-003/D-004).

Covered:
  - VC-003 (L0): the engineering vocabulary literals are absent from every
    `autopilot/*.py` source file (closure.py included; this test file lives at
    the package root and is therefore outside the scan surface).
  - VC-004 (L1): three-condition overwrite authorization truth table, four
    negative cases, each pure (no directory bytes change).
  - VC-005 (L1): all-true case, write/read field round-trip, atomic write
    (tmp + os.replace, no residue), idempotent delete, single-file marker.
  - failure_lines: stable-prefix extraction (verbatim remainder, CJK, curly
    quotes), header rejection, CRLF handling.
  - compose_reprompt_prompt: byte-exact three-part concatenation.
  - REPROMPT_INSTRUCTION: no vocabulary literal, no file names but the
    sanctioned one.

The vocabulary literals intentionally live in this file (package root) so that
the VC-003 scanner over `autopilot/` reports zero hits.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys
from datetime import datetime

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from autopilot import closure

# Engineering vocabulary that the scan surface must never hardcode.
VOCAB_LITERALS = ("系统行为变化", "行为影响", "未了事项")

MARKER_NAME = ".mw-achieved-baddraft.json"
TMP_NAME = ".mw-achieved-baddraft.json.tmp"

# Realistic advance subprocess stderr shape (CJK + curly quotes intact).
GATE_BLOCKED_STDERR = (
    "GATE BLOCKED: mw-done-closure-repair (current phase: verify)\n"
    "Current phase: verify\n"
    "   - NO MATCH: achieved.md missing pattern '系统行为变化' — 规则一\n"
    "   - NO MATCH: achieved.md missing pattern '行为影响' — “引号”规则二\n"
)
EXPECTED_FAILURE_LINES = [
    "NO MATCH: achieved.md missing pattern '系统行为变化' — 规则一",
    "NO MATCH: achieved.md missing pattern '行为影响' — “引号”规则二",
]

DRAFT = ("# Achieved\n\n" + ("body line\n" * 20)).encode("utf-8")
assert len(DRAFT) >= 200


def _key_dir(tmp_path: pathlib.Path, draft: bytes = DRAFT) -> pathlib.Path:
    key_dir = tmp_path / "key"
    key_dir.mkdir()
    (key_dir / "achieved.md").write_bytes(draft)
    return key_dir


def _snapshot(directory: pathlib.Path) -> dict[str, bytes]:
    return {
        path.name: path.read_bytes()
        for path in sorted(directory.iterdir())
        if path.is_file()
    }


def _marker(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# --- VC-003 / L0: no vocabulary literals in the autopilot source -------------


def test_vc003_autopilot_source_has_no_vocab_literals() -> None:
    source_dir = pathlib.Path(__file__).parent / "autopilot"
    scanned = sorted(source_dir.rglob("*.py"))
    # The scan surface is non-empty and includes the new module.
    assert scanned, f"no python source found under {source_dir}"
    assert (source_dir / "closure.py") in scanned

    offenders: list[str] = []
    for path in scanned:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for literal in VOCAB_LITERALS:
                if literal in line:
                    offenders.append(f"{path.name}:{lineno}: {literal}")
    assert offenders == [], f"vocab literals found in autopilot source: {offenders}"


@pytest.mark.parametrize("literal", VOCAB_LITERALS)
def test_reprompt_instruction_has_no_vocab_literal(literal: str) -> None:
    assert literal not in closure.REPROMPT_INSTRUCTION


@pytest.mark.parametrize(
    "file_name",
    ["output.md", "task.md", "plan.md", "design.md", "spec.md", "trace.log"],
)
def test_reprompt_instruction_names_no_other_file(file_name: str) -> None:
    assert file_name not in closure.REPROMPT_INSTRUCTION


def test_reprompt_instruction_tells_the_reviewer_what_to_do() -> None:
    instruction = closure.REPROMPT_INSTRUCTION
    assert "## Achieved" in instruction
    assert "PASS/FAIL" in instruction
    assert "## Quality Gate Report" in instruction


# --- failure_lines: stable-prefix extraction --------------------------------


def test_failure_lines_extracts_prefixed_lines_verbatim() -> None:
    assert closure.failure_lines(GATE_BLOCKED_STDERR) == EXPECTED_FAILURE_LINES


def test_failure_lines_skips_header_and_unprefixed_lines() -> None:
    err = (
        "GATE BLOCKED: key (current phase: verify)\n"
        "Current phase: verify\n"
        "  - one leading space too few\n"
        "- no indent at all\n"
        "trailing prose\n"
    )
    assert closure.failure_lines(err) == []


def test_failure_lines_returns_empty_list_without_failures() -> None:
    assert closure.failure_lines("") == []
    assert closure.failure_lines("GATE BLOCKED: key\n\nAll good\n") == []


def test_failure_lines_strips_only_the_exact_prefix() -> None:
    # Exactly "   - " (3 spaces + dash + space) is structural; the remainder,
    # including further leading spaces, is preserved byte-for-byte.
    err = "   -    double spaced payload\n"
    assert closure.failure_lines(err) == ["   double spaced payload"]


def test_failure_lines_crlf_input_strips_line_trailing_cr() -> None:
    err = (
        "GATE BLOCKED: key\r\n"
        "Current phase: verify\r\n"
        "   - NO MATCH: achieved.md missing pattern 'a'\r\n"
        "   - NO MATCH: achieved.md missing pattern 'b'\r\n"
    )
    lines = closure.failure_lines(err)
    assert lines == [
        "NO MATCH: achieved.md missing pattern 'a'",
        "NO MATCH: achieved.md missing pattern 'b'",
    ]
    assert all("\r" not in line for line in lines)


def test_has_achieved_failure_detects_literal() -> None:
    assert closure.has_achieved_failure(EXPECTED_FAILURE_LINES) is True
    assert closure.has_achieved_failure(["NO MATCH: other rule"]) is False
    assert closure.has_achieved_failure([]) is False


# --- compose_reprompt_prompt: byte-exact concatenation -----------------------


def test_compose_reprompt_prompt_is_byte_exact_base_plus_instruction_plus_lines() -> None:
    base = "# L3 reviewer\n\nRound 2 context\n"
    expected = (
        base
        + closure.REPROMPT_INSTRUCTION
        + "NO MATCH: achieved.md missing pattern '系统行为变化' — 规则一\n"
        + "NO MATCH: achieved.md missing pattern '行为影响' — “引号”规则二\n"
    )
    assert closure.compose_reprompt_prompt(base, EXPECTED_FAILURE_LINES) == expected


def test_compose_reprompt_prompt_without_lines_is_base_plus_instruction() -> None:
    base = "base"
    assert (
        closure.compose_reprompt_prompt(base, []) == base + closure.REPROMPT_INSTRUCTION
    )


# --- marker read/write/delete ------------------------------------------------


def test_read_marker_returns_none_when_absent(tmp_path: pathlib.Path) -> None:
    key_dir = _key_dir(tmp_path)
    assert closure.read_bad_draft_marker(key_dir) is None


def test_read_marker_returns_none_on_corrupt_json(tmp_path: pathlib.Path) -> None:
    key_dir = _key_dir(tmp_path)
    path = key_dir / MARKER_NAME
    path.write_bytes(b"{not json")
    assert closure.read_bad_draft_marker(key_dir) is None
    path.write_bytes(b'["not", "an", "object"]')
    assert closure.read_bad_draft_marker(key_dir) is None
    path.write_bytes(b"\xff\xfe\x00garbage")
    assert closure.read_bad_draft_marker(key_dir) is None


def test_write_marker_requires_the_achieved_evidence(tmp_path: pathlib.Path) -> None:
    key_dir = tmp_path / "key"
    key_dir.mkdir()
    with pytest.raises(FileNotFoundError):
        closure.write_bad_draft_marker(key_dir, ["NO MATCH: achieved.md ..."])
    assert not (key_dir / MARKER_NAME).exists()


def test_write_read_marker_round_trips_all_fields(tmp_path: pathlib.Path) -> None:
    key_dir = _key_dir(tmp_path)
    closure.write_bad_draft_marker(key_dir, EXPECTED_FAILURE_LINES)
    marker = _marker(key_dir / MARKER_NAME)

    assert marker["file"] == "achieved.md"
    assert marker["sha256"] == hashlib.sha256(DRAFT).hexdigest()
    assert marker["failures"] == EXPECTED_FAILURE_LINES
    declared = datetime.fromisoformat(marker["declared_at"])
    assert declared.tzinfo is not None

    # UTF-8, unescaped CJK, trailing newline in the on-disk bytes.
    raw = (key_dir / MARKER_NAME).read_text(encoding="utf-8")
    assert "系统行为变化" in raw
    assert "\\u" not in raw
    assert raw.endswith("\n")

    assert closure.read_bad_draft_marker(key_dir) == marker


def test_write_marker_is_atomic_via_tmp_and_os_replace(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key_dir = _key_dir(tmp_path)
    marker_path = key_dir / MARKER_NAME
    tmp_path_expected = key_dir / TMP_NAME
    calls: list[tuple[str, str]] = []
    real_replace = closure.os.replace

    def spy(src, dst):  # type: ignore[no-untyped-def]
        src_p = pathlib.Path(src)
        dst_p = pathlib.Path(dst)
        assert src_p.name == TMP_NAME
        assert src_p == tmp_path_expected
        assert dst_p == marker_path
        assert src_p.exists(), "tmp file must exist at replace time"
        assert not dst_p.exists(), "final marker must not exist before replace"
        calls.append((str(src_p), str(dst_p)))
        return real_replace(src, dst)

    monkeypatch.setattr(closure.os, "replace", spy)
    closure.write_bad_draft_marker(key_dir, EXPECTED_FAILURE_LINES)

    assert len(calls) == 1
    assert not tmp_path_expected.exists(), "no .tmp residue after atomic write"
    assert marker_path.is_file()
    assert closure.read_bad_draft_marker(key_dir) is not None


def test_write_marker_repeated_failures_keep_a_single_file(
    tmp_path: pathlib.Path,
) -> None:
    key_dir = _key_dir(tmp_path)
    closure.write_bad_draft_marker(key_dir, ["NO MATCH: achieved.md rule one"])
    closure.write_bad_draft_marker(key_dir, ["NO MATCH: achieved.md rule two"])

    files = sorted(p.name for p in key_dir.iterdir() if p.is_file())
    assert files == sorted(["achieved.md", MARKER_NAME])
    assert closure.read_bad_draft_marker(key_dir)["failures"] == [
        "NO MATCH: achieved.md rule two"
    ]


def test_delete_marker_is_idempotent(tmp_path: pathlib.Path) -> None:
    key_dir = _key_dir(tmp_path)
    closure.write_bad_draft_marker(key_dir, EXPECTED_FAILURE_LINES)
    assert closure.read_bad_draft_marker(key_dir) is not None

    closure.delete_bad_draft_marker(key_dir)
    assert closure.read_bad_draft_marker(key_dir) is None
    assert not (key_dir / MARKER_NAME).exists()

    closure.delete_bad_draft_marker(key_dir)  # absent: silent no-op
    assert closure.read_bad_draft_marker(key_dir) is None


# --- VC-004 / VC-005: three-condition overwrite authorization ----------------


def test_vc004_negative_marker_absent(tmp_path: pathlib.Path) -> None:
    key_dir = _key_dir(tmp_path)
    before = _snapshot(key_dir)
    assert closure.overwrite_authorized(None, DRAFT, []) is False
    assert _snapshot(key_dir) == before


def test_vc004_negative_sha_mismatch(tmp_path: pathlib.Path) -> None:
    key_dir = _key_dir(tmp_path)
    marker = {
        "file": "achieved.md",
        "sha256": hashlib.sha256(b"a different rejected draft").hexdigest(),
        "declared_at": "2026-09-25T00:00:00+00:00",
        "failures": EXPECTED_FAILURE_LINES,
    }
    before = _snapshot(key_dir)
    assert closure.overwrite_authorized(marker, DRAFT, []) is False
    assert _snapshot(key_dir) == before


def test_vc004_negative_marker_failures_without_achieved_line(
    tmp_path: pathlib.Path,
) -> None:
    key_dir = _key_dir(tmp_path)
    marker = {
        "file": "achieved.md",
        "sha256": hashlib.sha256(DRAFT).hexdigest(),
        "declared_at": "2026-09-25T00:00:00+00:00",
        "failures": ["NO MATCH: some unrelated rule", "GATE BLOCKED: key"],
    }
    before = _snapshot(key_dir)
    # The caller-side lines are explicitly ignored: the anchor is the marker.
    assert closure.overwrite_authorized(marker, DRAFT, EXPECTED_FAILURE_LINES) is False
    assert _snapshot(key_dir) == before


def test_vc004_negative_empty_current_bytes(tmp_path: pathlib.Path) -> None:
    key_dir = _key_dir(tmp_path)
    marker = {
        "file": "achieved.md",
        "sha256": hashlib.sha256(DRAFT).hexdigest(),
        "declared_at": "2026-09-25T00:00:00+00:00",
        "failures": EXPECTED_FAILURE_LINES,
    }
    before = _snapshot(key_dir)
    assert closure.overwrite_authorized(marker, b"", []) is False
    assert _snapshot(key_dir) == before


def test_vc005_all_conditions_true_authorizes_and_cycle_closes(
    tmp_path: pathlib.Path,
) -> None:
    key_dir = _key_dir(tmp_path)
    closure.write_bad_draft_marker(key_dir, EXPECTED_FAILURE_LINES)
    marker = closure.read_bad_draft_marker(key_dir)
    assert marker is not None

    current_bytes = (key_dir / "achieved.md").read_bytes()
    assert closure.overwrite_authorized(marker, current_bytes, []) is True

    # Authorized overwrite: new draft bytes land, marker is deleted in the same
    # lock scope, and the next rejection re-arms a single marker file.
    new_draft = ("# Achieved\n\n" + ("fixed line\n" * 30)).encode("utf-8")
    (key_dir / "achieved.md").write_bytes(new_draft)
    closure.delete_bad_draft_marker(key_dir)
    assert closure.read_bad_draft_marker(key_dir) is None

    before = _snapshot(key_dir)
    assert closure.overwrite_authorized(marker, new_draft, []) is False
    assert _snapshot(key_dir) == before


def test_vc005_authorized_uses_marker_state_current_bytes_only(
    tmp_path: pathlib.Path,
) -> None:
    key_dir = _key_dir(tmp_path)
    marker = {
        "file": "achieved.md",
        "sha256": hashlib.sha256(DRAFT).hexdigest(),
        "declared_at": "2026-09-25T00:00:00+00:00",
        "failures": EXPECTED_FAILURE_LINES,
    }
    assert closure.overwrite_authorized(marker, DRAFT, []) is True
    # One byte of external edit (human repair) breaks authorization.
    assert closure.overwrite_authorized(marker, DRAFT + b"\n", []) is False
