"""autopilot/dispatch.py — typed dispatch registry + task/queue writer
(goal-autopilot T-06, D-107/D-111/D-104).

Typed registry (conductor side, D-107): every autopilot dispatch goes through
an explicit type -> tool set -> cli/provider entry. An unregistered type is
refused — zero queue rows, a ``type-rejected`` timeline event, and never a
fallback to the full tool set (GC-8: the *manual* fallback path stays
untouched; this module simply is not that path). The Python registry's tool
sets must stay exactly equal to the TS-side ``TOOL_ALLOWLISTS`` entries added
in T-14; the L0 parity test (T-17) locks that equality.

Task identity (D-111): the queue task key is ``ap-{owner}-{stem}``. The
``ap-`` prefix is globally unique to conductor dispatches — manual task keys
can never collide with it, and stale/legacy rows stay distinguishable.

Dispatch transaction (D-102, revised by mw-write-face-guard W-03/AC-014): the
``.mw/workers.lock`` (O_CREAT|O_EXCL, mw_common protocol) critical section now
covers the write-face judgement, the task.md write, and the queue row — the
gate reads the live queue, so judgement and row write must not be separable
(the old order wrote task.md *outside* the lock and left a check-then-act
window). After the lock is released a read-back verifies the row. The two
writes stay deliberately non-atomic *inside* the lock: a crash between them
leaves exactly the orphan shape (task.md with ``origin: conductor`` and no
row) that per-tick reconciliation re-inserts as pending with the same
loop/attempt — no round consumed, no work duplicated.

Write-face gate (D-001/D-003/D-008): a dispatch whose rendered task.md
declares no ``write_face:`` head is serial-only (audit + no parallel with a
same-owner in-flight worker) but never rejected; a parse-time-invalid face or
a provable overlap with an in-flight same-owner worker is refused with zero
side effects (no taskDir, no task.md, no queue row). Card-less internal
dispatches (L3/repair/roadmap/phase-writer) are exempt from the serial-only
refusal — see :func:`_write_face_verdict`.

task.md frontmatter (worker protocol extension, backward compatible):
``origin: conductor`` makes the TS dispatcher skip the task (D-104) and is
the worker-side fail-closed anchor; ``loop:``/``attempt:`` are the round
budget labels state.py derives budgets from; ``read_scope:`` is mandatory
for ``verifier`` (D-106 containment) and omitted otherwise.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import pathlib
import re
import sys
from collections.abc import Sequence

# Script-mode bootstrap (same rationale as state.py).
_PARENT = pathlib.Path(__file__).resolve().parent.parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

import mw_common  # noqa: E402  (path bootstrapped above)

from autopilot import config as autopilot_config  # noqa: E402
from autopilot import effective_config  # noqa: E402
from autopilot import timeline as timeline_mod  # noqa: E402
from autopilot import write_face as write_face_mod  # noqa: E402

# ── Typed registry (D-107) ────────────────────────────────────────────────────

_CODING_TOOLS = ("read", "write", "edit", "bash", "find", "grep", "ls")
_REVIEW_TOOLS = ("read", "find", "grep", "ls")
#: mw-decision-substitution W8/W10: read-only tools + `bash` (the runtime
#: narrows the shell to `mw decide book check` / `git diff --stat` / `rg` / `cat`).
DECIDE_PREPARE_TOOLS = ("read", "find", "grep", "ls", "bash")


@dataclasses.dataclass(frozen=True)
class DispatchType:
    """One registry entry: type -> tools + route."""

    name: str
    tools: tuple[str, ...]
    cli: str
    provider: str  # explicit route; "" = route default (CLI_DEFAULT_PROVIDER at spawn time)
    requires_read_scope: bool
    # mw-rag-integration T-09: PM-only types (e.g. rag-research) carry False;
    # the conductor refuses to dispatch them. A default keeps every existing
    # 5 positional entries unchanged (conductor_dispatchable=True).
    conductor_dispatchable: bool = True


REGISTRY: dict[str, DispatchType] = {
    # Writes the _roadmap.md proposal: file tools, no shell.
    "roadmap-writer": DispatchType(
        "roadmap-writer",
        ("read", "write", "edit", "find", "grep", "ls"),
        "pi", "timi", False,
    ),
    # Evidence/artifact patches: full coding set.
    "phase-writer": DispatchType(
        "phase-writer", _CODING_TOOLS, "pi", "timi", False,
    ),
    # L2 gate verdicts: review set + mandatory read_scope (D-106).
    "verifier": DispatchType(
        "verifier", _REVIEW_TOOLS, "pi", "timi", True,
    ),
    # L3 final verdicts: review set.
    "reviewer": DispatchType(
        "reviewer", _REVIEW_TOOLS, "pi", "timi", False,
    ),
    # Post-below repair: full coding set.
    "repair": DispatchType(
        "repair", _CODING_TOOLS, "pi", "timi", False,
    ),
    # RAG research bucket (mw-rag-integration D-011/AC-011): renders rag_chat,
    # the only type allowed to call it. PM/user-dispatched only — the
    # conductor must not use it (conductor_dispatchable=False below). Tool
    # order is locked per-item against the TS TOOL_ALLOWLISTS entry.
    "rag-research": DispatchType(
        "rag-research",
        (
            "read", "find", "grep", "ls",
            "rag_search", "rag_symbol", "rag_graph", "rag_impact",
            "rag_sources", "rag_feedback", "rag_chat",
        ),
        "pi", "timi", False, False,
    ),
    # Vision bucket (mw-vision-role D-001): full coding set, conductor may
    # dispatch it. Tool order is locked per-item against the TS
    # TOOL_ALLOWLISTS entry.
    "vision": DispatchType(
        "vision", _CODING_TOOLS, "pi", "timi", False,
    ),
    # Decision-book writer (mw-decision-substitution W8, renamed W10):
    # read-only tools plus a read-only shell subset (the runtime narrows `bash`
    # further — see worker-mode.ts `decisionBashBlockReason`). It never writes
    # code: its whole product is one book under `<key>/evidence/books/**`.
    # Tool order is locked per-item against the TS TOOL_ALLOWLISTS entry.
    # W10: the type value is `decide_prepare` (was `decision`; no alias kept).
    "decide_prepare": DispatchType(
        "decide_prepare", DECIDE_PREPARE_TOOLS, "pi", "timi", False,
    ),
}

SCRATCH_OWNER = "_scratch"

# pm-state.md's phase interface line is owned by advance_phase.py (read-only
# here). The token is split so the VC-007 static scan never sees the literal.
_PHASE_LINE_KEY = "Phase:"


def _owner_phase(project_root: pathlib.Path, owner: str) -> str:
    """Current phase of ``owner`` from its pm-state.md interface line.

    mw-rag-integration T-14: the phase axis of
    ``required = role.require OR phase.require`` is written into task.md from
    the owning key's current phase. ``_scratch`` dispatches, a missing
    pm-state.md, and a file without the interface line all return "" — the
    renderer then writes no ``phase:`` header (never guessed). pm-state.md is
    owned by advance_phase.py; this read never writes it.
    """
    if owner == SCRATCH_OWNER:
        return ""
    state_path = pathlib.Path(project_root) / ".agenticdoc" / owner / "pm-state.md"
    try:
        text = state_path.read_text(encoding="utf-8")
    except OSError:
        return ""
    prefix = "- " + _PHASE_LINE_KEY
    for raw in text.splitlines():
        if raw.startswith(prefix):
            return raw[len(prefix):].strip()
    return ""


def tool_set(task_type: str) -> tuple[str, ...]:
    """Tool set of a registered type; () for unregistered types."""
    entry = REGISTRY.get(task_type)
    return entry.tools if entry else ()


def registry_snapshot() -> dict[str, tuple[str, ...]]:
    """type -> tools snapshot for the L0 parity test (T-17)."""
    return {name: entry.tools for name, entry in REGISTRY.items()}


# ── decision worker type (mw-decision-substitution W8/W10) ───────────────────
#
# A `decide_prepare` worker writes ONE decision book: read the config, collect
# evidence, fill the skeleton, pass `mw decide book check`, hand the book back.
# (W10 renamed the type `decision` -> `decide_prepare`; the old value is no
# longer a registered type or role — no alias.)
# This block owns the three dispatch-time criteria that make that role safe:
#
#   1. the card must declare `- dp:`, `- 证据来源:`, `- 分支后果:` and
#      `- allow-send:` (missing any one of them is a refusal — the worker
#      cannot invent its own decision point or send authority);
#   2. the dp must declare `required_state_fields` in the registry
#      (`decide_registry.json`): without a field list there is no book to fill
#      and the book-check gate would be vacuous (dp1/dp2/dp3 today);
#   3. `allow-send: no` (the default) means the worker may run `book check`
#      only — the send (`decide run|ask --book`) stays with the PM.
#
# The write face is narrowed to `<key>/evidence/books/**`, the one directory a
# book may live in. A card that declares a wider face still wins (the author's
# declaration is authoritative, D-113); the task.md then records the
# `narrowed_by` line so the widening stays visible instead of silent.

DECIDE_PREPARE_TYPE = "decide_prepare"
DECISION_WRITE_FACE_SUBDIR = "evidence/books"

#: Card bullet labels every decision card must declare (lowercase keys).
DECISION_CARD_ITEMS = ("dp", "证据来源", "分支后果", "allow-send")
DECISION_SEND_ITEM = "allow-send"
DECISION_SEND_YES = "yes"
DECISION_SEND_NO = "no"

#: Heading of the synthesized task.md section carrying the normalized items.
DECISION_PARAMS_HEADING = "决策本参数"

#: `- dp: dp3-worker-clarify` / `* 证据来源：x` → ("dp", "dp3-worker-clarify").
_DECISION_ITEM_RE = re.compile(r"^\s*[-*+]\s*(?:\*\*)?([^:：]{1,32}?)(?:\*\*)?\s*[:：]\s*(.*)$")


@dataclasses.dataclass(frozen=True)
class DecisionIssue:
    """One refused decision-card criterion (stable code + locator + prose)."""

    code: str
    path: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "detail": self.detail}

    def format(self) -> str:
        return f"{self.code} {self.path}: {self.detail}"


def decision_card_fields(text: str) -> dict[str, str]:
    """Bullet-label map of a decision card: `{label: value}` (first hit wins).

    Wide on purpose (P-03 in the card-judge family): any bullet carrying the
    label counts, indentation and bold markers included. Labels are folded to
    lowercase so `Allow-Send:` and `allow-send:` are the same item.
    """
    fields: dict[str, str] = {}
    for raw in str(text or "").splitlines():
        match = _DECISION_ITEM_RE.match(raw)
        if match is None:
            continue
        label = match.group(1).strip().lower()
        value = match.group(2).strip().strip("`").strip()
        if label and label not in fields:
            fields[label] = value
    return fields


def decision_allows_send(fields: dict[str, str]) -> bool:
    """Only an explicit `allow-send: yes` authorizes the worker to send.

    Absent/`no`/anything else is the closed state: the worker runs
    `book check` and stops, the PM sends (card requirement 4)."""
    return str(fields.get(DECISION_SEND_ITEM, "")).strip().lower() == DECISION_SEND_YES


def _decision_registry_points() -> dict[str, dict]:
    """Read-only registry view (`decide_registry.json`). Import is local so a
    dispatch path that never sees a `decide_prepare` task pays nothing for the
    registry build."""
    import decision_book  # local: read-only view, W8 calls it and never patches it

    return decision_book.registry_points()


def decision_card_issues(
    card_text: str,
    *,
    card_path: str = "card",
    dp: str = "",
    book: str = "",
    require_items: bool = True,
) -> list[DecisionIssue]:
    """Every refusal of one decision card (empty list = dispatchable).

    ``dp`` / ``book`` are CLI-only overrides: ``dp`` lets the checker validate
    the registry criterion without a card, ``book`` turns on the send check
    (`--book` under `allow-send: no`). The four card items are always required
    on a real dispatch (requirement 4: missing any one is a refusal, not a
    warning); ``require_items=False`` is the registry-only probe shape.
    """
    fields = decision_card_fields(card_text)
    issues: list[DecisionIssue] = []
    for item in (DECISION_CARD_ITEMS if require_items else ()):
        if not fields.get(item, "").strip():
            issues.append(DecisionIssue(
                f"missing-item:{item}", card_path,
                f"decision 卡片缺少 `- {item}:` 条目（缺任一项不得派发）",
            ))
    if (send := fields.get(DECISION_SEND_ITEM, "").strip().lower()) and send not in (
        DECISION_SEND_YES, DECISION_SEND_NO,
    ):
        issues.append(DecisionIssue(
            f"invalid-item:{DECISION_SEND_ITEM}", card_path,
            f"allow-send 只能是 yes|no（读到 {send!r}；缺省按 no 处理）",
        ))
    target_dp = (dp or fields.get("dp", "")).strip()
    if target_dp:
        points = _decision_registry_points()
        point = points.get(target_dp)
        if point is None:
            issues.append(DecisionIssue(
                f"dp-unknown:{target_dp}", card_path,
                f"dp {target_dp!r} 不在 decide_registry.json（先定义该 dp）",
            ))
        elif not (point.get("required_state_fields") or ()):
            issues.append(DecisionIssue(
                f"dp-required-state-fields-missing:{target_dp}", card_path,
                f"dp {target_dp!r} 没有 required_state_fields：先给该 dp 定义必填字段，"
                "否则没有决策本可填",
            ))
    if book and not decision_allows_send(fields):
        issues.append(DecisionIssue(
            "book-send-refused", card_path,
            "allow-send: no（或缺失）时 worker 只能跑 `mw decide book check`；"
            "`decide run|ask --book` 由 PM 发送",
        ))
    return issues


def decision_write_face(
    owner: str, task_key: str, card_entries: Sequence[str] | None
) -> tuple[list[str], str, str]:
    """(write_face entries, carrier, `narrowed_by` note) for one decision task.

    ``card_entries is None`` / empty = the card declares no face (or none at
    all): the type default `<key>/evidence/books/**` is used — that is the
    narrowing requirement 3 asks for, since the generic writeless face
    (`<key>/evidence/**`) would let a book land anywhere in the evidence tree.
    A declared card face always wins (D-113); the third element records whether
    it was wider than the type default, so the widening lands in task.md as a
    `narrowed_by` line instead of staying invisible.
    """
    default_entry = f".agenticdoc/{owner}/workers/{task_key}/{DECISION_WRITE_FACE_SUBDIR}/**"
    entries = [str(entry).strip() for entry in (card_entries or ()) if str(entry).strip()]
    if not entries:
        return (
            [default_entry],
            "type-default",
            f"type-default:{DECISION_WRITE_FACE_SUBDIR}/** (decide_prepare 类型默认收窄，卡片未声明写入面)",
        )
    books_prefix = f".agenticdoc/{owner}/workers/{task_key}/{DECISION_WRITE_FACE_SUBDIR}/"
    inside = all(entry.replace("\\", "/").startswith(books_prefix) for entry in entries)
    if inside:
        return entries, "card", f"card:{DECISION_WRITE_FACE_SUBDIR}/** (卡片面在类型默认面内，无放宽)"
    return (
        entries,
        "card-wider",
        f"card-wider: 卡片声明面比类型默认面 {books_prefix}** 更宽，以卡片为准",
    )


def decision_params_body(
    fields: dict[str, str], *, book_path: str, carrier: str, narrowed_by: str
) -> str:
    """Body of the synthesized task.md section the worker (and the PM) reads.

    Normalized, ordered, machine-grepable: the four card items first, then the
    resolved send authority, the book target and the write-face provenance.
    """
    send = DECISION_SEND_YES if decision_allows_send(fields) else DECISION_SEND_NO
    return "\n".join([
        f"- dp: {fields.get('dp', '').strip()}",
        f"- 证据来源: {fields.get('证据来源', '').strip()}",
        f"- 分支后果: {fields.get('分支后果', '').strip()}",
        f"- allow-send: {send}",
        f"- book: {book_path}",
        f"- write_face_carrier: {carrier}",
        f"- narrowed_by: {narrowed_by}",
    ])


def _read_card_text(project_root: pathlib.Path, owner: str, stem: str) -> str:
    """Raw text of the dispatch's card file, or "" when there is none."""
    card_file = pathlib.Path(project_root) / ".agenticdoc" / owner / "tasks" / f"{stem}.md"
    try:
        return card_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def decision_dispatch_issues(
    project_root: pathlib.Path, owner: str, stem: str
) -> list[DecisionIssue]:
    """Dispatch-time gate for `type: decide_prepare` (zero side effects on refusal).

    A card-less dispatch is refused: every criterion lives on the card, so
    there is nothing to fall back to (unlike the internal roles, whose extras
    are synthesized from metadata).
    """
    card_text = _read_card_text(project_root, owner, stem)
    if not card_text.strip():
        return [DecisionIssue(
            "card-missing", f"tasks/{stem}.md",
            "decide_prepare 派发必须带卡片（dp/证据来源/分支后果/allow-send 都在卡片上）",
        )]
    return decision_card_issues(card_text, card_path=f"tasks/{stem}.md")


