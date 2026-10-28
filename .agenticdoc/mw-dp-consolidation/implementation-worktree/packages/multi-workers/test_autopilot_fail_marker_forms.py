"""L1 truth table for the L3 FAIL marker forms (key mw-l3-fail-marker-forms, T-01).

TDD contract: the implementation lands in ``autopilot/conductor.py`` (worker B)

* ``_L3_FAIL_RE = re.compile(r"\\|\\s*\\**\\s*FAIL\\b")`` stays the pipe rule;
* ``_L3_FAIL_BULLET_RE = re.compile(r"^\\s*[-*]\\s*\\**\\s*FAIL\\b")``;
* ``_L3_FAIL_PROSE_RE = re.compile(r"^[^|\\n]*?\\**\\s*FAIL\\s*[—–-]")``;
* ``_L3_FAIL_ZERO_RE = re.compile(r"FAIL\\s*\\**\\s*[：:=]?\\s*\\**\\s*0\\b")``;
* ``_l3_fail_marker_line(text: str) -> str | None`` scans a whole document line
  by line and returns the FIRST failing line verbatim (or ``None``). A line
  fires when the pipe rule or the prose rule matches anywhere in the line, or
  when the bullet rule matches AND the token-local zero exemption does NOT fire
  (``_L3_FAIL_ZERO_RE.match(line, pos_of_FAIL_token)`` -- never a whole-line
  search).

At HEAD the constants and the helper do not exist yet, so collection succeeds
and every case below fails red against ``conductor``; worker B turns it green.
Positive / negative anchors are frozen live L3 artifacts (provenance cited per
line); the variants in ``TestConstructedVariants`` are explicitly constructed
character-level cases and carry no corpus provenance.
"""

from __future__ import annotations

import pathlib
import re
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from autopilot import conductor  # noqa: E402

# Frozen pipe rule (the pre-existing constant; must not drift).
_PIPE_PATTERN = r"\|\s*\**\s*FAIL\b"

_FAIL_CONSTANTS = (
    "_L3_FAIL_RE",
    "_L3_FAIL_BULLET_RE",
    "_L3_FAIL_PROSE_RE",
    "_L3_FAIL_ZERO_RE",
)


def _fail_line(text: str) -> str | None:
    """Call the TDD-red helper with a readable failure when it is absent."""
    helper = getattr(conductor, "_l3_fail_marker_line", None)
    if helper is None:
        pytest.fail("conductor._l3_fail_marker_line is not implemented yet (TDD red)")
    return helper(text)


def _const(name: str) -> re.Pattern[str]:
    """Fetch one TDD-red constant with a readable failure when it is absent."""
    value = getattr(conductor, name, None)
    if value is None:
        pytest.fail(f"conductor.{name} is not implemented yet (TDD red)")
    return value


def _fail_token_pos(line: str, pattern: re.Pattern[str]) -> int:
    """Offset of the FAIL token inside an anchored bullet match on ``line``."""
    match = pattern.match(line)
    assert match is not None, f"bullet rule did not match {line!r}"
    return match.start() + match.group(0).rindex("FAIL")


# Multi-line surfaces: the tail-of-file QG table must stay visible to the
# scanner, and the earliest failing line must win over a later one.
_TLDR_FAIL_LINE = "TL;DR: FAIL — 21/30 VC 通过，9 项失败"
_TLDR_PASS_LINE = "TL;DR: PASS 35，FAIL 0，needs-rerun 0。"
_QG_PIPE_LINE = "| VC-001 | FAIL | yes | 需重跑 1 | evidence/x.txt |"
_QG_PASS_LINE = "| VC-002 | PASS | - | - | evidence/y.txt |"


