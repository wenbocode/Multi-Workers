"""L1 truth table for the cross-key repair mechanism (key ``xkey-repair-mechanism``,
task T-02; covers VC-001..006, 011, 012).

TDD contract: this file is written against the frozen public face quoted in
``.agenticdoc/xkey-repair-mechanism/plan.md`` section "契约冻结" (``autopilot/xkey.py``,
provided by T-01/W1) plus the conductor mount provided by T-03/W3.  T-01 and
T-03 have landed, so the whole file runs green with zero skips.

Discipline:
* The corpus is quoted **verbatim** from
  ``.agenticdoc/xkey-repair-mechanism/evidence/research/design-registration-carrier-20260926.md``
  section Q3 (10 shapes S-A..S-J) and
  ``.agenticdoc/xkey-repair-mechanism/evidence/research/design-boundary-apply-20260926.md``
  section Q3/Q4 (byte-exact frozen block, line-range drift); every expected
  value carries its provenance.  No shape is fabricated.
* New file only: no existing test file is modified.  The two frozen sha locks
  (``test_autopilot_verdict_source_fallback.py:66-67/:529`` and
  ``test_autopilot_verdict_freshness.py:68``) are deliberately untouched.
* Every fixture lives under ``tmp_path``; no real project tree and no
  FeatureMigrator path is read or written (AC-010 / R-6: the FM tree stays
  read-only).
* T-03 (conductor mount) has landed, so the three former T-03-dependent cases
  run for real; no ``skip``/``xfail`` marker remains in this file.  Each of the
  three emits a ``[VERIFY]`` line (visible under ``pytest -s``) for the T-07
  evidence report.

VC coverage (machine-readable, one line per VC):

# VC-001 -> test_vc001_ledger_append_is_idempotent, test_vc001_dedup_key_is_stable
# VC-002 -> test_vc002_owner_role_values_are_rejected
# VC-003 -> test_vc003_ticket_write_leaves_target_bytes_unchanged
# VC-005 -> test_vc005_boundary_positive_and_negatives
# VC-006 -> test_vc006_evidence_bundle_requires_five_items
# VC-011 -> test_vc011_key_value_shapes_field_exact
#           test_vc011_table_row_shape_s_d
#           test_vc011_prose_shapes_escalate
#           test_vc011_collect_registrations_scans_all_sources
#           test_vc011_write_side_prompt_requires_machine_line
# VC-008 -> test_vc008_switch_off_writes_no_xkey_artifacts
# VC-012 -> test_vc012_single_gate_per_pending_ticket
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from autopilot import config, conductor, gates, timeline, xkey  # noqa: E402


def _verify(tag: str, **kv: object) -> None:
    """Machine-readable checkpoint line (visible under ``pytest -s``)."""
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()))


def _state(root: pathlib.Path) -> conductor.ConductorState:
    """A fresh conductor state; the timeline seq is recovered from ``root``."""
    tl = timeline.Timeline(timeline.timeline_path(root))
    return conductor.ConductorState(tl, conductor.goal_mtime_ns(root))


# Minimal running stage so ``orchestrate`` reaches the xkey mount
# (``conductor.py:224``) instead of returning at the roadmap/stage gate.
_ROADMAP_RUNNING = (
    "# Roadmap\n"
    "> generated_at: 2026-09-10T00:00:00+00:00\n"
    "> goal_mtime: 1789000000000\n"
    "\n"
    "## Stage 1: work\n"
    "> goal: deliver\n"
    "> status: running\n"
    "> key-status: k1=running\n"
    "### Keys\n"
    "| key | role | depends_on |\n"
    "|-----|------|-----------|\n"
    "| k1 | worker | - |\n"
)


def _plant_below_round(root: pathlib.Path, key: str = "k-source") -> None:
    """One below-round provenance sidecar carrying a complete registration.

    ``_xkey_below_records`` (``conductor.py:2405``) reads exactly this shape;
    with the switch on the aggregator writes a ledger row (plus a ticket and an
    ``xkey-authorize`` gate when the owner key is terminal).
    """
    key_dir = root / ".agenticdoc" / key
    key_dir.mkdir(parents=True, exist_ok=True)
    (key_dir / "l3-verdict-provenance.json").write_text(
        json.dumps([{
            "raw_verdict": "below",
            "round": 1,
            "registration": {
                "file": "tests/test_x.py",
                "test_id": "test_a",
                "owner_key": "k-owner",
                "handoff": "registered",
                "frozen_block": None,
            },
        }]),
        encoding="utf-8",
    )


# ── corpus: 10 shapes S-A..S-J, verbatim ─────────────────────────────────────
#
# Provenance for every literal below is the research carrier
# ``design-registration-carrier-20260926.md`` section Q3, which itself quotes
# the FeatureMigrator tree (read-only).  The FM anchors re-quoted in spec §1.1
# are ``repair-r1-out-20260925-r3.txt:220``,
# ``cli-run-state-and-events/l3-report.md:17/:58`` and
# ``ap-cli-hitl-channel-l3-a1/report.md:68``.

# S-A: repair-round [VERIFY] machine line, pure key=value.
# src: design-registration-carrier-20260926.md §Q3 S-A (FM
# repair-r1-out-20260925-r3.txt:220; same payload -r2.txt:239, r1.txt:209).
CORPUS_S_A = "[VERIFY] REPAIR-R1-F1: cross_key_test=tests/test_hitl_channel.py::test_top_level_command_groups_unchanged rc=1 cli_groups=13 frozen_groups=12 owner=cli-hitl-channel handoff=registered not_fixed_by_this_key=True"

# S-B: L3-a2 report.md section-B table row (B-side decision source, embedded KV).
# src: design-registration-carrier-20260926.md §Q3 S-B (FM
# cli-run-state-and-events/workers/ap-cli-run-state-and-events-l3-a2/report.md:22).
CORPUS_S_B = "| F-1 跨 key 红 `tests/test_hitl_channel.py::test_top_level_command_groups_unchanged` | **未闭合（按设计）**：当前树复跑仍红（rc=1，`cli_groups=13` vs 该用例冻结 12），owner=`cli-hitl-channel`，挂账交接、本 key 不修（写面纪律正确） | `repair-r1-out-20260925-r3.txt:220`（`REPAIR-R1-F1: rc=1 cli_groups=13 frozen_groups=12 owner=cli-hitl-channel handoff=registered not_fixed_by_this_key=True`）+ §F-1 原始 pytest 输出 |"

# S-C: L3-a2 output.md QG-section F-1 prose line (B-side *deciding* source).
# src: design-registration-carrier-20260926.md §Q3 S-C (FM
# cli-run-state-and-events/workers/ap-cli-run-state-and-events-l3-a2/output.md, QG section).
CORPUS_S_C = "- **F-1（跨 key 红）未闭合（按设计）**：r3 实测仍红（`cli_groups=13` vs 冻结 12，r3:220）；owner=`cli-hitl-channel`，挂账交接、本 key 写面外不修，纪律正确。"

# S-D: L3-a2 report.md section-F needs-rerun N-1 row (only shape naming the frozen block).
# src: design-registration-carrier-20260926.md §Q3 S-D (FM
# cli-run-state-and-events/workers/ap-cli-run-state-and-events-l3-a2/report.md:83;
# key-level cli-run-state-and-events/l3-report.md:54).
CORPUS_S_D = "| N-1 | 跨 key 红 `tests/test_hitl_channel.py::test_top_level_command_groups_unchanged`（第 1 轮 F-1 承接） | r3（10:49Z）实测仍红（`cli_groups=13` vs 冻结 12）；owner key 的修复是否已落地，本 key 记录无法证明 | `python -X utf8 -m pytest tests/test_hitl_channel.py -k top_level_command_groups -s -q`（期望 owner 修复后绿） | **`cli-hitl-channel`**（一行修复 = `TOP_LEVEL_GROUPS` 插入 `\"runs\"`）；conductor done 事务前确认收口或显式挂账 |"

# S-E: cli-hitl-channel L3-a1 report.md K-1..K-4 prose line (A-side; fewest fields).
# src: design-registration-carrier-20260926.md §Q3 S-E (FM
# cli-hitl-channel/workers/ap-cli-hitl-channel-l3-a1/report.md:68; spec §1.1 anchor).
CORPUS_S_E = "- **K-1..K-4**（4 条已知红）：K-1 兄弟 key 新增顶层组 `runs` 致本 key PG-2 断言（12 组）红；K-2 本 key P1 的 `conftest.py` 子 env 改名（`env`→`child_env`）触发 `tests/gui_contract/paths_encoding.py` 静态匹配器 0 命中；K-3/K-4 本 key P4 的 `gate_service.write_acceptance`（design D-007.2/D-008/PG-3 明文要求）与两条既有只读源码守卫（token 扫描，连 docstring 提及 `write_text` 都判红）冲突。owner 与一行级修法均已登记（P7 §9.5 / P4 L-2/L-3/L-4；P4 明确拒绝以改名/别名绕过守卫——避免假绿，处置正确）。"

# S-F: cli-hitl-channel L3-a1 report.md leftover summary line.
# src: design-registration-carrier-20260926.md §Q3 S-F (FM
# cli-hitl-channel/workers/ap-cli-hitl-channel-l3-a1/report.md:96).
CORPUS_S_F = "- **已登记遗留**：4 条已知红 K-1..K-4（owner 在案，修复面均在本 key 白名单外）、A-1 上游 17 处格式违规（解析面 0 失效）、R-1/R-2/R-3 重冻结申请（契约 owner）、N6 一行既有形状（另立 AC）、`push` 归 Stage 3 key、口径登记类（N1/N7/N9/DEFAULT_TIMEOUT_SEC）。"

# S-G: cli-hitl-channel L3-a2 report.md NR-B row (path::test present, owner is a ROLE).
# src: design-registration-carrier-20260926.md §Q3 S-G (FM
# cli-hitl-channel/workers/ap-cli-hitl-channel-l3-a2/report.md:65;
# cli-hitl-channel/l3-report.md:58).
CORPUS_S_G = "| **NR-B** | `python -X utf8 -m pytest tests/test_hitl_channel.py::test_top_level_command_groups_unchanged`（+ 守卫网 G4 复跑） | K-1 仍红（`known_red_rc` 第 1 位 = 1，`repair-a1-evidence.txt:408` 完整失败输出在案）：第 13 个顶层组 `runs` 由兄弟 key 的未跟踪 `migrator/commands/cmd_runs.py` 引入，本 key PG-2 字面量（12 组）需 owner 更新 | 兄弟 key / PM 更新 PG-2 的 12 项字面量（或兄弟 key 撤 `runs` 组）后 |"

# S-H: gui-contract-mock-tests [VERIFY] LEFTOVER-CROSSKEY line ("Owner: conductor" role).
# src: design-registration-carrier-20260926.md §Q3 S-H (FM
# gui-contract-mock-tests/evidence/runs/repair-r1-needs-rerun-20260924.txt:730).
CORPUS_S_H = "[VERIFY] REPAIR-R1-LEFTOVER-CROSSKEY: the frozen AC-014 behaviour table entry AG-8 = tests/test_cli_json_snapshot.py is still untracked (sibling key cli-readonly-snapshot) -> a clean checkout of THIS key's face alone is red on test_gcm_forbidden_rules_and_agreement_anchors_all_resolve. Owner: conductor (commit both keys' tests/** together) or the anchor declaration (re-point AG-8, which would be a declared-face change, not a repair). Not fixable by weakening the assertion."

# S-I: gui-skeleton-shell cross_key_conflicts count (no per-red registration).
# src: design-registration-carrier-20260926.md §Q3 S-I (FM
# gui-skeleton-shell/workers/ap-gui-skeleton-shell-001-gui-deps-and-write-entries/output.md:14).
CORPUS_S_I = "**唯一天窗：`cross_key_conflicts=1`（已登记，未修）**"

# S-J: A-06 / refreeze governance prose ("red has no owner").
# src: design-registration-carrier-20260926.md §Q3 S-J (FM
# _autopilot/reflect/plan-writeface-gap.md:38).
CORPUS_S_J = "2. **红没有 owner**：plan 依赖\"下一阶段会修\"这一默认假设，而没有把红**显式指派**给任何 task；"

# Probe skeletons for the role-rejection case (VC-002).  The KV skeleton is
# S-A's; the role values are corpus-attested (see provenance strings).
_ROLE_PROBE_TEMPLATE = (
    "[VERIFY] XKEY-PROBE: "
    "cross_key_test=tests/test_hitl_channel.py::test_top_level_command_groups_unchanged "
    "owner={role} handoff=registered"
)

REGISTRATION_FIELDS = ("file", "test_id", "owner_key", "handoff", "frozen_block")


# ── synthetic project fixture (tmp_path only; never the FM tree) ─────────────

FIXTURE_TARGET_REL = "tests/test_hitl_channel.py"

# Lines 1-2 are the frozen TOP_LEVEL_GROUPS block (the byte-exact anchor);
# line 5 is the cross-key test itself (the assertion body is line 7).
FIXTURE_SOURCE = (
    'TOP_LEVEL_GROUPS = ("agent", "analyze", "branch", "config", "gate", "gui", "init",\n'
    '                    "install-hooks", "mcp", "mr", "project", "runs", "validate")\n'
    "\n"
    "\n"
    "def test_top_level_command_groups_unchanged():\n"
    '    groups = ("agent", "analyze")\n'
    '    assert tuple(groups) == TOP_LEVEL_GROUPS, f"top-level groups changed: {groups}"\n'
)

FIXTURE_TEST_ID = "test_top_level_command_groups_unchanged"
FIXTURE_BLOCK_RANGE = (1, 2)   # inclusive, 1-based (AST lineno/end_lineno)

REPLACEMENT_BLOCK = (
    'TOP_LEVEL_GROUPS = ("agent", "analyze", "branch", "config", "gate", "gui", "init",\n'
    '                    "install-hooks", "mcp", "mr", "project", "runs", "validate", "extra")\n'
).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _block_bytes(path: pathlib.Path, line_range: tuple[int, int]) -> bytes:
    lines = path.read_bytes().splitlines(keepends=True)
    start, end = line_range
    return b"".join(lines[start - 1:end])


def _project(tmp_path: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path, dict]:
    """Materialise a throw-away project root and the frozen-block descriptor.

    The descriptor is computed here (not via ``locate_frozen_block``) so the
    boundary/apply cases do not cascade off the locator's own test.
    """
    root = tmp_path / "proj"
    target = root / FIXTURE_TARGET_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(FIXTURE_SOURCE.encode("utf-8"))
    block = {
        "file": FIXTURE_TARGET_REL,
        "symbol": "TOP_LEVEL_GROUPS",
        "line_range": list(FIXTURE_BLOCK_RANGE),
        "old_block_sha256": _sha256(_block_bytes(target, FIXTURE_BLOCK_RANGE)),
    }
    return root, target, block


def _ticket(root: pathlib.Path, block: dict, *, untouchable: tuple[int, ...] = (7,),
            request_id: str = "XKEY-2026-09-26-01") -> dict:
    target = root / FIXTURE_TARGET_REL
    return {
        "request_id": request_id,
        "schema_version": 1,
        "created_by": "conductor",
        "created_at": "2026-09-26T00:00:00+00:00",
        "status": "pending-auth",
        "source_key": "cli-run-state-and-events",
        "owner_key": "cli-hitl-channel",
        "affected_keys": ["cli-run-state-and-events", "cli-hitl-channel"],
        "file": FIXTURE_TARGET_REL,
        "test_id": FIXTURE_TEST_ID,
        "frozen_block": dict(block),
        "proposed_boundary": {"file": FIXTURE_TARGET_REL, "line_range": list(block["line_range"])},
        "untouchable": [int(n) for n in untouchable],
        "authorization_snapshot": {
            "file": FIXTURE_TARGET_REL,
            "sha256": _sha256(target.read_bytes()),
        },
        "dedup_key": xkey.dedup_key(FIXTURE_TARGET_REL, FIXTURE_TEST_ID, block["old_block_sha256"]),
    }


def _proposal(file: str, line_range: tuple[int, ...], block_sha: str, new_bytes: bytes) -> dict:
    return {
        "file": file,
        "line_range": list(line_range),
        "old_block_sha256": block_sha,
        "new_bytes": new_bytes,
        "reason": "top-level group `runs` added by the source key; refresh the frozen snapshot",
    }


# ── VC-011: parse truth table (10 shapes S-A..S-J) ───────────────────────────

@pytest.mark.parametrize(
    "shape, source, expected",
    [
        pytest.param(
            "S-A",
            CORPUS_S_A,
            {
                # Field-by-field manual reading, per §Q3 S-A matrix row.
                "file": "tests/test_hitl_channel.py",
                "test_id": "test_top_level_command_groups_unchanged",
                "owner_key": "cli-hitl-channel",
                "handoff": "registered",
                # `frozen_groups=12` is a COUNT, not a block name: §Q3 S-A
                # explicitly records "抽不出块名" (the real name is in S-D).
                "frozen_block": None,
            },
            id="S-A-repair-verify-kv",
        ),
        pytest.param(
            "S-B",
            CORPUS_S_B,
            {
                # §Q3 S-B matrix row: file/test_id/owner/handoff extractable.
                "file": "tests/test_hitl_channel.py",
                "test_id": "test_top_level_command_groups_unchanged",
                "owner_key": "cli-hitl-channel",
                "handoff": "registered",
                "frozen_block": None,
            },
            id="S-B-l3-report-table-row",
        ),
    ],
)
def test_vc011_key_value_shapes_field_exact(shape: str, source: str, expected: dict) -> None:
    """VC-011: KV shapes parse with every field equal to the manual reading."""
    result = xkey.parse_registration(source)
    assert result is not None, f"{shape}: KV shape must parse, not escalate"
    for field in REGISTRATION_FIELDS:
        assert field in result, f"{shape}: registration must expose {field!r}"
    for field, value in expected.items():
        assert result.get(field) == value, f"{shape}: field {field!r}"


def test_vc011_table_row_shape_s_d() -> None:
    """VC-011: S-D (NL table row) parses; block identity is D-006's locator, not the line parser.

    §Q3 S-D matrix row marks ``frozen_block`` as human-extractable, but the
    frozen parser contract (T-01 card item 1) takes ``frozen_block`` from a
    ``frozen_block=``/``frozen=`` key only; the block is then located by
    ``locate_frozen_block`` (D-006) from ``(file, test_id)``.  So the line
    parser may either read the name here or abstain; both are contract-legal.
    """
    result = xkey.parse_registration(CORPUS_S_D)
    assert result is not None, "S-D must parse: file/test_id/owner extractable"
    assert result.get("file") == "tests/test_hitl_channel.py"
    assert result.get("test_id") == "test_top_level_command_groups_unchanged"
    assert result.get("owner_key") == "cli-hitl-channel"
    assert result.get("frozen_block") in (None, "TOP_LEVEL_GROUPS")
    # handoff is marked heuristic (⚠) for S-D in §Q3 (no `handoff=` token):
    # accept the corpus reading or an explicit abstention, never a guess.
    assert result.get("handoff") in (None, "registered")


@pytest.mark.parametrize(
    "shape, source, provenance",
    [
        pytest.param(
            "S-C", CORPUS_S_C,
            "§Q3 S-C: output.md QG F-1 line has owner but no (file,test_id)",
            id="S-C-l3-output-prose",
        ),
        pytest.param(
            "S-E", CORPUS_S_E,
            "§Q3 S-E: cli-hitl-channel l3-a1/report.md:68 K-1..K-4 prose (spec §1.1 anchor)",
            id="S-E-known-red-prose",
        ),
        pytest.param(
            "S-F", CORPUS_S_F,
            "§Q3 S-F: cli-hitl-channel l3-a1/report.md:96 leftover summary prose",
            id="S-F-leftover-summary-prose",
        ),
        pytest.param(
            "S-G", CORPUS_S_G,
            "§Q3 S-G: owner column is the ROLE `兄弟 key / PM`, never a key name",
            id="S-G-nr-b-role-owner",
        ),
        pytest.param(
            "S-H", CORPUS_S_H,
            "§Q3 S-H: `Owner: conductor` is a ROLE; no `path::test_id` pair either",
            id="S-H-leftover-crosskey-role-owner",
        ),
        pytest.param(
            "S-I", CORPUS_S_I,
            "§Q3 S-I: only `cross_key_conflicts=<n>` count, no per-red registration",
            id="S-I-conflict-count",
        ),
        pytest.param(
            "S-J", CORPUS_S_J,
            "§Q3 S-J: A-06 governance prose, `红没有 owner`, no test_id/owner_key",
            id="S-J-a06-governance-prose",
        ),
    ],
)
def test_vc011_prose_shapes_escalate(shape: str, source: str, provenance: str) -> None:
    """VC-011 / AC-002: every non-extractable shape must degrade to escalation.

    Returning ``None`` is the "no registration -> escalate only, never propose"
    contract (spec §2.3 / AC-002).  Never guess an owner.
    """
    assert xkey.parse_registration(source) is None, f"{shape} must escalate: {provenance}"


def test_vc011_collect_registrations_scans_all_sources() -> None:
    """VC-011 / D-001: the parser must scan EVERY source, not only the deciding one.

    S-C (output.md, deciding source) has only ``owner``; S-B (report.md) carries
    ``(file, test_id)``.  Reading only the deciding source would return None
    (the exact mismatch D-001 fixes).
    """
    merged = xkey.collect_registrations([
        ("workers/ap-cli-run-state-and-events-l3-a2/output.md", CORPUS_S_C),
        ("workers/ap-cli-run-state-and-events-l3-a2/report.md", CORPUS_S_B),
    ])
    assert merged is not None, "merge must span all sources (S-C + S-B)"
    assert merged.get("file") == "tests/test_hitl_channel.py"
    assert merged.get("test_id") == "test_top_level_command_groups_unchanged"
    assert merged.get("owner_key") == "cli-hitl-channel"

    assert xkey.collect_registrations([
        ("a/output.md", CORPUS_S_C),
        ("a/report.md", CORPUS_S_E),
        ("a/l3-report.md", CORPUS_S_F),
    ]) is None, "no source carries (file, test_id): escalate"


# ── VC-002: role values are never an owner key ───────────────────────────────

@pytest.mark.parametrize(
    "source, provenance",
    [
        pytest.param(
            _ROLE_PROBE_TEMPLATE.format(role="PM"),
            "role `PM` attested in §Q3 S-G (l3-a2/report.md:65)",
            id="role-pm",
        ),
        pytest.param(
            _ROLE_PROBE_TEMPLATE.format(role="conductor"),
            "role `conductor` attested in §Q3 S-H (repair-r1-needs-rerun-20260924.txt:730)",
            id="role-conductor",
        ),
        pytest.param(
            CORPUS_S_G,
            "verbatim S-G: owner column is `兄弟 key / PM` (roles, not a key)",
            id="verbatim-S-G-sibling-key-and-PM",
        ),
        pytest.param(
            CORPUS_S_H,
            "verbatim S-H: `Owner: conductor` (role, not a key)",
            id="verbatim-S-H",
        ),
    ],
)
def test_vc002_owner_role_values_are_rejected(source: str, provenance: str) -> None:
    """VC-002: ``兄弟 key`` / ``PM`` / ``conductor`` are roles -> None, never owner_key."""
    assert xkey.parse_registration(source) is None, f"role value must not become owner_key: {provenance}"


# ── VC-001: ledger idempotency + dedup-key stability ─────────────────────────

def test_vc001_ledger_append_is_idempotent(tmp_path: pathlib.Path) -> None:
    """VC-001 / AC-001: N=3 scans of one (file, test_id, block_sha) yield exactly 1 row."""
    root = tmp_path / "proj"
    root.mkdir()
    block_sha = _sha256(b'TOP_LEVEL_GROUPS = ("agent", "runs")\n')
    dedup = xkey.dedup_key(FIXTURE_TARGET_REL, FIXTURE_TEST_ID, block_sha)
    row = {
        "dedup_key": dedup,
        "source_key": "cli-run-state-and-events",
        "owner_key": "cli-hitl-channel",
        "test_id": FIXTURE_TEST_ID,
        "file": FIXTURE_TARGET_REL,
        "frozen_block": block_sha,
        "block_sha": block_sha,
        "status": "detected",
        "request_id": None,
        "history": [{"ts": "2026-09-26T00:00:00+00:00", "event": "detected", "detail": CORPUS_S_A}],
    }

    xkey.ledger_append(str(root), dict(row))
    first = xkey.ledger_load(str(root))
    assert len(first["rows"]) == 1
    assert "history" in first["rows"][0]
    history_len = len(first["rows"][0]["history"])

    for _ in range(2):  # total N = 3 scans
        xkey.ledger_append(str(root), dict(row))

    again = xkey.ledger_load(str(root))
    assert len(again["rows"]) == 1, "repeated scans must not add rows"
    assert len(again["rows"][0]["history"]) == history_len, "history must not grow on re-scan"
    assert again["rows"][0]["dedup_key"] == dedup


def test_vc001_dedup_key_is_stable() -> None:
    """VC-001 / Q8: the dedup key is a deterministic function of (file, test_id, block_sha)."""
    a = xkey.dedup_key(FIXTURE_TARGET_REL, FIXTURE_TEST_ID, "sha-1")
    b = xkey.dedup_key(FIXTURE_TARGET_REL, FIXTURE_TEST_ID, "sha-1")
    c = xkey.dedup_key(FIXTURE_TARGET_REL, FIXTURE_TEST_ID, "sha-2")
    assert isinstance(a, str) and a
    assert a == b
    assert a != c


# ── VC-003: ticket generation writes nothing to the target ───────────────────

def test_vc003_ticket_write_leaves_target_bytes_unchanged(tmp_path: pathlib.Path) -> None:
    """VC-003 / AC-003: from ticket creation until approval the target bytes are frozen."""
    root, target, block = _project(tmp_path)
    ticket = _ticket(root, block)
    before = target.read_bytes()

    path = xkey.ticket_write(str(root), ticket)
    assert path, "ticket_write must return the ticket path"
    assert pathlib.Path(path).is_file()
    assert target.read_bytes() == before, "ticket generation must not write the involved file"

    loaded = xkey.ticket_load(str(root), ticket["request_id"])
    assert loaded is not None
    assert loaded.get("request_id") == ticket["request_id"]
    assert any((t or {}).get("request_id") == ticket["request_id"]
               for t in xkey.tickets_iter(str(root)))

    assert sorted(p.name for p in target.parent.iterdir()) == [target.name], (
        "no stray files beside the involved file"
    )


# ── D-006 / D-012: frozen-block locator (byte-exact sha) ─────────────────────

def test_locate_frozen_block_resolves_symbol_and_byte_sha(tmp_path: pathlib.Path) -> None:
    """D-006/D-012: AST location returns the module constant with byte-exact sha256."""
    root, target, _ = _project(tmp_path)
    located = xkey.locate_frozen_block(str(root), FIXTURE_TARGET_REL, FIXTURE_TEST_ID)
    assert located is not None, "the fixture has exactly one module-level constant reference"
    assert located.get("file") == FIXTURE_TARGET_REL
    assert located.get("symbol") == "TOP_LEVEL_GROUPS"
    assert tuple(located.get("line_range") or ()) == FIXTURE_BLOCK_RANGE
    assert located.get("old_block_sha256") == _sha256(_block_bytes(target, FIXTURE_BLOCK_RANGE))


# ── VC-005: boundary positive / negatives (zero write, apply not called) ─────

def test_vc005_boundary_positive_and_negatives(tmp_path: pathlib.Path,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    """VC-005 / AC-005: value-only change is ok; three violations stay at zero write."""
    root, target, block = _project(tmp_path)
    ticket = _ticket(root, block, untouchable=(5, 7))
    before = target.read_bytes()

    positive = _proposal(FIXTURE_TARGET_REL, FIXTURE_BLOCK_RANGE, block["old_block_sha256"],
                         REPLACEMENT_BLOCK)
    assert xkey.check_boundary(positive, ticket) == "ok"

    calls = {"n": 0}
    real_apply = xkey.apply_block_replace

    def _counting(*args: object, **kwargs: object) -> str:
        calls["n"] += 1
        return real_apply(*args, **kwargs)

    monkeypatch.setattr(xkey, "apply_block_replace", _counting)

    negatives = {
        # 1. assertion body touched (line 7), outside the declared block.
        "assert-body": _proposal(FIXTURE_TARGET_REL, (7, 7), block["old_block_sha256"],
                                 b"    assert True\n"),
        # 2. an explicitly untouchable line is touched (line 5, the def line).
        "untouchable": _proposal(FIXTURE_TARGET_REL, (5, 5), block["old_block_sha256"],
                                 b"def test_top_level_command_groups_unchanged():\n"),
        # 3. a second file is involved.
        "second-file": _proposal("tests/other_test.py", FIXTURE_BLOCK_RANGE,
                                 block["old_block_sha256"], REPLACEMENT_BLOCK),
    }
    for name, proposal in negatives.items():
        assert xkey.check_boundary(proposal, ticket) == "violation", name

    # VC-005 "applied=0 / target_sha_unchanged=True / status!=applied".
    assert calls["n"] == 0, "check_boundary must be side-effect free on violations"
    assert target.read_bytes() == before
    assert ticket.get("status") != "applied"


# ── D-005: apply is atomic and byte-exact; D-012: sha drift aborts ───────────

def test_d005_apply_block_replace_writes_the_new_block(tmp_path: pathlib.Path) -> None:
    """D-005: a matching ticket applies the block and returns its new sha256."""
    root, target, block = _project(tmp_path)
    ticket = _ticket(root, block, untouchable=())
    before = target.read_bytes()

    new_sha = xkey.apply_block_replace(str(root), ticket, REPLACEMENT_BLOCK)
    after = target.read_bytes()
    assert b'"extra"' in after
    assert after != before, "the frozen block must actually change"

    assert isinstance(new_sha, str) and len(new_sha) == 64
    assert all(c in "0123456789abcdef" for c in new_sha)
    # plan.md fixes only the return type ("新 sha256"); the value is either the
    # new whole-file sha (AC-006 old->new) or the new block sha (re-fingerprint).
    assert new_sha in {_sha256(after), _sha256(REPLACEMENT_BLOCK)}


def test_d012_apply_block_replace_rejects_sha_drift(tmp_path: pathlib.Path) -> None:
    """D-012 / AC-005: a ticket whose recorded sha does not match disk aborts without writing."""
    root, target, block = _project(tmp_path)
    ticket = _ticket(root, block, untouchable=())
    ticket["frozen_block"]["old_block_sha256"] = "0" * 64
    before = target.read_bytes()

    with pytest.raises(Exception):
        xkey.apply_block_replace(str(root), ticket, REPLACEMENT_BLOCK)

    assert target.read_bytes() == before, "sha drift must abort before any byte is written"


# ── VC-006: evidence bundle requires all five items ──────────────────────────

# The five AC-006 items and the field spellings accepted for each.  plan.md
# freezes the SIGNATURE of ``evidence_bundle_write`` but not the bundle field
# names, so the invariant ("missing any item -> closed=False") is asserted over
# the implementation's slot names plus their aliases; a name outside this table
# would make the complete bundle incomplete and surface as a red case.
_EVIDENCE_ITEMS = (
    ("old/new sha256",
     ("old_sha256", "new_sha256", "old_sha", "new_sha",
      "old_block_sha256", "new_block_sha256")),
    ("reason",
     ("reason",)),
    ("relaxed_assertion",
     ("relaxed_assertion", "assertion_relaxed", "relaxed")),
    ("targeted rerun command + raw stdout (file must exist)",
     ("verify_cmd", "targeted_cmd", "rerun_cmd", "repro_command", "command",
      "stdout_path", "raw_stdout", "stdout", "repro_stdout", "targeted_stdout")),
    ("full-suite red before/after",
     ("red_before", "red_after", "full_red_before", "full_red_after",
      "reds_before", "reds_after", "full_suite_red_before", "full_suite_red_after")),
)


def _full_bundle(root: pathlib.Path) -> dict:
    cmd = ["python", "-X", "utf8", "-m", "pytest", FIXTURE_TARGET_REL,
           "-k", "top_level_command_groups", "-q"]
    stdout = root / "evidence" / "stdout.txt"
    stdout.parent.mkdir(parents=True, exist_ok=True)
    stdout.write_text("1 failed, 0 passed\n", encoding="utf-8")
    return {
        "old_sha256": "a" * 64, "new_sha256": "b" * 64,
        "old_sha": "a" * 64, "new_sha": "b" * 64,
        "old_block_sha256": "a" * 64, "new_block_sha256": "b" * 64,
        "reason": "source key legally added the `runs` top-level group; refresh the frozen snapshot",
        "relaxed_assertion": False, "assertion_relaxed": False,
        "verify_cmd": cmd, "targeted_cmd": list(cmd), "repro_command": list(cmd),
        "stdout_path": str(stdout), "raw_stdout": str(stdout), "repro_stdout": str(stdout),
        "red_before": 1, "red_after": 0,
        "full_suite_red_before": 1, "full_suite_red_after": 0,
    }


def _closure_record(root: pathlib.Path, request_id: str, returned: str) -> dict | None:
    candidates: list[pathlib.Path] = []
    if returned:
        path = pathlib.Path(returned)
        if not path.is_absolute():
            path = root / path
        candidates.append(path)
        if path.is_dir():
            candidates.extend(sorted(path.glob("*.json")))
    evidence_dir = root / ".agenticdoc" / "_autopilot" / "xkey" / "evidence" / request_id
    candidates.append(evidence_dir / "closure.json")
    if evidence_dir.is_dir():
        candidates.extend(sorted(evidence_dir.glob("*.json")))
    found: list[dict] = []
    for candidate in candidates:
        if candidate.is_file() and candidate.suffix == ".json":
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(data, dict):
                found.append(data)
    for record in found:
        if "closed" in record:
            return record
    for record in found:
        if "missing" in record:
            return record
    return found[0] if found else None


def _bundle_closed(root: pathlib.Path, request_id: str, bundle: dict) -> bool:
    try:
        returned = xkey.evidence_bundle_write(str(root), request_id, dict(bundle))
    except Exception:
        return False  # fail-closed: incomplete bundle must never read as closed
    record = _closure_record(root, request_id, returned)
    if record is None:
        return False
    if "closed" in record:
        return bool(record["closed"])
    if "missing" in record:
        return not list(record["missing"])
    return False


def test_vc006_evidence_bundle_requires_five_items(tmp_path: pathlib.Path) -> None:
    """VC-006 / AC-006: five items -> closed; drop any one of them -> not closed."""
    root = tmp_path
    assert _bundle_closed(root, "XKEY-2026-09-26-01", _full_bundle(root)) is True

    for index, (label, keys) in enumerate(_EVIDENCE_ITEMS):
        bundle = _full_bundle(root)
        for key in keys:
            bundle.pop(key, None)
        request_id = f"XKEY-2026-09-26-{index + 10:02d}"
        assert _bundle_closed(root, request_id, bundle) is False, f"missing {label} must not close"


# ── T-03 mount (conductor) — live, not skipped ───────────────────────────────

def test_vc012_single_gate_per_pending_ticket(tmp_path: pathlib.Path) -> None:
    """VC-012 / AC-003 / D-010: one pending ticket over N=5 ticks -> one gate.

    Drives the real aggregator mount (``conductor._xkey_aggregate``,
    ``conductor.py:2446``, spliced into ``orchestrate`` at ``conductor.py:224``)
    instead of replaying its guard: five ticks on one below registration must
    leave exactly one ``xkey-authorize`` gate.  The flood guard itself is
    ``_xkey_ensure_gate`` -> ``_gate_open(request_id=...)``
    (``conductor.py:2583`` / ``conductor.py:2157``).
    """
    root = tmp_path / "proj"
    (root / ".agenticdoc").mkdir(parents=True)
    _plant_below_round(root)
    st = _state(root)
    cfg = {
        "xkey_repair": True,
        "xkey_verify_cmd": [],
        "xkey_verify_timeout_s": 1800,
    }
    for _ in range(5):  # N = 5 ticks
        conductor._xkey_aggregate(root, st, {"k-owner": "done"}, cfg)

    gates_dir = conductor.gates_dir(root)
    gate_files = sorted(gates_dir.glob("gate-*.md"))
    assert len(gate_files) == 1, f"flood guard must keep one gate, got {gate_files}"
    pending = [g for g in gates.enumerate(gates_dir)
               if g.kind == "xkey-authorize" and g.status == "pending"]
    assert len(pending) == 1, "the single gate must be the pending xkey-authorize"
    assert len(list(xkey.tickets_iter(str(root)))) == 1, "one ticket, not one per tick"
    _verify("VC-012", gates_for_ticket=len(gate_files), ticks=5)


def test_vc008_switch_off_writes_no_xkey_artifacts(tmp_path: pathlib.Path) -> None:
    """VC-008 / AC-008: ``xkey_repair`` off -> zero xkey artifacts/events.

    The fixture is an *active* autopilot project (``enabled=True``) with one
    below-round registration on disk: with the switch on that record opens a
    ledger row, a ticket and a gate (T-03 report §3.4).  ``conductor.py:224``
    gates the whole aggregate on ``cfg["xkey_repair"]``, so the switch-off tick
    must reach ``orchestrate`` yet write nothing under ``_autopilot/xkey``.
    """
    root = tmp_path / "proj"
    (root / ".agenticdoc" / "goal.md").parent.mkdir(parents=True)
    (root / ".agenticdoc" / "goal.md").write_text("# Goal\n", encoding="utf-8")
    cfg = config.default_config()
    cfg["enabled"] = True
    cfg["xkey_repair"] = False
    config.save_config(root, cfg)
    (root / ".agenticdoc" / "_autopilot" / "_roadmap.md").write_text(
        _ROADMAP_RUNNING, encoding="utf-8"
    )
    _plant_below_round(root)

    assert config.cached_load(root).get("xkey_repair", False) is False
    status = conductor.tick(root, _state(root))
    assert status == "ok", "tick must reach orchestrate, not die before the gate"
    assert not (root / ".agenticdoc" / "_autopilot" / "xkey").exists()
    events = timeline.query_events(timeline.timeline_path(root)).events
    xkey_events = [e for e in events if str(e.get("ev", "")).startswith("xkey-")]
    assert xkey_events == [], f"switch off must emit zero xkey events: {xkey_events}"
    _verify("VC-008", xkey_artifacts=0, xkey_events=len(xkey_events))


def test_vc011_write_side_prompt_requires_machine_line() -> None:
    """VC-011 write half / D-001: the L3 prompt must require the S-A machine line
    *inside* the mandatory ``## Quality Gate Report`` section (not an appendix).

    The prompt is built by ``conductor._l3_prompt`` (``conductor.py:1138``, the
    only construction point); the line lands in the mandatory-section bullet, so
    the reviewer's deciding source carries it where the parser scans (D-001).
    """
    prompt = conductor._l3_prompt("k1", 1)
    qg_start = prompt.find("## Quality Gate Report")
    achieved_start = prompt.find("## Achieved")
    assert qg_start != -1 and achieved_start != -1, "both mandatory sections must exist"
    section = prompt[qg_start:achieved_start]

    for token in ("cross_key_test=", "owner=", "handoff=registered",
                  "not_fixed_by_this_key=True"):
        assert token in prompt, f"machine line contract missing {token!r}"
        assert token in section, (
            f"{token!r} must sit inside ## Quality Gate Report, not an appendix"
        )
    _verify("VC-011-write", machine_line_in_prompt=True, in_mandatory_section=True)