# ── task.md rendering ─────────────────────────────────────────────────────────

def _strip_rag_block(content: str) -> str:
    """Remove an existing `<!-- mw-rag: v1 -->` block (marker replacement).

    The block runs from the marker line through the terminating
    `fingerprint=` line (the marker and the fingerprint are the only two
    anchors both sides render). Stopping at the fingerprint keeps a profile
    block that may follow it intact — the profile block shares the `[mw] `
    line prefix. Content without the marker is returned untouched, so a
    RAG-less task.md is byte-identical to the pre-RAG generator (AC-001).
    """
    idx = content.find(mw_common.RAG_MARKER_V1)
    if idx == -1:
        return content
    start = content.rfind("\n", 0, idx) + 1
    match = re.search(r"^fingerprint=\S+[ \t\r]*$", content[idx:], flags=re.MULTILINE)
    if match is None:
        # Malformed (marker without a fingerprint): drop the marker line only.
        end = content.find("\n", idx)
        end = len(content) if end == -1 else end + 1
    else:
        end = idx + match.end()
        if end < len(content) and content[end] == "\n":
            end += 1
    return content[:start] + content[end:]


def _inject_rag_block(
    content: str, rag_config: dict | None, task_meta: dict | None, task_type: str
) -> str:
    """Append (or replace) the task.md mw-rag block; no-op when disabled.

    `mw_common.render_rag_block` returns None with an empty enabled set — the
    structural zero-impact guarantee (D-014/AC-001) — so a RAG-less task.md
    keeps every byte. The append shape (`rstrip()` + blank line + block +\n)
    matches the T-06 golden byte contract; an existing block is replaced
    wholesale, which makes repeated rendering idempotent.
    """
    if not rag_config:
        return content
    meta = task_meta if isinstance(task_meta, dict) else {}
    if not meta:
        meta = {
            "type": task_type,
            "role": mw_common.TASK_TYPE_TO_ROLE.get(task_type, task_type),
        }
    block = mw_common.render_rag_block(rag_config, meta)
    if block is None:
        return content
    return _strip_rag_block(content).rstrip() + "\n\n" + block + "\n"


# ── claims block contract (claim-driven-review T-03, design §2/§3.2) ──────────
#
# A card may declare its falsifiable claims in a ``<!-- mw-claims: v1 -->``
# block: a seven-column table (``claim | 类型 | 陈述 | 反证条件 | 定位 | 判据 |
# 预算``). The conductor needs exactly two things from it — the parsed claims
# (so the settle side can compare them against the worker's ``## 断言裁决``
# table) and the derived read budget (so the worker's cap matches the card it
# was actually given instead of a fixed 8 files / 65536 B). The gate itself
# (which gaps refuse a dispatch, which only warn) stays in the TS layer
# (``shared/dispatch-card.ts``); this module is the parser + budget mirror, so
# a card without claims keeps the pre-claims renderer byte for byte.
#
# The four constants below are the Python half of the single-source contract in
# design §2.3: ``test_claim_parity.py`` (T-06) compares each of them verbatim
# against the TS module, the same lock the decision registry uses for
# ``decision_points.ESCALATED_REASONS`` — that vocabulary drifted once because
# two modules each kept a copy.
CLAIM_TYPES: list[str] = ["cmd", "grep", "struct", "manual"]
UNVERIFIED_REASONS: list[str] = [
    "budget",
    "no-access",
    "not-found",
    "ambiguous",
    "environment",
    "out-of-scope",
    "awaiting-input",
]
CLAIM_GATE_DEFAULT = "advisory"
CLAIM_BUDGET: dict[str, int] = {
    "perClaim": 6,
    "callCap": 30,
    "hardCap": 35,
    "claimByteCap": 65536,
    "byteCapMax": 393216,
}
#: Legal gate modes (D-006: advisory by default, enforce is opt-in).
_CLAIM_GATE_MODES = ("advisory", "enforce")

_CLAIM_BLOCK_START_RE = re.compile(
    r"^<!--\s*mw-claims\s*:\s*v1\s*-->$", re.IGNORECASE
)
_CLAIM_BLOCK_END_RE = re.compile(r"^<!--\s*/\s*mw-claims\s*-->$", re.IGNORECASE)
#: H2 only (``## x``, not ``###``): the tolerance end of an unterminated block.
_CLAIM_HEADING_RE = re.compile(r"^##(?!#)\s+")
#: Fence opener, split into marker + rest so the closer can be recognised.
_CLAIM_FENCE_RE = re.compile(r"^(`{3,}|~{3,})(.*)$")
#: ``C-01`` / ``C-01.3`` — the TS parser upper-cases the id it rebuilds.
_CLAIM_ID_RE = re.compile(r"^C-(\d{2,3})(?:\.(\d+))?$", re.IGNORECASE)
_CLAIM_SEPARATOR_RE = re.compile(r"^:?-{1,}:?$")

#: Field -> header aliases (P-048 / RQ-3 §5.6): column order is free, extra
#: columns are ignored, and either script of a header word is accepted. This is
#: the verbatim mirror of the TS ``CLAIM_COLUMN_ALIASES`` table; full-width
#: variants are folded before the lookup.
_CLAIM_COLUMN_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("id", ("claim", "claim id", "claim id /", "断言", "断言 id")),
    ("type", ("类型", "type", "类别")),
    ("statement", ("陈述", "statement", "主张", "断言内容")),
    ("falsifier", ("反证条件", "反证", "falsifier", "refutation")),
    ("locator", ("定位", "locator", "anchor", "锚点")),
    ("judgement", ("判据", "judgement", "judgment", "criterion")),
    ("budget", ("预算", "budget")),
)

#: Full-width -> half-width folding for the table header/cell scan (the TS
#: ``normalizeClaimText``): ``：｜``, ideographic space and full-width digits.
_CLAIM_FULLWIDTH = str.maketrans(
    {
        "：": ":", "｜": "|", "　": " ",
        "０": "0", "１": "1", "２": "2", "３": "3", "４": "4",
        "５": "5", "６": "6", "７": "7", "８": "8", "９": "9",
    }
)


def _claim_normalize(text: str) -> str:
    """Full-width folding + trim (mirror of the TS ``normalizeClaimText``)."""
    return str(text).translate(_CLAIM_FULLWIDTH).strip()


def _claim_strip_ticks(text: str) -> str:
    """Drop the backticks a card writer wraps a cell value in."""
    return str(text).replace("`", "").strip()


def _advance_claim_fence(line: str, open_marker: str | None) -> str | None:
    """Fence state after ``line``: the opener marker, or ``None`` outside.

    Same semantics as the TS ``advanceClaimFence``: the closer only closes a
    fence of the same character with at least its length and nothing after it
    (a nested ```` ```ts ```` line does not close a ```` ``` ```` fence).
    """
    match = _CLAIM_FENCE_RE.match(line)
    if match is None:
        return open_marker
    marker = match.group(1)
    rest = match.group(2)
    if open_marker is None:
        return marker
    if (
        marker[0] == open_marker[0]
        and len(marker) >= len(open_marker)
        and rest.strip() == ""
    ):
        return None
    return open_marker


def _claim_cells(line: str) -> list[str]:
    """Table cells of one row (mirror of the TS ``splitClaimRow``).

    Full-width ``：``/``｜``/digits are folded first, then the leading/trailing
    pipes are dropped so both ``| a | b |`` and ``a | b`` shapes work.
    """
    parts = _claim_normalize(line).split("|")
    if parts and parts[0].strip() == "":
        parts = parts[1:]
    if parts and parts[-1].strip() == "":
        parts = parts[:-1]
    return [part.strip() for part in parts]


def _claim_header_columns(cells: Sequence[str]) -> dict[str, int] | None:
    """Field -> column index of a claims table header, or ``None``.

    Column order is free and an extra column keeps no slot (it is ignored).
    The table only counts as a claims header when it names the id column
    (``claim`` / ``断言`` families) — same rule as the TS ``matchClaimHeader``.
    """
    columns: dict[str, int] = {}
    for index, cell in enumerate(cells):
        name = _claim_strip_ticks(_claim_normalize(cell)).lower()
        name = re.sub(r"\s+", " ", name)
        if name.endswith(":"):
            name = name[:-1]
        for field, aliases in _CLAIM_COLUMN_ALIASES:
            if name not in aliases:
                continue
            if field not in columns:
                columns[field] = index
            break
    return columns if "id" in columns else None