class TestPositiveAnchors:
    """Frozen live artifacts whose L3 line carries a FAIL marker."""

    def test_naive_pipe_cell(self) -> None:
        # source: feature-mvp-closeout l3-a1 report.md:26 shape
        line = "| VC-001 | FAIL | yes | 需重跑 1 | evidence/x.txt |"
        assert _fail_line(line) == line

    def test_bold_pipe_cell(self) -> None:
        # source: feature-inline-marker-patchkit l3-a3 output.md:22 shape
        line = "| VC-006 | **FAIL** | no | ... |"
        assert _fail_line(line) == line

    def test_slash_pipe_cell(self) -> None:
        # source: feature-gui-time-mvp-board l3-a2 report.md:17
        line = "| 总裁决 | **FAIL / below** |"
        assert _fail_line(line) == line

    def test_chinese_colon_bullet_nonzero(self) -> None:
        # source: feature-sampling-human-channel l3-a1 output.md:12
        line = "- **FAIL：9**"
        assert _fail_line(line) == line

    def test_line_start_prose(self) -> None:
        # source: feature-sampling-human-channel l3-a1 output.md:3
        line = "FAIL — 21/30 VC 通过，9 项失败"
        assert _fail_line(line) == line


class TestWholeFileSurface:
    """The scanner walks the entire document, not just the first section."""

    def test_qg_table_tail_is_scanned_when_tldr_is_clean(self) -> None:
        doc = "\n".join(
            [
                "# L3 report",
                _TLDR_PASS_LINE,
                "",
                "## Quality Gate Report",
                _QG_PASS_LINE,
                _QG_PIPE_LINE,
            ]
        )
        assert _fail_line(doc) == _QG_PIPE_LINE

    def test_first_failing_line_wins_over_later_qg_table(self) -> None:
        doc = "\n".join(
            [
                "# L3 report",
                _TLDR_FAIL_LINE,
                "",
                "## Quality Gate Report",
                _QG_PASS_LINE,
                _QG_PIPE_LINE,
            ]
        )
        assert _fail_line(doc) == _TLDR_FAIL_LINE


class TestConstructedVariants:
    """Constructed character-level cases (no corpus provenance)."""

    def test_bare_bold_fail_line(self) -> None:
        # Constructed: first `*` is the bullet marker, second opens the bold run.
        line = "**FAIL**"
        assert _fail_line(line) == line

    def test_second_token_zero_does_not_exempt_first_token(self) -> None:
        # Constructed: the `FAIL：0` at the end must not exempt `FAIL 9`.
        line = "- FAIL 9 项，其中 FAIL：0"
        assert _fail_line(line) == line

    def test_ascii_colon_bullet_nonzero(self) -> None:
        # Constructed: ASCII colon form of the Chinese-colon anchor.
        line = "- FAIL: 9"
        assert _fail_line(line) == line