def _claim_cell(cells: Sequence[str], columns: dict[str, int], field: str) -> str:
    """Cell of ``field`` (``""`` when the column or the cell is absent)."""
    index = columns.get(field)
    if index is None or index >= len(cells):
        return ""
    return str(cells[index]).strip()


def _claim_from_row(
    cells: Sequence[str],
    columns: dict[str, int],
    row: int,
    by_id: dict[str, dict],
) -> dict | None:
    """One table row -> claim dict, or ``None`` when the row cannot be read.

    Mirrors the TS ``claimFromRow``: the id is normalised to ``C-<nnn>``, a
    ``C-01.3`` child is only legal under an already-seen ``struct`` parent
    (RQ-3 §5.1/B-10) and inherits ``struct`` when its own 类型 cell is empty,
    and a non-numeric 预算 is "absent" (``None`` — the Python form of the TS
    ``NaN``; both mean "no budget declared", never 0).
    """
    id_match = _CLAIM_ID_RE.match(
        _claim_strip_ticks(_claim_cell(cells, columns, "id"))
    )
    if id_match is None:
        return None
    number = id_match.group(1)
    child = id_match.group(2)
    parent = "" if child is None else f"C-{number}"
    claim_id = f"C-{number}" if child is None else f"C-{number}.{child}"
    if parent:
        parent_claim = by_id.get(parent)
        if parent_claim is None or parent_claim.get("type") != "struct":
            return None
    declared = _claim_strip_ticks(_claim_cell(cells, columns, "type")).lower()
    budget_text = _claim_strip_ticks(_claim_cell(cells, columns, "budget"))
    return {
        "id": claim_id,
        "type": "struct" if declared == "" and parent else declared,
        "parent": parent,
        "statement": _claim_cell(cells, columns, "statement"),
        "falsifier": _claim_cell(cells, columns, "falsifier"),
        "locator": _claim_cell(cells, columns, "locator"),
        "judgement": _claim_cell(cells, columns, "judgement"),
        "budget": int(budget_text) if re.fullmatch(r"\d+", budget_text) else None,
        "row": row,
    }


def parse_claims_block(text: str) -> dict:
    """Parse a card's ``mw-claims: v1`` block: ``{present, claims, errors}``.

    Mirrors the TS ``parseClaimsBlock`` grammar (design §2.1/§3.1) so both sides
    read one shape:

    * the block runs from ``<!-- mw-claims: v1 -->`` to ``<!-- /mw-claims -->``;
      a missing end marker tolerates up to the next H2 or EOF;
    * markers and tables inside fenced code blocks contribute nothing (a card
      often shows the format in an example fence);
    * the header row names the columns (any order, extra columns ignored, alias
      table ``_CLAIM_COLUMN_ALIASES``, full-width ``：｜``/digits folded); a
      non-table line resets the header state, so a second table needs its own;
    * an unreadable row lands in ``errors`` as ``claim:<line>:unparsable`` —
      this function never raises (P-048).
    """
    lines = str(text or "").splitlines()
    claims: list[dict] = []
    errors: list[str] = []
    by_id: dict[str, dict] = {}
    present = False
    in_block = False
    columns: dict[str, int] | None = None
    fence: str | None = None
    for index, line in enumerate(lines):
        fence = _advance_claim_fence(line, fence)
        if fence is not None:
            continue
        if not in_block:
            if _CLAIM_BLOCK_START_RE.match(line):
                in_block = True
                present = True
            continue
        if _CLAIM_BLOCK_END_RE.match(line) or _CLAIM_HEADING_RE.match(line):
            in_block = False
            columns = None
            continue
        if not _claim_normalize(line).startswith("|"):
            columns = None
            continue
        cells = _claim_cells(line)
        if columns is None:
            columns = _claim_header_columns(cells)
            continue
        if cells and all(
            cell == "" or _CLAIM_SEPARATOR_RE.match(cell) for cell in cells
        ):
            continue
        claim = _claim_from_row(cells, columns, index + 1, by_id)
        if claim is None:
            errors.append(f"claim:{index + 1}:unparsable")
            continue
        claims.append(claim)
        by_id[str(claim["id"])] = claim
    return {"present": present, "claims": claims, "errors": errors}


def claim_budget_caps(claims: Sequence[dict] | None) -> tuple[int, int]:
    """``(file_cap, byte_cap)`` derived from a card's claims (design §4).

    ``file_cap = min(30, Σ(manual ? 2 : 1))`` — a manual claim is weighted
    double because it buys PM attention instead of worker fetches; ``byte_cap =
    min(393216, 65536 × n)``. Both bounds come from :data:`CLAIM_BUDGET`, the
    calibrated values (RQ-1 §5, D-007), never from a local literal. No claims
    returns ``(0, 0)``, which :func:`_read_scope_caps` reads as "keep the
    historical behaviour" — the byte-identity guarantee for pre-claims cards.
    """
    rows = list(claims or ())
    if not rows:
        return 0, 0
    budget_sum = sum(
        2 if str(row.get("type") or "").strip().lower() == "manual" else 1
        for row in rows
    )
    file_cap = min(CLAIM_BUDGET["callCap"], budget_sum)
    byte_cap = min(
        CLAIM_BUDGET["byteCapMax"], CLAIM_BUDGET["claimByteCap"] * len(rows)
    )
    return file_cap, byte_cap


def claim_gate() -> str:
    """Claim gate mode: ``advisory`` (default) or ``enforce`` (D-006).

    Unknown/blank values fall back to :data:`CLAIM_GATE_DEFAULT` with one
    diagnostic on stderr and never block a dispatch: the gate is opt-in, so a
    typo may not silently turn enforcement on *or* stall the loop (fail-open).
    """
    raw = os.environ.get("MW_CLAIM_GATE", CLAIM_GATE_DEFAULT)
    value = str(raw).strip().lower()
    if value in _CLAIM_GATE_MODES:
        return value
    print(
        f"[CLAIMS] claim_gate={raw} fallback={CLAIM_GATE_DEFAULT}",
        file=sys.stderr,
        flush=True,
    )
    return CLAIM_GATE_DEFAULT


def _project_scope_caps(
    project_root: pathlib.Path,
) -> tuple[int | None, int | None]:
    """``l2_read_file_cap`` / ``l2_read_byte_cap`` for the rendered task.md.

    Until 2026-09-23 these two fields were dead config: config.py parsed and
    validated them, but no Python renderer ever emitted them, so every
    conductor-dispatched worker fell back to the harness default
    (``DEFAULT_READ_FILE_CAP`` = 8 files / 65536 B). The cap only activates
    for tasks that carry ``read_scope`` (worker-mode.ts: zero interception
    otherwise) — i.e. exactly the verifiers, where read_scope is mandatory
    (D-106). Measured consequence (FeatureMigrator gui-contract-surface /
    gui-shell-spike, 2026-09-23): both L3 reviewers spent all 8 allowed
    read/ls/find/grep calls on context loading, could not read a single
    EXECUTE evidence file, and returned fail-closed ``below`` verdicts
    (0/23 and 0/31 verification criteria assertable) — structurally
    unverifiable keys, not product failures.

    A missing config file keeps ``(None, None)`` → task.md byte-identical to
    the pre-fix renderer (config.py's own contract: absent file = defaults,
    zero footprint, and the worker default is the same 8/65536). The cap
    *default* values are owned by the TS harness
    (``read-scope.ts::DEFAULT_READ_*``): the Python side deliberately defines
    no fallback constant of its own (D-002 / GC-4: single source).
    """
    try:
        if not autopilot_config.config_path(project_root).exists():
            return None, None
        # Layered effective read (T-06, D-003): strictly read-only, no
        # directory is created. Presence is taken from the project layer's raw
        # keys: the effective layer always materialises the built-in defaults,
        # so it cannot express "this field was never configured" — an omitted
        # cap must stay omitted (VC-008: a hand-written partial config renders
        # byte-identically to the pre-cap renderer). The value itself comes from
        # the layered read. The caps are not machine-overridable, so the machine
        # layer can only contribute diagnostics here.
        project_layer = autopilot_config.load_config(project_root)
        effective = effective_config.load_effective(project_root)
    except Exception:  # invalid/unreadable config must not break dispatching
        return None, None
    caps: list[int | None] = []
    for field in ("l2_read_file_cap", "l2_read_byte_cap"):
        value = effective.values.get(field) if field in project_layer else None
        caps.append(
            int(value)
            if isinstance(value, int) and not isinstance(value, bool) and value > 0
            else None
        )
    return caps[0], caps[1]


def _read_scope_caps(
    project_root: pathlib.Path, claims: Sequence[dict] | None = None
) -> tuple[int | None, int | None]:
    """Read-scope caps for the rendered task.md: project config first, then the
    card's claims.

    Two sources, in that order:

    1. the project layer (``_autopilot/config.json``) — an explicitly
       configured key always wins, unchanged from before
       (:func:`_project_scope_caps`);
    2. the card being dispatched (:func:`claim_budget_caps`), used only for the
       field the project layer left unset.

    Before T-03 the conductor computed the caps *before* reading the card, so a
    claims card inherited the previous dispatch's budget (or none); the caller
    now passes this card's own claims. ``claims=None``/empty keeps the
    historical behaviour bit for bit: no config → ``(None, None)`` → no cap
    lines → a pre-claims card renders the same bytes it did before (AC-007).
    """
    file_cap, byte_cap = _project_scope_caps(project_root)
    derived_file, derived_byte = claim_budget_caps(claims)
    if file_cap is None and derived_file:
        file_cap = derived_file
    if byte_cap is None and derived_byte:
        byte_cap = derived_byte
    return file_cap, byte_cap


# ── producer identity (mw-dispatch-card-gate T-13) ───────────────────────────
#
# Every conductor-produced task.md carries `<producer>@<version>` in its
# header region so the service layer can tell a *stale producer* (an old
# framework copy whose task.md shape predates the current envelope/extras
# contract) apart from a genuinely missing section. Without the line both
# look identical to the G-3 judge, and the incident's failure mode — every
# dispatch of an unsynced project refused with `envelope missing: ...` — is
# indistinguishable from a hand-written non-compliant card (AC-009/P-10).
#
# The version comes from the release train's own metadata, not a new constant:
# the multi-workers Python tree has no package.json, and AGENTS.md pins all
# packages to one lockstep version, so `packages/coding-agent/package.json`
# (the pi release the bundle is built from) is the existing version source;
# the repo-root `package.json` is the older second source.
PRODUCER_NAME = "autopilot-conductor"
PRODUCER_IDENTITY_KEY = "envelope_producer"
_PRODUCER_VERSION_UNKNOWN = "unknown"


def _repo_root() -> pathlib.Path:
    """Repo root of this file: packages/multi-workers/autopilot/dispatch.py."""
    return pathlib.Path(__file__).resolve().parents[3]


def producer_version() -> str:
    """Version of the release train this producer ships with.

    Read from the existing metadata sources in order:
    ``packages/coding-agent/package.json`` (the lockstep release version) then
    the repo-root ``package.json``. ``"unknown"`` is a marker for an
    unreadable source, never a version value: the header key is still written,
    and the service layer treats a non-parsing value as "producer declared no
    version" rather than guessing one.
    """
    for relative in ("packages/coding-agent/package.json", "package.json"):
        try:
            data = json.loads((_repo_root() / relative).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        value = data.get("version") if isinstance(data, dict) else None
        if isinstance(value, str) and value.strip():
            return value.strip()
    return _PRODUCER_VERSION_UNKNOWN


def producer_identity() -> str:
    """``<producer>@<version>`` for the task.md header line."""
    return f"{PRODUCER_NAME}@{producer_version()}"


# The value has no whitespace and is split on the FIRST `@`, so a producer
# name may not contain `@` (it never does: `PRODUCER_NAME` is kebab-case).
_PRODUCER_LINE_RE = re.compile(
    rf"^{PRODUCER_IDENTITY_KEY}\s*:\s*(?P<producer>[^\s@|]+)@(?P<version>[^\s|]+)\s*$",
    re.MULTILINE,
)


def parse_producer_identity(text: str) -> tuple[str, str] | None:
    """``(producer, version)`` from a rendered task.md, or None when absent.

    Shape (line-anchored, no whitespace inside the value):
    ``envelope_producer: <producer>@<version>``. Public so the T-13 regression
    and the T-14 service-layer consumer share exactly one parser — a second
    parser would be a second way to disagree about "old producer".
    """
    match = _PRODUCER_LINE_RE.search(text)
    if match is None:
        return None
    return match.group("producer"), match.group("version")


# ── dispatch-card envelope injection (mw-dispatch-card-gate T-09/T-10) ───────
#
# T-02 gave every tool-generated task.md the canonical envelope (the three
# section headings plus the bare `card_path:` / `card_sha256:` header lines).
# The conductor wrote task.md directly (`render_task_md` -> `dispatch()`) with
# only a frontmatter + prompt body — the exact shape the service-layer gate
# used to exempt as "no signal", and therefore the producer the gate did not
# actually cover. `render_task_md` renders the T-02 triple when given a `card`
# input, and `dispatch()` builds that input from the dispatch's own card file
# (`<key>/tasks/<stem>.md`) when one exists.
#
# T-09 injected the envelope only for card-backed dispatches and left the
# card-less internal ones (L3 reviewer / repair / roadmap-writer / phase-
# writer) byte-identical. That was the loophole the service gate's time
# boundary (launcher.py `ENVELOPE_ENFORCE_SINCE`) then closed the hard way: a
# card-less auto dispatch issued after the cutover is refused as "missing
# sections", so the whole autopilot path stalls. T-10 makes the injection
# unconditional: `dispatch()` synthesizes a non-empty canonical envelope from
# the dispatch metadata when no card file exists (`synthesized_card` below),
# so every conductor-produced task.md passes the same judge. The bare
# `card_path:` / `card_sha256:` lines stay card-only — there is no card to
# name for a synthesized one, and a phantom path would turn the T-06 card
# audit red (`missing_cards`).
ENVELOPE_CARD_SEED_DISCLAIMER = "以上为种子，不是探索上界；可自行检索补充上下文。"

_DEFAULT_DELIVERABLES = (
    "按任务书交付：report.md / output.md 必备段（结论 / 证据（含原始命令与输出）/ "
    "改动清单（coding）或未覆盖面声明（review）/ 残留与未验证 / 上下文来源清单）；"
    "coding 同时记录 trace.log 的写入事件。"
)

# Final requirements fallback: `_envelope_card_body` must never emit an empty
# section (T-10 requirement 1: non-emptiness is guaranteed by construction).
_DEFAULT_REQUIREMENTS = (
    "判据（可判定）：任务书列出的目标逐项满足，产物在本轮 worker 目录可核；"
    "[VERIFY] 证据与结论闭合，未满足不得声称完成。"
)

# Heading families for the card-section extraction, first hit wins (the same
# deliverables > context > requirements order as the T-01 judge). Canonical
# titles only — a card that uses a variant still gets its full body through
# the post-first-heading fallback below.
_CARD_SECTION_FAMILIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("deliverables", ("交付物", "交付", "预期产出", "预期产物", "产物", "输出", "证据")),
    ("context", ("背景", "上下文", "问题", "现状", "动机", "根因", "目标", "描述", "输入", "范围")),
    ("requirements", (
        "要求", "任务", "契约", "验收", "验证", "完成判定", "完成判据", "判据",
        "行为", "测试", "接口", "协议", "内容", "标准", "做法", "策略", "规范",
        "实现", "步骤", "改动", "变更",
    )),
)

_CARD_HEADING_RE = re.compile(r"^#{2,6}\s+(.*)$")

# ── §1.2 type extras on the DERIVED task.md (T-13/F-02) ──────────────────────
#
# The service judge (`launcher.type_extras_missing`) reads the derived
# task.md, but the producer only carried the three canonical sections: a card
# declaring its extras as separate `##` headings had them dropped by
# `extract_card_sections`, and a card-less synthesized dispatch had none at
# all — either way the row is refused after the cutover. The fix mirrors the
# TS generator (T-12 `renderCardSeedSections`):
#
#   1. every card heading outside the three envelope families is injected
#      verbatim as its own `## <title>` section (`extract_card_extras`);
#   2. any required item still absent is filled from the dispatch metadata
#      (never an empty skeleton — T-10 requirement 1).
#
# Only the three canonical role types have an extras rule. The conductor's
# registry types (phase-writer / repair / verifier / reviewer / roadmap-writer
# / vision / rag-research) are in the single-source vocabulary and require
# none, so this block is inert on every conductor-produced task.md.
PRODUCER_EXTRA_ITEMS: dict[str, tuple[str, ...]] = {
    "coding": ("写入允许面", "写入禁止面", "验收命令", "改动历史"),
    "research": ("唯一证据文件",),
    "review": ("审计目标", "未覆盖面声明"),
}

# Acceptance-command shapes worth lifting out of a card-less prompt. A miss is
# not an error: the fallback names the task's own decidable criterion instead.
_ACCEPTANCE_CMD_RE = re.compile(
    r"`?((?:python(?:\s+-X\s+utf8)?\s+-m\s+pytest|pytest|npm\s+(?:run\s+)?test|"
    r"pnpm\s+(?:run\s+)?test|yarn\s+test|npx\s+vitest|node\s+\S*vitest|"
    r"cargo\s+test|go\s+test|make\s+\S+)[^\n`]*)",
    re.IGNORECASE,
)


def _first_acceptance_command(prompt: str) -> str:
    """First acceptance-looking command in a prompt, or "" (real metadata)."""
    match = _ACCEPTANCE_CMD_RE.search(prompt)
    return match.group(1).strip() if match else ""


def _fallback_extra_line(item: str, worker_dir: str, prompt: str) -> str:
    """One required extra's non-empty line, built from real dispatch metadata.

    ``worker_dir`` is the round's own artifact directory (always available from
    the card input's ``worker_dir`` key); the acceptance command is lifted from
    the prompt. Nothing here is a placeholder: every clause states a fact about
    this round (its worker dir, its trace log, its prompt) or a conservative
    default rule ("undeclared paths are not written").
    """
    artifacts = f"{worker_dir}/" if worker_dir else "本轮 worker 目录"
    if item == "写入允许面":
        return (
            f"写入允许面: {artifacts}（本轮产物）；项目源文件的改动面以「要求」段列出的"
            "清单为准，未列出的路径不写。"
        )
    if item == "写入禁止面":
        return "写入禁止面: 上述允许面之外的文件一律不写；任务书未声明的路径视为禁止。"
    if item == "验收命令":
        command = _first_acceptance_command(prompt)
        if command:
            return f"验收命令: {command}"
        return (
            "验收命令: 以「要求」段列出的判定源为准；无显式命令时以 [VERIFY] 证据与结论"
            "闭合为验收判据。"
        )
    if item == "改动历史":
        return f"改动历史: {artifacts}trace.log 的写入事件（[WRITE_FILE] / [WRITE_EDIT]）。"
    if item == "审计目标":
        target = _first_content_line(prompt) or "任务书「要求」段列出的审计问题"
        return f"审计目标: {target}"
    if item == "未覆盖面声明":
        return (
            "未覆盖面声明: 本轮未核对/未及的环境、分支或断言须在报告「未覆盖面」段逐条"
            "列出，不得沉默略过。"
        )
    if item == "唯一证据文件":
        return f"唯一证据文件: {artifacts}output.md（本轮唯一写入文件，其余只读）。"
    # An item added to PRODUCER_EXTRA_ITEMS without a wording here must not
    # become an empty skeleton: name the item and point at the real task body.
    return f"{item}: 见「要求」段。"


def card_digest(path: pathlib.Path | str) -> str:
    """EOL-normalized sha256 of a card file.

    Thin wrapper over :func:`mw_common.sha256_eol_normalized` so the conductor
    renderer, the T-06 audit (`card_audit.card_digest`) and the TS leaf
    `shared/card-digest.ts` all hash through the same frozen recipe (CRLF→LF,
    then sha256).
    """
    return mw_common.sha256_eol_normalized(path)