class TestNegativeAnchors:
    """Frozen live artifacts whose FAIL mention is a zero / meta / lowercase token."""

    def test_prose_zero_with_nonblocking_leftover(self) -> None:
        # source: cigate a1 output.md:3
        line = (
            "PASS（有非阻断遗留）——35/35 条 VC "
            "均有 PASS 证据，FAIL=0，needs-rerun=0。"
        )
        assert _fail_line(line) is None

    def test_bold_summary_zero(self) -> None:
        # source: cigate a1 report.md:50
        line = (
            "**汇总**：PASS 35，FAIL 0，needs-rerun 0。"
            "质量门禁结论为 "
            "**PASS（有非阻断证据维护遗留）**。"
        )
        assert _fail_line(line) is None

    def test_bold_ratio_summary_zero(self) -> None:
        # source: cigate a2 output.md:84
        line = "**汇总**：**PASS 35 / FAIL 0 / needs-rerun 0**。"
        assert _fail_line(line) is None

    def test_zero_fail_substring_inside_bullet(self) -> None:
        # source: tier-a a1 report.md:44
        line = "- VC：**32 PASS / 0 FAIL**（按冻结的 VC 与已记录 EXECUTE 证据）。"
        assert _fail_line(line) is None

    def test_bullet_zero_value_hard_trap(self) -> None:
        # source: tier-a a2 report.md:53 -- bullet shape, zero value -> exempt.
        line = "- FAIL：0"
        assert _fail_line(line) is None

    def test_gate_summary_zero(self) -> None:
        # source: mvp a2 output.md:10
        line = "- 质量门禁：38 PASS、0 FAIL、0 needs-rerun。"
        assert _fail_line(line) is None

    def test_blockquote_summary_zero(self) -> None:
        # source: params a3 output.md:12
        line = "> 总结：**PASS 24 / FAIL 0 / needs-rerun 0**。"
        assert _fail_line(line) is None

    def test_bold_gate_verdict_zero(self) -> None:
        # source: freshness report.md:31
        line = "**门禁总判定：PASS（19 PASS / 0 FAIL / 1 needs-rerun）。**"
        assert _fail_line(line) is None

    def test_lowercase_metric_tokens(self) -> None:
        # source: cigate a1 output.md:12 shape -- lowercase `fail_items`.
        line = (
            "- 最终 `build-runs/ci/exports/verify_report.json#summary`："
            "`verify_items=35`、`fail_items=[]`、`pending_items=[]`。"
        )
        assert _fail_line(line) is None

    def test_suite_count_lowercase_failed(self) -> None:
        # source: cigate a2 output.md:42 shape -- suite counts, not VC markers.
        line = (
            "- `regression_report.json`：`tests/featureci` **337 passed / 0 failed**；"
            "全量 **3005 passed / 9 failed**，`subset=true`。"
        )
        assert _fail_line(line) is None

    def test_bare_suite_count_line(self) -> None:
        # source: feature-gui-time a2 report.md:74 shape
        line = "9 failed"
        assert _fail_line(line) is None

    def test_failed_is_not_fail(self) -> None:
        # Framework superset sample: `FAIL` requires a word boundary.
        line = "FAILED"
        assert _fail_line(line) is None

    def test_meta_pass_fail_mention(self) -> None:
        # source: tier-a a1 output.md:12 shape -- meta description of rows.
        line = (
            "- `## Quality Gate Report`：逐条 VC PASS/FAIL、"
            "needs-rerun 均有断言行。"
        )
        assert _fail_line(line) is None


class TestInlineNegation:
    """A zero-value mention inside a failing pipe row must not exempt it."""

    def test_pipe_hit_with_inline_zero_fail(self) -> None:
        # source: featuremark a3 report.md:44 shape
        line = (
            "| VC-034 | **FAIL** | yes | `regression_report.json` 记录 "
            "featuremark 0 fail、全量 9=registered 9。 |"
        )
        assert _fail_line(line) == line


class TestRegexUnits:
    """Character-level checks on the four compiled constants."""

    def test_constants_exist(self) -> None:
        for name in _FAIL_CONSTANTS:
            assert isinstance(_const(name), re.Pattern), name

    def test_pipe_pattern_is_unchanged(self) -> None:
        assert _const("_L3_FAIL_RE").pattern == _PIPE_PATTERN

    def test_pipe_rule_search_anywhere_in_line(self) -> None:
        assert _const("_L3_FAIL_RE").search("| **FAIL** |") is not None
        assert _const("_L3_FAIL_RE").search("| FAIL |") is not None
        assert _const("_L3_FAIL_RE").search("no marker here") is None

    def test_bullet_rule_match_forms(self) -> None:
        bullet = _const("_L3_FAIL_BULLET_RE")
        assert bullet.match("- **FAIL：9**") is not None
        assert bullet.match("- FAIL：0") is not None
        assert bullet.match("**FAIL**") is not None
        assert bullet.match("- 质量门禁：0 FAIL") is None

    def test_bullet_zero_exemption_is_token_local(self) -> None:
        bullet = _const("_L3_FAIL_BULLET_RE")
        zero = _const("_L3_FAIL_ZERO_RE")

        exempt_line = "- FAIL：0"
        assert zero.match(exempt_line, _fail_token_pos(exempt_line, bullet)) is not None

        # The second token's zero must not exempt the first token's 9.
        trap_line = "- FAIL 9 项，其中 FAIL：0"
        assert zero.match(trap_line, _fail_token_pos(trap_line, bullet)) is None

    def test_prose_rule_match_forms(self) -> None:
        prose = _const("_L3_FAIL_PROSE_RE")
        assert prose.match("FAIL — 21/30 VC 通过，9 项失败") is not None
        assert prose.match("- FAIL：0") is None
        assert prose.match("FAILED") is None