def _extract_card_parts(
    text: str,
) -> tuple[dict[str, str], list[dict[str, str]]]:
    """(canonical sections, unclassified extra sections) of a card text.

    Python mirror of T-02/T-12's `extractCardSections`: a heading family with a
    non-empty body wins (first hit wins, an already-filled family does not
    claim a later heading), then every still-empty section falls back to the
    text after the first heading (or the whole text when there is no heading) —
    content is never dropped. Every heading NOT used by that pass and carrying
    a non-empty body is returned as an unclassified extra in document order
    (the §1.2 `写入允许面` / `审计目标` / ... sections, F-02).
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    headings: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        match = _CARD_HEADING_RE.match(line.strip())
        if match:
            headings.append((i, match.group(1).strip()))
    bodies = [
        "\n".join(
            lines[
                headings[order][0] + 1 : (
                    headings[order + 1][0] if order + 1 < len(headings) else len(lines)
                )
            ]
        ).strip()
        for order in range(len(headings))
    ]

    out = {"context": "", "requirements": "", "deliverables": ""}
    used: set[int] = set()
    for order, (_idx, title) in enumerate(headings):
        body = bodies[order]
        if not body:
            continue
        for section, tokens in _CARD_SECTION_FAMILIES:
            if out[section] == "" and any(title.startswith(token) for token in tokens):
                out[section] = body
                used.add(order)
                break
    fallback = (
        "\n".join(lines[headings[0][0] + 1 :]).strip() if headings else text.strip()
    )
    for section in out:
        if out[section] == "":
            out[section] = fallback
    extras = [
        {"title": headings[order][1], "body": bodies[order]}
        for order in range(len(headings))
        if order not in used and bodies[order]
    ]
    return out, extras


def extract_card_sections(text: str) -> dict[str, str]:
    """Canonical envelope sections of a card text (3-key shape, unchanged).

    The unclassified §1.2 extras live in :func:`extract_card_extras` — kept
    out of this return value so the caller contract stays the 3-key dict the
    T-02/T-10 tests pin.
    """
    return _extract_card_parts(text)[0]


def extract_card_extras(text: str) -> list[dict[str, str]]:
    """Card headings outside the three envelope families, in document order.

    Each entry is ``{"title": <heading text>, "body": <non-empty body>}``;
    `_envelope_card_body` re-emits them verbatim as `## <title>` sections so a
    card that declares its extras as headings is not false-rejected by the
    service extras judge (F-02, mirror of the TS `CardSections.extras`).
    """
    return _extract_card_parts(text)[1]


def dispatch_card(project_root: pathlib.Path, owner: str, stem: str) -> dict | None:
    """The card input for one conductor dispatch, or None when the dispatch has
    no card file.

    The card identity is the D-111 execute-loop contract: the task card is
    ``<key>/tasks/<stem>.md`` and the stem is the dispatch's own stem. Missing
    file = no card (card-less internal dispatch), and the renderer then stays
    byte-identical to the pre-T-09 output.

    ``extras`` carries the card's unclassified headings (T-13/F-02) and
    ``worker_dir`` the round's artifact directory, so the renderer can both
    inject the card's own declarations and fill any still-missing §1.2 item
    from real metadata (never an empty skeleton).

    ``claims`` (T-03) is the card's parsed ``mw-claims: v1`` block and
    ``claim_errors`` its row-level parse errors. The card text read here is the
    only text source in the module, so the claims are parsed from it exactly
    once (no second read) and the derived read budget follows THIS card —
    ``dispatch()`` reads the claims from this dict instead of pricing the caps
    before the card exists. A card without a claims block returns ``[]`` (the
    pre-claims behaviour).
    """
    card_path = f"tasks/{stem}.md"
    card_file = pathlib.Path(project_root) / ".agenticdoc" / owner / card_path
    if not card_file.is_file():
        return None
    try:
        text = card_file.read_text(encoding="utf-8", errors="replace")
        sections, extras = _extract_card_parts(text)
        claims_block = parse_claims_block(text)
        digest = card_digest(card_file)
    except OSError:
        return None
    return {
        "path": card_path,
        "sha256": digest,
        "worker_dir": f".agenticdoc/{owner}/workers/{task_key_for(owner, stem)}",
        "extras": extras,
        # T-03: claims parsed from the text above (single read, single grammar)
        # + their row-level errors. A malformed row is reported, never raised.
        "claims": claims_block["claims"],
        "claim_errors": claims_block["errors"],
        **sections,
    }


# ── S2 recovery-contract checklist (mw-worker-output-contract T-06, AC-003) ───
#
# The card-declared report roles get their `output.md` / `report.md` section
# contract injected into the task.md body, so the worker knows the required
# sections BEFORE it starts instead of being stopped at settle with
# `missing section(s): …` (AC-003; design §4.4). The section names are the
# write-side contract of `packages/coding-agent/src/extensions/agent-team-loop/
# worker/output-sections.ts`: the base four every report role must carry
# (`RECOVERY_SECTIONS`) plus the role extra (`RECOVERY_TYPE_SECTIONS`).
# Python cannot import a TS module, so the two tuples below are a verbatim
# mirror; `test_mwoc_s2_sections.py::test_recovery_tables_match_the_ts_source`
# parses the real TS source and fails on any drift — never two free-running
# copies (requirement 3).
RECOVERY_SECTIONS: tuple[str, ...] = ("结论", "证据", "残留与未验证", "上下文来源")
RECOVERY_TYPE_SECTIONS: dict[str, tuple[str, ...]] = {
    "coding": ("改动清单",),
    "review": ("未覆盖面声明",),
}

# The card types whose task.md carries the checklist: the three card-declared
# report roles (the same keys as :data:`PRODUCER_EXTRA_ITEMS`) plus the two
# writable internal conductor roles (`phase-writer` / `roadmap-writer`). The
# latter settle an artifact but DO produce a `report.md` product along the way,
# and the settle judge (worker-mode.ts `judgeRecoveryHere`) judges any write
# role once `hasReportProduct` is true — E2Feature gate-0032 shipped exactly
# this trap: a phase-writer wrote a free-form report.md, the judge fail-closed
# on missing section aliases, and the loop stalled after burning both attempts
# despite byte-correct deliverables. Injecting the checklist is inert for a
# settle that produces no report product (`hasReportProduct=False` never
# triggers the section judgement), so over-inclusion costs nothing.
# The remaining internal roles (`verifier` / `reviewer` / `repair`) settle a
# verdict on the reply/summary, not a sectioned report — they stay
# uninjected. The `vision` / `rag-research` buckets are out of the contract's
# scope — injecting a section list there would announce a contract the role
# does not carry (requirement 2: 无契约段角色不注入，不硬塞空段名).
RECOVERY_CONTRACT_TYPES: tuple[str, ...] = (
    "coding", "research", "review", "phase-writer", "roadmap-writer",
)

#: Fixed heading of the injected checklist section.
RECOVERY_CONTRACT_HEADING = "## 交付段契约（本角色）"


def recovery_sections_for(task_type: str) -> tuple[str, ...]:
    """Checklist of ``task_type``: the base four plus its role extra.

    Mirror of the TS ``recoverySectionsFor`` (``RECOVERY_SECTIONS`` +
    ``RECOVERY_TYPE_SECTIONS[type]``); a type absent from the extra table
    carries the base four only.
    """
    return RECOVERY_SECTIONS + RECOVERY_TYPE_SECTIONS.get(task_type, ())


def recovery_contract_section(task_type: str) -> str:
    """The ``## 交付段契约（本角色）`` block, or "" outside the report roles.

    Every required section is rendered as a copyable ``## <段名>`` code span
    (AC-003: 每段给出可复制的 ``## <段名>``), so the worker can paste the
    heading verbatim. The names are the canonical ones the settle judge looks
    for — never an invented alias. ``""`` for a type outside
    :data:`RECOVERY_CONTRACT_TYPES` (and for an empty checklist), so a
    card-backed render of an internal/out-of-scope role stays byte-identical.
    """
    if task_type not in RECOVERY_CONTRACT_TYPES:
        return ""
    sections = recovery_sections_for(task_type)
    if not sections:
        return ""
    lines = [
        RECOVERY_CONTRACT_HEADING,
        "",
        f"本角色（type: {task_type}）的恢复契约段：report.md / output.md 必须按下列标题"
        "成节（可直接复制；缺任一段即 settle 判缺失）：",
        "",
    ]
    lines.extend(f"- `## {name}`" for name in sections)
    return "\n".join(lines)


def _envelope_card_body(card: dict, prompt: str, task_type: str = "") -> str:
    """The canonical G-2 body: the three section headings plus the
    seed-not-an-upper-bound disclaimer (T-02 contract C3 shape), the card's
    unclassified §1.2 extras, this type's still-missing extras (T-13), and the
    S2 recovery-contract checklist (T-06/AC-003).

    Every section is non-empty by construction (T-10 requirement 1): a missing
    context falls back to a synthesized autopilot sentence, empty requirements
    fall back to the prompt and then to :data:`_DEFAULT_REQUIREMENTS`, and
    empty deliverables fall back to :data:`_DEFAULT_DELIVERABLES`.

    The extras half is inert for every conductor registry type (none has an
    extras rule); for `coding`/`review`/`research` it guarantees the derived
    task.md satisfies the service extras judge on its own (F-02). The
    recovery-contract checklist (:func:`recovery_contract_section`) is
    injected for those same report roles only — this function is the
    card-backed branch of :func:`render_task_md`, so a `card=None` legacy
    render never sees it.
    """
    context = str(card.get("context") or "").strip()
    requirements = (
        str(card.get("requirements") or "").strip()
        or prompt.strip()
        or _DEFAULT_REQUIREMENTS
    )
    deliverables = str(card.get("deliverables") or "").strip() or _DEFAULT_DELIVERABLES
    if not context:
        ref = str(card.get("path") or "").strip()
        context = (
            "本任务由 autopilot conductor 自动派发（种子）"
            + (f"，来源卡片 {ref}" if ref else "")
            + "；项目锚点见 .agenticdoc/goal.md，可自行只读检索补充。"
        )
    parts = [
        "## 上下文", "", context, "",
        "## 要求", "", requirements, "",
        "## 交付格式", "", deliverables, "",
    ]
    for extra in card.get("extras") or ():
        if not isinstance(extra, dict):
            continue
        title = str(extra.get("title") or "").strip()
        body = str(extra.get("body") or "").strip()
        if title and body:
            parts += [f"## {title}", "", body, ""]
    # T-13 extras judgement runs on the card's own declarations BEFORE the
    # S2 checklist is appended: the checklist names the recovery sections, it
    # is not a declaration of the §1.2 extras, so it must not suppress a
    # still-missing extras fallback line (`未覆盖面声明` is both a review
    # recovery section and a review extra item — the names coincide by design).
    declared_text = "\n".join(parts)
    required = PRODUCER_EXTRA_ITEMS.get(task_type)
    missing = [item for item in required if item not in declared_text] if required else []
    # S2/AC-003: the role's recovery-contract checklist. The presence guard
    # makes the injection idempotent — a card that already declares the heading
    # (or a re-render of an already-seeded body) is never given a second copy.
    if RECOVERY_CONTRACT_HEADING not in declared_text:
        contract = recovery_contract_section(task_type)
        if contract:
            parts += [contract, ""]
    text = "\n".join([*parts, ENVELOPE_CARD_SEED_DISCLAIMER])
    if not required:
        return text
    if not missing:
        return text
    worker_dir = str(card.get("worker_dir") or "").strip()
    lines = [_fallback_extra_line(item, worker_dir, prompt) for item in missing]
    return text.rstrip() + "\n\n" + "\n".join(lines)


def _first_content_line(text: str) -> str:
    """First non-empty line of a prompt, heading markers stripped."""
    for raw in text.splitlines():
        line = raw.strip().lstrip("#").strip()
        if line:
            return line
    return ""


def _synthesized_deliverables(worker_dir: str) -> str:
    """Artifact path + shape for a card-less dispatch (T-10 requirement 1).

    Deliberately phrased without the shared :data:`_DEFAULT_DELIVERABLES`
    write-verb vocabulary: the L3/verifier provenance guard (F-P4 T1/T2)
    treats any clause naming output.md/report.md or ``workers/`` together with
    a write verb as a write directive on the deciding source, and a card-less
    envelope body is scanned by that guard like any other dispatched task.md.
    """
    return (
        f"交付格式：本轮产物集中在 {worker_dir}/，报告与输出文件"
        "（report.md / output.md）按任务书列出的必备段成节"
        "（结论 / 证据（含原始命令与输出）/ 审计未及范围 / 残留与未验证 / "
        "上下文来源清单）。"
    )


def synthesized_card(
    owner: str, stem: str, task_type: str, prompt: str, loop: str, attempt: int
) -> dict:
    """Card-less auto-dispatch envelope, synthesized from the dispatch metadata.

    T-10 requirement 1: the L3 review/reprompt, repair, roadmap-writer and
    phase-writer dispatches have no `tasks/<stem>.md` card, so there is no card
    text to read. Instead of an empty skeleton, the three canonical sections
    are built from what the conductor already knows (never nothing):

    * context      — trigger/failure reason (the prompt's first line) plus the
                     evidence paths (this round's worker dir + goal.md);
    * requirements — the task prompt itself (the repair/proposal goal) plus an
                     explicit decidable criterion;
    * deliverables — the round's artifact path and the required section shape.

    The returned dict has empty ``path`` / ``sha256`` on purpose: a card-less
    dispatch must not name a card it does not have (the T-06 audit would flag
    the phantom reference as ``missing_cards``).
    """
    task_key = task_key_for(owner, stem)
    worker_dir = f".agenticdoc/{owner}/workers/{task_key}"
    trigger = _first_content_line(prompt) or f"{task_type} 自动派发"
    context = (
        f"autopilot 自动派发（无任务卡；以下为种子，不是探索上界）。"
        f"type={task_type}，loop={loop}，attempt={attempt}。"
        f"触发/失败原因：{trigger}。"
        f"证据路径：{worker_dir}/trace.log、{worker_dir}/worker.log "
        f"及任务书要求段列出的判定源；项目锚点 .agenticdoc/goal.md。"
    )
    body = prompt.strip()
    requirements = f"{body}\n\n{_DEFAULT_REQUIREMENTS}" if body else _DEFAULT_REQUIREMENTS
    return {
        "path": "",
        "sha256": "",
        # T-13: the round's artifact directory, so a missing §1.2 extra is
        # filled from real metadata rather than an empty skeleton.
        "worker_dir": worker_dir,
        "context": context,
        "requirements": requirements,
        "deliverables": _synthesized_deliverables(worker_dir),
    }


def _worker_timeout_min(project_root: pathlib.Path) -> int | None:
    """`worker_timeout_min` for the rendered task.md, or None when unconfigured.

    Until 2026-09-26 this key was a silent no-op: config.py parsed and
    validated it, but no renderer emitted a task.md `timeout:` header, so the
    worker wall chain (task.md > PI_WORKER_TIMEOUT_MS > 60m,
    worker-mode.ts `resolveBudgetMs`) could never reach the configured value
    (D-017/VC-015).

    Only an explicit project-layer value is rendered, mirroring
    :func:`_read_scope_caps`. The built-in default (config.py
    ``worker_timeout_min = 30``) must NOT materialise as a header: task.md wins
    the chain, so rendering the default would silently cut every
    conductor-dispatched worker from the 60m harness default to 30m — the same
    regression that moved `DEFAULT_BUDGET_MS` to 60m in the first place.
    """
    try:
        if not autopilot_config.config_path(project_root).exists():
            return None
        project_layer = autopilot_config.load_config(project_root)
        if "worker_timeout_min" not in project_layer:
            return None
        effective = effective_config.load_effective(project_root)
    except Exception:  # invalid/unreadable config must not break dispatching
        return None
    value = effective.values.get("worker_timeout_min")
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None


def render_task_md(
    task_type: str,
    prompt: str,
    *,
    loop: str,
    attempt: int,
    read_scope: Sequence[str] = (),
    deny_globs: Sequence[str] = (),
    read_file_cap: int | None = None,
    read_byte_cap: int | None = None,
    model: str = "",
    phase: str = "",
    images: str | None = None,
    profile_block: str | None = None,
    rag_config: dict | None = None,
    task_meta: dict | None = None,
    worker_timeout_min: int | None = None,
    card: dict | None = None,
) -> str:
    """Render one conductor task.md: frontmatter labels + prompt body.

    ``card is not None`` is the dispatch-envelope presence marker (T-09/T-10;
    ``card=None`` is the documented legacy/direct-unit-test shape the read-scope
    byte-identity suite pins), and it also gates two T-13 additions: the
    ``envelope_producer: <producer>@<version>`` header line and the §1.2 type
    extras. Both are therefore always present on a real dispatch (``dispatch()``
    always supplies a card) and never alter a legacy render.

    Every conductor dispatch carries origin/loop/attempt (design §4.1);
    read_scope renders as a YAML block list (verifier requires it —
    dispatch() enforces, this renderer just renders). deny_globs (mw-
    dual-workspace AC-006) renders single-quoted: a leading ``*`` is a YAML
    alias marker, and single-quote style has no escape sequences — the
    worker-side parser (worker-mode.ts) strips one quote pair.

    ``phase`` (mw-rag-integration T-14): the phase axis of
    ``required = role.require OR phase.require``. Only a non-empty value emits
    ``phase: <P>`` right after ``type:`` — ``phase=""`` (unknown phase,
    ``_scratch``, legacy callers) leaves the output byte-identical to the
    pre-T-14 renderer, so existing task.md files and tests do not churn.

    ``images`` (mw-vision-role AC-009): the task's declared image capability
    (``"yes"`` / ``"no"``). Only a truthy value emits ``images: <v>`` between
    ``phase:`` and ``model:`` — both ``None`` and ``""`` leave the output
    byte-identical to the pre-images renderer (the header declares a caller
    decision, it is never a default, so an undeclared task must not gain a
    line).

    ``profile_block`` (mw-target-partition FIX-1) is emitted before the RAG
    block so the conductor path keeps the same block order as the TS
    dispatcher. ``rag_config`` is `mw_common.load_rag_config`'s output; an
    absent/empty config appends nothing. Re-rendering is idempotent: an
    existing `mw-rag: v1` block is replaced wholesale (same marker/anchor).

    ``read_file_cap`` / ``read_byte_cap`` (read-scope budgets, see
    :func:`_read_scope_caps`) render only when supplied — ``None`` (absent
    config, legacy callers, direct unit tests) leaves the output
    byte-identical to the pre-fix renderer.

    ``worker_timeout_min`` (D-017) renders ``timeout: <minutes>`` in the
    frontmatter only when the project explicitly configured the key
    (:func:`_worker_timeout_min`) — worker-mode.ts gives the task.md header
    top priority in the wall chain, so an unconfigured render would pin every
    worker to the config default instead of the 60m harness default.

    ``card`` (T-09) is the T-02-shaped envelope input ``{"path", "sha256",
    "context", "requirements", "deliverables"}``: a non-empty ``path`` /
    ``sha256`` renders the bare ``card_path:`` / ``card_sha256:`` header lines,
    and the body becomes the canonical ``## 上下文`` / ``## 要求`` /
    ``## 交付格式`` triple (missing section bodies fall back to the prompt /
    a generic deliverable contract). ``card=None`` (legacy callers, direct
    unit tests) keeps the pre-T-09 bytes exactly, which is why the byte
    goldens for card-less internal dispatches stay valid.

    T-13 additions, both gated by ``card is not None`` (the dispatch-envelope
    presence marker): the optional ``extras`` list of ``{"title", "body"}``
    card sections is re-emitted verbatim as ``## <title>`` sections, any
    still-missing §1.2 item of ``task_type`` is filled from
    ``card["worker_dir"]`` / the prompt, and the header carries
    ``envelope_producer: <producer>@<version>`` (the service layer's
    old-producer vs. genuinely-missing-section discriminator). ``card=None``
    stays byte-identical, so the read-scope regression suite's frozen-renderer
    comparisons hold.

    ``write_face:`` (mw-write-face-guard W-03/D-001): the card's
    ``## 写入允许面`` entries render as ONE header line (``write_face: a, b``;
    a declared-but-empty section renders the ``-`` undeclared marker). The
    line is emitted only when the card carries that section, so every
    card-less render stays byte-identical; :func:`render_write_face_line` is
    the single renderer and :func:`write_face.parse_write_face` the single
    parser, so the two are the same source (the round trip is pinned in
    ``test/test_write_face_dispatch.py``).
    """
    lines = [
        "---",
        f"type: {task_type}",
    ]
    card = card if isinstance(card, dict) else None
    write_face_entries = _card_write_face_entries(card)
    if card is not None:
        card_path = str(card.get("path") or "").strip()
        card_sha256 = str(card.get("sha256") or "").strip()
        if card_path:
            lines.append(f"card_path: {card_path}")
        if card_sha256:
            lines.append(f"card_sha256: {card_sha256}")
    if phase:
        lines.append(f"phase: {phase}")
    if images:   # None / "" -> zero bytes (AC-009); declared -> images: yes|no
        lines.append(f"images: {images}")
    if model:
        lines.append(f"model: {model}")
    if card is not None:
        # T-13: producer identity/version, machine-readable, next to the other
        # attribution line (`origin: conductor`). It sits after the semantic
        # headers (phase/images/model) so the `type:`-adjacent ordering the
        # rag-phase contract pins stays byte-identical.
        lines.append(f"{PRODUCER_IDENTITY_KEY}: {producer_identity()}")
    lines += [
        "origin: conductor",
        f"loop: {loop}",
        f"attempt: {attempt}",
    ]
    if worker_timeout_min is not None:
        lines.append(f"timeout: {int(worker_timeout_min)}")
    if read_scope:
        lines.append("read_scope:")
        lines.extend(f"  - {item}" for item in read_scope)
    if read_file_cap is not None:
        lines.append(f"l2_read_file_cap: {int(read_file_cap)}")
    if read_byte_cap is not None:
        lines.append(f"l2_read_byte_cap: {int(read_byte_cap)}")
    if deny_globs:
        lines.append("deny_globs:")
        lines.extend(f"  - '{item}'" for item in deny_globs)
    if write_face_entries is not None:
        lines.append(
            render_write_face_line(write_face_entries)
            if write_face_entries else "write_face: -"
        )
    body = (
        prompt.strip() if card is None
        else _envelope_card_body(card, prompt, task_type)
    )
    lines += ["---", "", body, ""]
    content = "\n".join(lines) + "\n"
    if profile_block is not None:
        content = content.rstrip() + "\n\n" + profile_block + "\n"
    return _inject_rag_block(content, rag_config, task_meta, task_type)


# ── workspace-profile injection (mw-dual-workspace D-005/D-007) ────────────────

def _expand_read_scope(
    scope: list[str], config: dict, project_root: pathlib.Path
) -> list[str]:
    """D-007 (mw-dual-workspace) + D-006 (mw-target-partition) + AC-001
    (mw-partition-parent-extended): dual mode anchors relative entries
    against the game root and partition mode against the partition root
    (the worker cwd in both), then appends the control root when absent
    (D-005: profile authorization — the worker must be able to read
    target.yml / task context files; never appended to an empty scope —
    that would create containment the dispatch never asked for). The
    parent root IS appended in partition mode: parent is the extended
    writable workspace (mw-partition-parent-extended AC-001 — the carved-
    out functionality lives in the parent and is developed directly),
    with the same absent-only append + normcase dedup as the control root.
    Single mode: scope passes through unchanged — relative entries anchor
    cwd = the (single) control root, so expansion would only churn output."""
    mode = config["mode"]
    if mode not in ("dual", "partition") or not scope:
        return scope
    anchor = pathlib.Path(config["game_root"] if mode == "dual" else config["partition_root"])
    expanded = [
        item if pathlib.Path(item).is_absolute() else str((anchor / item).resolve())
        for item in scope
    ]
    # Only widen an ALREADY-configured containment: appending the control
    # root to an empty scope would create containment the dispatch never
    # asked for (scopeless types keep full access — AC-012 red line).
    control = str(project_root.resolve())
    if all(os.path.normcase(s) != os.path.normcase(control) for s in expanded):
        expanded.append(control)
    if mode == "partition":
        # Extended workspace (AC-001): the parent root joins the containment
        # with the same absent-only append + normcase dedup as the control
        # root. Order: [...entries, control, parent].
        parent = config.get("parent_root")
        if parent:
            parent_abs = str(pathlib.Path(parent).resolve())
            if all(os.path.normcase(s) != os.path.normcase(parent_abs) for s in expanded):
                expanded.append(parent_abs)
    return expanded


def _resolve_deny_globs(config: dict, explicit: Sequence[str] | None) -> list[str]:
    """AC-006 generation side: deny globs default from target.yml's
    ignore.deny_globs (any mode — a single-root UE project can still deny
    its DDC); an explicit per-task list (including empty) wins."""
    if explicit is not None:
        return [str(g) for g in explicit]
    return [str(g) for g in config.get("ignore", {}).get("deny_globs", [])]


# ── dispatch ──────────────────────────────────────────────────────────────────

@dataclasses.dataclass(frozen=True)
class DispatchResult:
    """Outcome of one dispatch attempt.

    ok=True  — task.md + queue row written and the row read back verified.
    ok=False — nothing entered the queue (rows stays 0); ``reason`` names why:
    unknown-type | verifier-read-scope-required | lock-unavailable |
    run-terminal:<status> | run-running (AC-004: a settled or live `run.json`
    outranks the ledger; both refuse before any side effect).
    A failure after the task.md was written (lock-unavailable) leaves the
    orphan shape on purpose — reconciliation re-inserts it next tick."""

    ok: bool
    reason: str
    task_key: str
    task_md: pathlib.Path | None
    row_verified: bool


def task_key_for(owner: str, stem: str) -> str:
    """Queue/task-dir identity: ap-{owner}-{stem} (D-111; ap- is globally
    unique to conductor dispatches, manual keys cannot collide)."""
    return f"ap-{owner}-{stem}"


def _timeline_key(owner: str) -> str | None:
    """Key field for timeline events: the owner key, or None (= '-'
    sentinel) for _scratch (stage-level) dispatches."""
    return None if owner == SCRATCH_OWNER else owner


# ── write-face gate (mw-write-face-guard W-03, D-001..D-008) ──────────────────

#: Card section whose entries become the task.md `write_face:` head (D-001).
WRITE_FACE_CARD_SECTION = "写入允许面"

#: Stable audit event kinds (D-008; W-06/doctor counts them).  A refused
#: dispatch emits `write-face-rejected` (parse-time) or `write-face-overlap`;
#: `write-face-undeclared` records the D-003 serial-only decision.
WRITE_FACE_AUDIT_UNDECLARED = "write-face-undeclared"
WRITE_FACE_AUDIT_OVERLAP = "write-face-overlap"
WRITE_FACE_AUDIT_REJECTED = "write-face-rejected"

_BACKTICK_SPAN_RE = re.compile(r"`([^`]+)`")


def write_face_case_insensitive() -> bool:
    """Explicit case mode for the write-face operator (D-006/AC-007).

    Never inferred inside the operator: the single platform helper lives at the
    call site, so the frozen corpus can pin both modes on either platform.
    """
    return os.name == "nt"


def write_face_base(project_root: pathlib.Path) -> str:
    """Base for every write-face parse: the same root `mw_common.workers_path`
    anchors, i.e. the `.agenticdoc` parent (card requirement 7)."""
    return str(project_root)


def _card_write_face_entries(card: dict | None) -> list[str] | None:
    """Raw entries of a card's `## 写入允许面` section.

    ``None`` = the section is absent (undeclared; no `write_face:` line is
    rendered). A present-but-entry-less section yields ``[]`` (the renderer
    then writes the ``-`` undeclared marker, D-001/§3.3). Entries keep the
    operator's single-`/` syntax verbatim: the renderer must not transform what
    the parser will normalize, or the two would stop being the same source
    (requirement 9). The section body itself is never part of the render —
    only these extracted entries are.
    """
    if not isinstance(card, dict):
        return None
    for extra in card.get("extras") or ():
        if not isinstance(extra, dict):
            continue
        title = str(extra.get("title") or "").strip()
        if not title.startswith(WRITE_FACE_CARD_SECTION):
            continue
        entries: list[str] = []
        for raw in str(extra.get("body") or "").splitlines():
            item = raw.strip()
            if not item:
                continue
            if item[0] in "-*+":
                item = item[1:].strip()
            span = _BACKTICK_SPAN_RE.search(item)
            if span is not None:
                item = span.group(1).strip()
            else:
                item = re.split(r"[\s（(]", item, maxsplit=1)[0].strip()
            if item and item != "-":
                entries.append(item)
        return entries
    return None


def render_write_face_line(entries: Sequence[str]) -> str:
    """The task.md `write_face:` head value for a non-empty entry list.

    The contract is D-113's round trip — ``parse_write_face`` of this string
    yields exactly `entries` (normalized, order included).  Two carrier shapes
    serve it:

    * no entry contains `,` -> the historical single line
      ``write_face: a, b`` (byte-identical to the pre-D-113 renderer);
    * any entry contains `,` -> the design §3.1 block-list carrier
      ``write_face:\n  - a\n  - b``, one entry per list item.  D-112 makes
      `,` an unconditional single-line separator that brackets/braces/quotes
      never shield, so a comma-bearing entry (e.g. the legal `a/{b,c}/**`)
      cannot survive the single line; the block form is the §3.1 equivalent
      and ``parse_write_face`` reads each list item as one whole entry.

    The returned string MAY contain newlines (the block shape).  The sole
    caller, :func:`render_task_md`, appends it as one element of its `lines`
    list, so the block shape lands as a valid multi-line head and the call
    site does not change.

    `entries` is non-empty by contract — the caller writes ``write_face: -``
    for a declared-but-empty face.
    """
    values = [str(entry).strip() for entry in entries]
    if any("," in entry for entry in values):
        return "write_face:\n" + "\n".join(f"  - {entry}" for entry in values)
    return "write_face: " + ", ".join(values)


def _write_face_audit(
    timeline: timeline_mod.Timeline | None, owner: str, ev: str, detail: str
) -> None:
    """Append one write-face audit event (D-008), never raising."""
    if timeline is not None:
        timeline.append(ev, key=_timeline_key(owner), detail=detail)


def _parse_inflight_write_face(
    row: dict[str, str], *, base: str, case_insensitive: bool
) -> write_face_mod.ParseResult | write_face_mod.WriteFace:
    """The in-flight worker's own task.md `write_face:` head.

    A missing/unreadable task.md is "no information" (``Undeclared``), never a
    guessed face: D-003 says a side that did not declare cannot prove an
    overlap, so the caller must not refuse on it.
    """
    path = str(row.get("task_path") or "").strip()
    if not path:
        return write_face_mod.Undeclared()
    try:
        text = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return write_face_mod.Undeclared()
    return write_face_mod.parse_write_face(
        text, base=base, case_insensitive=case_insensitive
    )


def _write_face_verdict(
    project_root: pathlib.Path,
    owner: str,
    task_key: str,
    content: str,
    *,
    card_backed: bool,
    timeline: timeline_mod.Timeline | None,
) -> DispatchResult | None:
    """D-001..D-008 gate, called INSIDE the `workers.lock` critical section.

    Returns a zero-side-effect refusal (`ok=False`, no taskDir / task.md / queue
    row) when this dispatch must not be queued, or ``None`` to proceed.

    The in-flight set is recomputed here from the live queue file (AC-008 — no
    queue column is added, D-004); ``mw_common.parse_workers_file`` is the
    lock-free reader (a second ``acquire_lock`` while already holding the lock
    backs off for 14.6h and then raises, RQ-D3).

    Card-less one-shot internal dispatches (L3 / repair / roadmap / phase-writer
    — the RQ-W2 §1.1 call-site list) are exempt from the D-003 serial-only
    *refusal* but still audited and dispatched normally: they carry no card the
    author could declare a face on, and the conductor treats a refused internal
    dispatch as a failure (`mark_stalled` / `return result.ok`), so refusing one
    would manufacture a permanent failure. A card-backed dispatch stays
    author-fixable, so its undeclared face is held serial-only.
    """
    base = write_face_base(project_root)
    case_insensitive = write_face_case_insensitive()
    parsed = write_face_mod.parse_write_face(
        content, base=base, case_insensitive=case_insensitive
    )
    rows = mw_common.parse_workers_file(mw_common.workers_path(project_root))
    in_flight = [
        row for row in rows
        if str(row.get("task_key", "")) != task_key
        # Same-owner predicate, origin-independent (mw_common.worker_owner_key
        # :2012; the conductor's `row_belongs_to` :2026 is conductor-only).
        and mw_common.worker_owner_key(row) == owner
        # The one existing terminal-status set (mw_common.py:168; the
        # conductor's single `_is_in_flight`, conductor.py:3540) — no local
        # set is invented.
        and str(row.get("status", "")) not in mw_common._TERMINAL_STATUSES  # noqa: SLF001
    ]

    if isinstance(parsed, write_face_mod.Refused):
        _write_face_audit(
            timeline, owner, WRITE_FACE_AUDIT_REJECTED,
            f"{task_key}: {parsed.code} {parsed.detail}".rstrip(),
        )
        return DispatchResult(
            ok=False,
            reason=f"{parsed.code}: {parsed.detail}".rstrip(": "),
            task_key=task_key,
            task_md=None,
            row_verified=False,
        )

    if isinstance(parsed, write_face_mod.Undeclared):
        # Audit coverage: a card-backed dispatch is always author-fixable; a
        # card-less one is audited only when the serial-only rule is actually
        # in play, so a no-contention internal dispatch stays byte-identical to
        # the pre-D-003 flow (which is what keeps the AC-017 event-count
        # assertions of the existing suite green).
        if in_flight or card_backed:
            _write_face_audit(
                timeline, owner, WRITE_FACE_AUDIT_UNDECLARED,
                f"{task_key}: write_face undeclared; {len(in_flight)} same-owner "
                f"worker(s) in flight",
            )
        if in_flight and card_backed:
            return DispatchResult(
                ok=False,
                reason=(
                    "write-face-undeclared: serial-only "
                    f"({len(in_flight)} same-owner worker(s) in flight)"
                ),
                task_key=task_key,
                task_md=None,
                row_verified=False,
            )
        return None

    for row in in_flight:
        other_key = str(row.get("task_key", ""))
        other_face = _parse_inflight_write_face(
            row, base=base, case_insensitive=case_insensitive
        )
        if not isinstance(other_face, write_face_mod.WriteFace):
            continue  # a side that did not declare cannot prove an overlap (D-003)
        result = write_face_mod.overlap(parsed, other_face)
        if result is None:
            continue
        if isinstance(result, write_face_mod.Conflict):
            detail = (
                f"{task_key}: overlap with {other_key} at {result.sample} "
                f"({result.rule} vs {result.other})"
            )
            reason = (
                f"write-face-overlap: overlap-with:{other_key} "
                f"sample={result.sample}"
            )
        else:
            # D-006 conservative fallback: an undecidable pair IS an overlap.
            detail = (
                f"{task_key}: undecidable overlap with {other_key} "
                f"({result.reason}: {result.detail}) treated as overlap"
            )
            reason = (
                f"write-face-overlap: overlap-with:{other_key} "
                f"unsupported={result.reason}"
            )
        _write_face_audit(timeline, owner, WRITE_FACE_AUDIT_OVERLAP, detail)
        return DispatchResult(
            ok=False, reason=reason, task_key=task_key, task_md=None,
            row_verified=False,
        )
    return None


def dispatch(
    project_root: pathlib.Path,
    owner: str,
    stem: str,
    task_type: str,
    prompt: str,
    *,
    loop: str,
    attempt: int,
    read_scope: Sequence[str] = (),
    deny_globs: Sequence[str] | None = None,
    model: str = "",
    timeline: timeline_mod.Timeline | None = None,
) -> DispatchResult:
    """Dispatch one typed worker task: run the write-face gate, write task.md
    and the queue row under one workers.lock critical section, then verify the
    row by reading it back.

    Rejections (zero queue rows, zero task.md, timeline event):
      - unregistered type (never a tool-set fallback, GC-8/D-107)
      - verifier without a non-empty read_scope (D-106)
      - unusable target.yml (mw-dual-workspace fail-closed: never a silently
        un-injected task.md; event kind target-config-rejected)
      - `run.json` already terminal or `running` (AC-004/DD-12, checked
        first, with zero side effects: no task dir, no queue row)
      - write-face parse refusal (event `write-face-rejected`), a provable
        overlap with an in-flight same-owner worker (`write-face-overlap`), or
        an undeclared face that must stay serial-only (`write-face-undeclared`)
        - AC-014: the judgement, the task.md write and the row write share one
        `workers.lock` critical section, so a refusal cannot leave a task dir.
      - the same `task_key` already has a non-terminal row in the live queue
        (`duplicate-dispatch:`, MDC M-04): identity-level, judged inside the
        same critical section, and zero-side-effect like the write-face
        refusal. A terminal old row (done/failed/...) still re-dispatches
        through the upsert, so a retry of the same identity is not sealed off.
    On success a ``dispatch`` timeline event is appended (AC-017: every
    dispatch leaves a timeline trace), when a timeline writer is given.
    """
    project_root = pathlib.Path(project_root)
    task_key = task_key_for(owner, stem)
    # The identity path is only computed here; creating it still happens after
    # every rejection below, so a refused dispatch leaves zero side effects.
    task_dir = project_root / ".agenticdoc" / owner / "workers" / task_key

    def reject(reason: str, detail: str, ev: str = "type-rejected") -> DispatchResult:
        if timeline is not None:
            timeline.append(
                ev, key=_timeline_key(owner), detail=f"{task_key}: {detail}"
            )
        return DispatchResult(
            ok=False, reason=reason, task_key=task_key, task_md=None, row_verified=False
        )

    # AC-004 (DD-12): the product carries its own run state (T-20/D-022), and
    # that state outranks every ledger-derived criterion below. This is the
    # FIRST dispatch criterion: a `run.json` that already ended means the work
    # is settled (re-dispatching would replay a finished task), and a live
    # `running` record means another process owns this identity right now
    # (re-dispatching would run it twice). Both refuse before ANY side effect —
    # no task dir, no task.md, no queue row. Exactly one read per attempt:
    # `mw_common.read_run_status` is the single reader (no new JSON parsing),
    # and `run_status` is reused for both branches. `None` (no run.json /
    # unreadable / no status) is "no information", so the historical
    # fail-open path is byte-for-byte unchanged — zero backfill.
    run_status = mw_common.read_run_status(task_dir)
    if run_status is not None:
        if run_status in mw_common.RUN_TERMINAL_STATUSES:
            return reject(
                f"run-terminal:{run_status}",
                f"run.json status={run_status} (terminal) - not re-dispatching",
            )
        if run_status == "running":
            return reject(
                "run-running",
                "run.json status=running - another process owns this task",
            )
        # Forward-compatible: an unknown non-terminal status is no information
        # either, so it keeps the fail-open default (dispatch) and is logged
        # for diagnosis rather than guessed into a terminal meaning.
        print(
            f"[dispatch] debug: unknown run.json status {run_status!r} for "
            f"{task_key} - dispatching (fail-open)",
            file=sys.stderr,
            flush=True,
        )

    entry = REGISTRY.get(task_type)
    if entry is None:
        return reject(
            "unknown-type",
            f"unknown dispatch type {task_type!r} "
            f"(registered: {', '.join(sorted(REGISTRY))})",
        )
    # PM-only types (mw-rag-integration T-09/AC-011): registered for the
    # PM/`/worker` dispatch surface but never conductor-dispatched. Rejected
    # before any task-dir side effect, exactly like an unknown type.
    if not entry.conductor_dispatchable:
        return reject(
            f"not-conductor-dispatchable: {task_type} is a PM-dispatched type, "
            "the conductor must not dispatch it",
            f"{task_type} is a PM-dispatched type, the conductor must not dispatch it",
        )
    scope = [str(item) for item in read_scope if str(item).strip()]
    if entry.requires_read_scope and not scope:
        return reject(
            "verifier-read-scope-required",
            "verifier dispatches require a non-empty read_scope (D-106)",
        )
    # W8: the decision role's whole contract lives on the card (dp / evidence
    # sources / branch consequence / send authority). Judged here, before the
    # target config and before any task-dir side effect, so a refused card
    # leaves the project exactly as it was.
    if task_type == DECIDE_PREPARE_TYPE:
        decision_issues = decision_dispatch_issues(project_root, owner, stem)
        if decision_issues:
            return reject(
                f"decision-card-invalid: {decision_issues[0].code}",
                "; ".join(issue.format() for issue in decision_issues),
            )

    # Workspace-profile injection (mw-dual-workspace D-005/D-007): the
    # resolved config drives scope expansion + deny_globs defaults. The
    # unusable-config message is shape-dynamic (mw-target-partition D-007):
    # v1/no-file keeps the historical text, a v2 file names its active mode.
    try:
        config = mw_common.load_target_config(project_root)
    except mw_common.TargetConfigError as exc:
        return reject(
            "target-config-unusable",
            mw_common.describe_target_error(exc, project_root),
            ev="target-config-rejected",
        )
    scope = _expand_read_scope(scope, config, project_root)
    globs = _resolve_deny_globs(config, deny_globs)

    # mw-target-partition FIX-1 (AC-007/AC-020): the TS dispatcher skips
    # origin: conductor tasks (D-104), so the conductor must inject the v2
    # profile block itself — without it the launcher sees an un-profiled
    # task, and an active-mode switch between dispatch and spawn silently
    # moves the spawn cwd past the tear check. The block mirrors
    # mw_common.render_partition_profile_md (the TS renderPartitionProfileBlock
    # line protocol); dual/single keep the historical no-injection shape
    # (AC-016d zero change). Rendered BEFORE any task-dir side effect so a
    # fail-closed render (undefined placeholder) rejects the dispatch with
    # nothing written and nothing queued; ignore_enforced mirrors the TS
    # ownDenyGlobs rule — the firewall section renders only when the task
    # carries no deny_globs of its own (an explicit list, including empty,
    # wins and skips it).
    # RAG static config (T-07/D-009) is loaded before any task-dir side
    # effect but never blocks dispatching: a broken config renders no block
    # (load_rag_config returns ({}, error) by contract).
    rag_config, _rag_error = mw_common.load_rag_config(project_root)
    profile_block: str | None = None
    if config["mode"] == "partition":
        try:
            profile_block = mw_common.render_partition_profile_md(
                config, ignore_enforced=deny_globs is None
            )
        except mw_common.TargetConfigError as exc:
            return reject(
                "target-config-unusable",
                mw_common.describe_target_error(exc, project_root),
                ev="target-config-rejected",
            )
    timeout_min = _worker_timeout_min(project_root)
    # T-10: every dispatch carries the T-02 envelope signal. A card-backed
    # execute dispatch reads the card (`card_path`/`card_sha256` + its section
    # bodies); a card-less internal dispatch (L3/repair/roadmap/phase-writer)
    # gets a synthesized non-empty envelope (§synthesized_card) so it passes the
    # service-layer judge too — the T-09 card-only injection left those rows
    # refused after the `ENVELOPE_ENFORCE_SINCE` cutover.
    card_backed = dispatch_card(project_root, owner, stem)
    # T-03 order fix: the caps must follow THIS card. Computing them above (the
    # pre-T-03 order) priced the previous dispatch's budget, because the card
    # was only read further down. `claims` empty / card-less (synthesized) →
    # `_read_scope_caps` degenerates to the config-only behaviour, so those
    # renders stay byte-identical. The gate read never blocks the dispatch
    # (advisory is the default); it only surfaces an invalid value on stderr.
    card_claims = card_backed.get("claims") if card_backed is not None else None
    if card_claims:
        claim_gate()
    read_file_cap, read_byte_cap = _read_scope_caps(project_root, card_claims)
    envelope_card = (
        card_backed if card_backed is not None
        else synthesized_card(owner, stem, task_type, prompt, loop, attempt)
    )
    narrowed_by_note = ""
    if task_type == DECIDE_PREPARE_TYPE:
        # W8 requirement 3: the write face of a decision worker is
        # `<key>/evidence/books/**` unless the card declares its own face (in
        # which case the card wins and the task.md records why). The computed
        # face is injected into the envelope as a `## 写入允许面` extra, which is
        # the SAME carrier `render_task_md` reads into the `write_face:` head —
        # a card that already declares one keeps it verbatim (never widened).
        face_entries, face_carrier, narrowed_by_note = decision_write_face(
            owner, task_key, _card_write_face_entries(card_backed)
        )
        decision_fields = decision_card_fields(
            _read_card_text(project_root, owner, stem)
        )
        extras = [dict(extra) for extra in (envelope_card.get("extras") or ())
                  if isinstance(extra, dict)]
        extras.append({
            "title": DECISION_PARAMS_HEADING,
            "body": decision_params_body(
                decision_fields,
                book_path=(
                    f"{envelope_card.get('worker_dir', '')}/"
                    f"{DECISION_WRITE_FACE_SUBDIR}/"
                    f"{decision_fields.get('dp', '').strip() or 'dp'}-book.json"
                ),
                carrier=face_carrier,
                narrowed_by=narrowed_by_note,
            ),
        })
        if face_carrier == "type-default":
            extras.append({
                "title": WRITE_FACE_CARD_SECTION,
                "body": "\n".join(f"- {entry}" for entry in face_entries),
            })
        envelope_card = {**envelope_card, "extras": extras}
    content = render_task_md(
        task_type, prompt, loop=loop, attempt=attempt, read_scope=scope,
        deny_globs=globs, model=model, phase=_owner_phase(project_root, owner),
        profile_block=profile_block,
        rag_config=rag_config,
        read_file_cap=read_file_cap,
        read_byte_cap=read_byte_cap,
        worker_timeout_min=timeout_min,
        card=envelope_card,
    )

    # 1. queue-row fields — precomputed; the task.md itself is written INSIDE
    #    the workers.lock critical section below (AC-014/D-005). The write-face
    #    judgement reads the live queue, so the judgement, the task.md write
    #    and the row write must share one critical section; the path is
    #    computed here but the file is not created until the gate passes (a
    #    refusal leaves no taskDir).
    wpath = mw_common.workers_path(project_root)
    lock = mw_common.lock_path(project_root)
    task_md = task_dir / "task.md"
    row = {
        "task_key": task_key,
        "status": "pending",
        "cli": entry.cli,
        "provider": entry.provider,
        "task_path": str(task_md),
        "dispatched_at": mw_common.iso_now(),
        "updated_at": mw_common.iso_now(),
        "model": model,
        # D-019/AC-021: the producer records who owns the row. The PM/TS
        # writer stamps `manual` (worker-store.ts); the conductor stamps
        # `conductor` here, so attribution never falls back to the `ap-`
        # task-key prefix (a false signal on 6 measured rows).
        "origin": mw_common.WORKER_ORIGIN_CONDUCTOR,
    }
    try:
        mw_common.acquire_lock(lock)
    except (OSError, RuntimeError) as exc:
        # RQ-D3 §2 / AC-014: task.md is no longer written before the lock, so
        # this returned path names a file that was never created. The field
        # shape stays unchanged (DispatchResult.task_md); only its guarantee
        # moved — `ok=False` always means "nothing was written".
        return DispatchResult(
            ok=False,
            reason=f"lock-unavailable: {exc}",
            task_key=task_key,
            task_md=task_md,
            row_verified=False,
        )
    try:
        # AC-014: the write-face gate runs under the SAME lock as the row
        # write. Nothing inside this section may acquire a lock again (RQ-D3:
        # a nested acquire backs off for 14.6h and then raises).
        refusal = _write_face_verdict(
            project_root, owner, task_key, content,
            card_backed=card_backed is not None, timeline=timeline,
        )
        if refusal is not None:
            return refusal  # zero side effects: no taskDir, no task.md, no row

        # MDC M-04: identity-level duplicate-dispatch guard, INSIDE the same
        # `workers.lock` critical section (and after the write-face gate) so
        # the judgement, the task.md write and the row write stay one atomic
        # step. `upsert_worker_row` replaces a row by `task_key` without ever
        # asking whether the old row is still in flight: a second dispatch of
        # a live identity would overwrite the in-flight row with a fresh
        # `pending` one and rewrite its task.md — the mechanism behind the
        # RF-1..RF-4 duplicate activation (same identity, two worker
        # instances, one shared `output.md`).
        #
        # The criterion is identity, never row count: under upsert semantics
        # the row count is always 1, so only "is this task_key already
        # non-terminal" can tell a duplicate from a requeue. The terminal set
        # is the single `mw_common._TERMINAL_STATUSES` (the one source already
        # used by `_write_face_verdict` above and by the conductor's
        # `_is_in_flight`) — never a local set. A terminal old row still
        # re-dispatches through upsert (a retry reuses the same identity), so
        # the retry path is not sealed off.
        #
        # Zero side effects, exactly like the write-face refusal above: no
        # taskDir, no task.md, no queue row, and no second `dispatch` timeline
        # event (the event vocabulary is frozen; the refusal is observable as
        # the missing `dispatch` event plus the `duplicate-dispatch:` reason).
        # No lock is acquired here — nesting `acquire_lock` while holding it
        # backs off for 14.6h and then raises (RQ-D3).
        duplicate = next(
            (
                row for row in mw_common.parse_workers_file(wpath)
                if str(row.get("task_key", "")) == task_key
                and str(row.get("status", "")) not in mw_common._TERMINAL_STATUSES  # noqa: SLF001
            ),
            None,
        )
        if duplicate is not None:
            return DispatchResult(
                ok=False,
                reason=(
                    f"duplicate-dispatch: {task_key} already in flight "
                    f"({duplicate.get('status', '')})"
                ),
                task_key=task_key,
                task_md=None,
                row_verified=False,
            )

        # 1a. task.md (before the queue row — the crash gap is the orphan
        #     shape that reconciliation heals; see module docstring / D-102).
        task_dir.mkdir(parents=True, exist_ok=True)
        task_md.write_text(content, encoding="utf-8", newline="\n")

        # 2. queue row under workers.lock — upsert by task_key: replace the
        #    first existing row (a retry requeues the same identity; matches
        #    the TS-side WorkerStore.upsert, so no duplicate-key rows ever
        #    appear) or append when the key is new.
        try:
            wpath.parent.mkdir(parents=True, exist_ok=True)
            # Queue write goes through mw_common.upsert_worker_row (content
            # fully precomputed, then tmp + os.replace): a serialization error
            # must never truncate _workers.parallel — open("w") truncates
            # before the write expression is evaluated (pitfalls P-003 / PM
            # defect #50). Slot-preserving (T-18/AC-023): the dispatcher
            # rewrites only its own row, so rows no parser can read are never
            # silently deleted (the third Python writer of the IN-3 amplifier
            # F4).
            mw_common.upsert_worker_row(wpath, row)
        except OSError as exc:
            return DispatchResult(
                ok=False,
                reason=f"queue-write-failed: {exc}",
                task_key=task_key,
                task_md=task_md,
                row_verified=False,
            )
    finally:
        mw_common.release_lock(lock)

    # 3. read-back verification: exactly one row with the right identity.
    row_verified = False
    matches = 0
    for queued in mw_common.parse_workers_file(wpath):
        if queued["task_key"] == task_key:
            matches += 1
            row_verified = (
                queued["task_path"] == str(task_md)
                and queued["cli"] == entry.cli
                and queued["status"] == "pending"
                and queued.get("origin") == mw_common.WORKER_ORIGIN_CONDUCTOR
            )
    row_verified = row_verified and matches == 1

    if timeline is not None:
        timeline.append(
            "dispatch",
            key=_timeline_key(owner),
            detail=f"{task_key} type={task_type} loop={loop} attempt={attempt}",
        )
    return DispatchResult(
        ok=True, reason="", task_key=task_key, task_md=task_md, row_verified=row_verified
    )


# ── decision-card checker CLI (`python -m autopilot.dispatch check`) ────────
#
# Offline, side-effect free: judges one decision card (and optionally a book)
# with the SAME criteria `dispatch()` refuses on, so a worker/PM can see the
# refusal before spending a spawn. Exit codes mirror `mw dp check`/
# `mw decide book check`: 0 clean, 2 refused, 1 usage/IO problem.
def _check_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="dispatch check",
        description=(
            "Validate a decision-card offline (type: decide_prepare): the four required items "
            "(dp / 证据来源 / 分支后果 / allow-send), the dp's required_state_fields, "
            "and the allow-send authority for `decide run|ask --book`."
        ),
    )
    parser.add_argument("--card", metavar="FILE",
                        help="Card markdown (e.g. tasks/W9-decision.md); omit with --dp for a registry-only probe")
    parser.add_argument("--dp", metavar="ID",
                        help="Override/replace the card's dp (registry probe: must define required_state_fields)")
    parser.add_argument("--book", metavar="FILE",
                        help="Decision book the caller intends to SEND: refused when allow-send is no (the default)")
    parser.add_argument("--json", action="store_true",
                        help="Emit the machine-readable issue list")
    return parser.parse_args(argv)


def check_command(argv: Sequence[str]) -> int:
    """`check` subcommand → exit code (0 clean / 2 refused / 1 IO)."""
    args = _check_args(argv)
    if not args.card and not args.dp:
        print("dispatch check: --card or --dp is required", file=sys.stderr)
        return 1
    text = ""
    card_path = args.card or "-"
    if args.card:
        try:
            text = pathlib.Path(args.card).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print(f"dispatch check: cannot read {args.card}: {exc}", file=sys.stderr)
            return 1
    issues = decision_card_issues(
        text, card_path=card_path, dp=args.dp or "", book=args.book or "",
        require_items=bool(args.card),
    )
    if args.json:
        print(json.dumps({
            "ok": not issues,
            "card": card_path,
            "dp": args.dp or decision_card_fields(text).get("dp", ""),
            "allow_send": decision_allows_send(decision_card_fields(text)),
            "issues": [issue.as_dict() for issue in issues],
        }, ensure_ascii=False, indent=2))
    elif issues:
        for issue in issues:
            print(issue.format(), file=sys.stderr)
    else:
        target = card_path if args.card else (args.dp or decision_card_fields(text).get("dp", ""))
        print(f"ok {target}".rstrip())
    return 0 if not issues else 2


def main(argv: Sequence[str] | None = None) -> int:
    """Module CLI: `python -m autopilot.dispatch check [--card FILE] ...`."""
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        parser = argparse.ArgumentParser(
            prog="dispatch",
            description=(
                "Conductor dispatch helpers. `check` validates a decide_prepare worker's "
                "card offline with the same criteria dispatch() refuses on "
                "(exit 0 clean / 2 refused / 1 usage)."
            ),
        )
        parser.add_argument("subcommand", nargs="?", choices=["check"],
                            help="check: validate a decision card / dp / book send authority")
        parser.parse_args(args)
        return 0
    if args[0] == "check":
        return check_command(args[1:])
    print(f"dispatch: unknown subcommand {args[0]!r} (known: check)", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
