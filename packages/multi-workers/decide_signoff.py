"""Decision sign-off: archive facts -> verdict -> ``evidence/review/sign-final.md``.

FIX-P implements the two halves the 2026-10-21 decision settled on:

* **(a) the command** - ``mw decide sign`` prints the key's decision summary and
  writes ``<key>/evidence/review/sign-final.md`` plus one
  ``kind=authority-change`` archive row. The conclusion comes from the decision
  model only; the machine lines (``counted_rows`` / ``rows_sha256``) are
  computed here, never typed.
* **(b) the gate** - ``advance_phase.py``'s ``decision_signoff`` check runs
  unconditionally and skips keys with no raw ``kind=decide`` row; when it does
  run it recomputes :func:`collect` and compares ``rows_sha256``, so a signed
  file stops matching the moment the archive is appended to or rewritten.

Everything here is a pure function over the authoritative archive
(``.agenticdoc/_autopilot/decisions.jsonl``, :mod:`decide_archive`) and the
authorization table (``.mw/decide-points.json``, :mod:`decision_points`); the
only writer is :func:`write_signoff`.

The 2026-10-21 ruling (spec §15 / design D-064..D-071) moved the authority for
the conclusion from a human to the decision model, and the 2026-10-22 ruling
(spec §2 / design §3) removed every other face: there is exactly one path.

* **auto-decide** - :func:`auto_conclusion` folds the *same* :func:`collect`
facts into the ``dp25-signoff-conclusion`` state and asks jev for
``continue|narrow|revoke`` (``intent="answer"``, nothing is executed).
* no conclusion from the caller, no LLM fallback, no human path: when jev is
unavailable nothing is written and no sign-off is required.

The write-side ``signed_via`` vocabulary is therefore just ``auto-decide``.
The read side (:mod:`decision_history`) still accepts the historical values
``auto-llm`` / ``cli`` / ``tui`` so archived sign-offs are not re-classified.

The evidence file ``.agenticdoc/_autopilot/triage-decisions.jsonl`` is
deliberately *not* read: it carries no ``key`` column, so it cannot be grouped
per key (FIX-P card, 事实依据).
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import pathlib
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import decide_archive
import decision
import decision_points
import decision_signoff_result

__all__ = [
    "AGENT_SESSION_ENV_VARS",
    "CONCLUSIONS",
    "SIGNOFF_DP_ID",
    "SIGNOFF_RELATIVE_PATH",
    "SIGNED_VIA_VALUES",
    "TRUE_ENGINE",
    "SignoffError",
    "SignoffFacts",
    "agent_session_vars",
    "archive_path",
    "auto_conclusion",
    "collect",
    "key_dir",
    "parse_signoff",
    "render",
    "rows_sha256",
    "signoff_path",
    "signoff_state",
    "verdict",
    "write_signoff",
]

#: ``<key>/evidence/review/sign-final.md`` (the only sign-off location the done
#: gate and ``mw decide dp apply`` agree on).
SIGNOFF_RELATIVE_PATH = pathlib.Path("evidence") / "review" / "sign-final.md"
#: The conclusion vocabulary (shared with ``mw decide dp apply`` / spec §7.2).
CONCLUSIONS = ("continue", "narrow", "revoke")
#: The only engine triple that counts as "a real jev decision" (FIX-P card).
TRUE_ENGINE = ("timi-decisions", "jev-latest", "api")
#: Field names of :data:`TRUE_ENGINE`, in triple order.
TRUE_ENGINE_FIELDS = ("transport", "model", "confidence_source")
_TRUE_ENGINE_KEY = "/".join(TRUE_ENGINE)
#: Same criterion as ``mw.py::_DP_AGENT_ENV_VARS`` (which now reads this tuple):
#: any of these set means an agent session, and an agent must not sign itself off.
AGENT_SESSION_ENV_VARS = ("PI_CODING_AGENT", "AI_AGENT", "PI_WORKER_TASK")

#: The registered decision point that produces the sign-off conclusion
#: (spec §15 AC-027 / design D-067). P2 (so it is on out of the box, W11),
#: ``default_mode="auto"``, executor ``wired`` but *echo only* (it returns
#: ``signoff:<conclusion>`` and writes nothing): the *write* stays here, the
#: point only answers.
SIGNOFF_DP_ID = "dp25-signoff-conclusion"
#: The ``signed_via`` vocabulary this module may write: the decision model is
#: the only authority, so there is exactly one face. Historical ``auto-llm`` /
#: ``cli`` / ``tui`` files stay readable (``decision_history.py`` keeps its own
#: four-value vocabulary) but are never produced again.
SIGNED_VIA_VALUES = ("auto-decide",)

#: Per-row snapshot the sign-off counts and hashes. Deliberately narrow: adding
#: an unrelated archive column must not invalidate an already-signed file.
_ROW_FIELDS = (
    "seq",
    "dp",
    "available",
    "acted",
    "mode",
    "escalated_reason",
    "transport",
    "model",
    "confidence_source",
    "ts",
)
#: First row of a hash chain (`decide_archive._GENESIS_PREV`).
_GENESIS_PREV = "0" * 16

_MACHINE_LINE_RE = re.compile(
    r"^(conclusion|counted_rows|rows_sha256|engine|allow_empty|key|claim|ts|reason"
    r"|promote|demote|p0-open|signed_via|decide_fallback|record_version|dp|logical_id"
    r"|decision_id|material_sha256|evidence_sha256|snapshot_sha256|initiator_role"
    r"|retry_of|transport|model|confidence_source):\s*(.*?)\s*$",
    re.MULTILINE,
)


class SignoffError(ValueError):
    """Sign-off refused (unwritable path); the CLI maps this to 2."""


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def _agenticdoc_root(project_dir: pathlib.Path | str) -> pathlib.Path:
    """The ``.agenticdoc`` dir for a project root, that dir itself, or a key dir."""
    path = pathlib.Path(project_dir)
    if path.name == ".agenticdoc":
        return path
    if path.parent.name == ".agenticdoc":  # the argument IS the key dir
        return path.parent
    return path / ".agenticdoc"


def _control_root(project_dir: pathlib.Path | str) -> pathlib.Path:
    """Where ``.mw/decide-points.json`` lives (the parent of ``.agenticdoc``)."""
    return _agenticdoc_root(project_dir).parent


def key_dir(project_dir: pathlib.Path | str, key: str) -> pathlib.Path:
    path = pathlib.Path(project_dir)
    if path.parent.name == ".agenticdoc" and path.name == key:
        return path
    return _agenticdoc_root(project_dir) / key


def signoff_path(project_dir: pathlib.Path | str, key: str) -> pathlib.Path:
    return key_dir(project_dir, key) / SIGNOFF_RELATIVE_PATH


def _archive_path(project_dir: pathlib.Path | str) -> pathlib.Path:
    # `.agenticdoc/_autopilot/decisions.jsonl`, reuse the archive layer's name.
    return _agenticdoc_root(project_dir) / pathlib.Path(
        *decide_archive.ARCHIVE_RELATIVE_PATH.parts[1:]
    )


def archive_path(project_dir: pathlib.Path | str) -> pathlib.Path:
    """The authoritative archive path (``<project>/.agenticdoc/_autopilot/...``)."""
    return _archive_path(project_dir)


# ---------------------------------------------------------------------------
# Facts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SignoffFacts:
    """Everything the verdict/render/gate need, computed once from the archive."""

    key: str
    archive: str
    rows: tuple[dict[str, Any], ...]
    n_available: int
    n_acted: int
    n_escalated: int
    engines: dict[str, int]
    sha256: str
    chain_ok: bool
    p0_open: tuple[str, ...] = ()
    p0_source: str = "missing"  # "missing" = no `.mw/decide-points.json`

    def as_dict(self) -> dict[str, Any]:
        """JSON-safe view (``mw decide sign --json`` facts)."""
        return {
            "key": self.key,
            "archive": self.archive,
            "counted_rows": len(self.rows),
            "n_available": self.n_available,
            "n_acted": self.n_acted,
            "n_escalated": self.n_escalated,
            "engines": dict(self.engines),
            "sha256": self.sha256,
            "chain_ok": self.chain_ok,
            "p0_open": list(self.p0_open),
            "p0_source": self.p0_source,
            "rows": [dict(row) for row in self.rows],
        }


def _engine_part(value: object) -> str:
    return value if isinstance(value, str) and value else "-"


def _engine_key(row: Mapping) -> str:
    return "/".join(_engine_part(row.get(name)) for name in TRUE_ENGINE_FIELDS)


def _row_matches_key(row: Mapping, key: str) -> bool:
    """``key`` column, else the ``:<key>`` suffix of ``decision_id`` (card rule)."""
    if row.get("key") == key:
        return True
    decision_id = row.get("decision_id")
    if not key or not isinstance(decision_id, str):
        return False
    return decision_id.endswith(":" + key)


def _canonical_rows_bytes(rows: Iterable[Mapping]) -> bytes:
    return json.dumps(
        list(rows),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8", errors="replace")


def rows_sha256(rows: Iterable[Mapping]) -> str:
    """``sha256(canonical(row list))`` over the counted snapshots (full hex)."""
    return hashlib.sha256(_canonical_rows_bytes(rows)).hexdigest()


def _chain_ok(rows: Iterable[Mapping]) -> bool:
    """``seq`` from 1 contiguous + ``prev_sha`` closed over the whole archive.

    Chain definition reused from :mod:`decide_archive` (``_row_sha`` /
    ``_GENESIS_PREV``) so the two sides cannot drift apart.
    """
    previous: Mapping | None = None
    expected = 1
    for row in rows:
        seq = row.get("seq")
        if not isinstance(seq, int) or isinstance(seq, bool) or seq != expected:
            return False
        if previous is None:
            if row.get("prev_sha") != _GENESIS_PREV:
                return False
        elif row.get("prev_sha") != decide_archive._row_sha(previous):
            return False
        previous = row
        expected += 1
    return True


def _p0_open(project_dir: pathlib.Path | str) -> tuple[tuple[str, ...], str]:
    """``(enabled P0 ids, source)``; ``source="missing"`` when the table is absent."""
    control = _control_root(project_dir)
    path = decision_points.decide_points_config_path(control)
    if not path.is_file():
        return (), "missing"
    config = decision_points.load_points_config(control)
    ids = tuple(
        sorted(
            point.id
            for point in decision_points.DP_REGISTRY
            if point.tier == "P0" and config.effective(point).enabled
        )
    )
    return ids, "config"


def collect(project_dir: pathlib.Path | str, key: str) -> SignoffFacts:
    """Read the archive and fold this key's ``kind=decide`` rows into facts.

    Reads ``<project>/.agenticdoc/_autopilot/decisions.jsonl`` (missing file =
    zero rows, not an error) and ``<project>/.mw/decide-points.json`` for the
    open-P0 list. ``project_dir`` may be the project root, the ``.agenticdoc``
    dir, or the key dir itself.
    """
    key = key or ""
    archive = _archive_path(project_dir)
    all_rows = [row for _lineno, row in decide_archive.iter_rows(archive)]
    counted = [
        row
        for row in all_rows
        if row.get("kind") == "decide"
        and _row_matches_key(row, key)
        # The sign-off's own decision rows are excluded (D-067): the signature
        # covers the decisions being signed off, and counting the advice that
        # produced it would let a `continue` justify itself (N>=1 + true engine)
        # and would make every re-sign move `rows_sha256` for no evidence gain.
        and row.get("dp") != SIGNOFF_DP_ID
    ]
    counted.sort(
        key=lambda row: row.get("seq") if isinstance(row.get("seq"), int) else 0
    )
    snapshots = [{name: row.get(name) for name in _ROW_FIELDS} for row in counted]

    engines: dict[str, int] = {}
    for row in snapshots:
        engine = _engine_key(row)
        engines[engine] = engines.get(engine, 0) + 1
    p0_open, p0_source = _p0_open(project_dir)
    return SignoffFacts(
        key=key,
        archive=str(archive),
        rows=tuple(snapshots),
        n_available=sum(1 for row in snapshots if row.get("available") is True),
        n_acted=sum(1 for row in snapshots if row.get("acted") is True),
        n_escalated=sum(
            1 for row in snapshots if row.get("escalated_reason") is not None
        ),
        engines=dict(sorted(engines.items())),
        sha256=rows_sha256(snapshots),
        chain_ok=_chain_ok(all_rows),
        p0_open=p0_open,
        p0_source=p0_source,
    )


# ---------------------------------------------------------------------------
# Facts -> dp25 state -> conclusion (spec §15 AC-024/AC-027, design D-067)
# ---------------------------------------------------------------------------


def signoff_state(
    facts: SignoffFacts, key: str | None = None
) -> dict[str, Any]:
    """Deterministic ``dp25-signoff-conclusion`` state from :func:`collect` facts.

    Only archive-derived facts go in (D-067): no diff, no code, no document is
    read here, so the model judges the same numbers :func:`verdict` checks. The
    required paths are exactly ``REQUIRED_STATE_FIELDS[SIGNOFF_DP_ID]``; the
    optional ones are the escalation vocabulary (``escalated_reasons``), the
    count behind it (``rows_escalated``) and the off-triple engines seen in the
    rows (``engine_violations``).
    """
    engine_violations = sorted(
        {_engine_key(row) for row in facts.rows if _engine_key(row) != _TRUE_ENGINE_KEY}
    )
    escalated_reasons = sorted(
        {
            str(row.get("escalated_reason"))
            for row in facts.rows
            if isinstance(row.get("escalated_reason"), str)
            and row.get("escalated_reason")
        }
    )
    state: dict[str, Any] = {
        "schema_version": 2,
        "decision_point": SIGNOFF_DP_ID,
        "questions_version": decision_points.get_decision_point(
            SIGNOFF_DP_ID
        ).questions_version,
        "key": facts.key or (key or ""),
        "rows_total": len(facts.rows),
        "rows_available": facts.n_available,
        "chain_ok": facts.chain_ok,
        "p0_open": list(facts.p0_open),
        "rows_escalated": facts.n_escalated,
        "escalated_reasons": escalated_reasons,
        "engine_violations": engine_violations,
    }
    return state


def auto_conclusion(
    project_dir: pathlib.Path | str,
    key: str,
    *,
    facts: SignoffFacts | None = None,
) -> tuple[str | None, str]:
    """Ask ``dp25-signoff-conclusion`` for ``continue|narrow|revoke``.

    Returns ``(conclusion, detail)``; ``(None, reason)`` means "fall back to the
    LLM path and record ``decide_fallback: <reason>``" (D-069): no
    ``.mw/decide.json`` / not enabled, ``dp25`` not registered or disabled in
    ``.mw/decide-points.json``, transport unavailable, low confidence, or an
    answer outside the conclusion vocabulary. Zero HTTP on every refusal that
    ``decide_for`` escalates before the transport call.

    ``project_dir`` may be the project root, the ``.agenticdoc`` dir or the key
    dir (``.mw/decide.json`` always lives at the control root, i.e. the parent of
    ``.agenticdoc``).
    """
    root = _control_root(project_dir)
    observed = facts if facts is not None else collect(project_dir, key)
    cfg, cfg_error = decision.DecisionConfig.from_project(root)
    if not cfg.is_configured:
        return None, cfg_error or (
            "decide unavailable (.mw/decide.json missing or enabled=false)"
        )
    try:
        point = decision_points.get_decision_point(SIGNOFF_DP_ID)
    except decision.DecisionInputError:
        return None, f"{SIGNOFF_DP_ID} is not registered"
    points = decision_points.load_points_config(root)
    if not points.effective(point).enabled:
        return None, f"{SIGNOFF_DP_ID} disabled in .mw/decide-points.json"
    state = signoff_state(observed, key)
    trigger = decision_points.Trigger.from_mapping(
        state,
        key=state["key"],
        trigger_id=f"{state['key'] or 'signoff'}@{_now_ts()}",
    )
    outcome = decision_points.decide_for(
        SIGNOFF_DP_ID,
        trigger,
        root,
        config=cfg,
        points_config=points,
        intent="answer",
    )
    if outcome.status != "suggested":
        reason = outcome.escalated_reason or outcome.status
        return None, f"{reason}: {outcome.detail}"
    answers = outcome.answer or {}
    item = answers.get("q-conclusion")
    value = item.get("value") if isinstance(item, Mapping) else item
    if value not in CONCLUSIONS:
        return None, f"unusable answer q-conclusion={value!r}"
    confidence = item.get("confidence") if isinstance(item, Mapping) else None
    source = outcome.confidence_source or "unknown"
    return str(value), (
        f"{SIGNOFF_DP_ID} decision_id={outcome.decision_id} "
        f"confidence={confidence if confidence is not None else '-'} source={source}"
    )


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------


def verdict(
    facts: SignoffFacts, conclusion: str, *, allow_empty: bool = False
) -> tuple[bool, list[str]]:
    """``(ok, problems)`` for one conclusion (the (b) gate's content check).

    ``continue`` needs N>=1 available rows, an intact hash chain and *every*
    counted row on the real jev triple; ``narrow``/``revoke`` only need the
    chain (they take authority away, so N=0 is legal). ``allow_empty`` only
    waives the ``continue`` N=0 rule (``mw decide sign --allow-empty``); the
    gate never passes it, so an empty ``continue`` cannot clear ``done``.
    """
    problems: list[str] = []
    if conclusion not in CONCLUSIONS:
        return False, [
            f"invalid conclusion {conclusion!r} (must be one of {'|'.join(CONCLUSIONS)})"
        ]
    if not facts.chain_ok:
        problems.append(
            "archive hash chain is broken (seq not contiguous from 1 or prev_sha "
            "does not close); the archive was appended to outside decide_archive"
        )
    if conclusion != "continue":
        return (not problems), problems

    if facts.n_available < 1 and not allow_empty:
        if not facts.rows:
            problems.append(
                "N=0: no decide row for this key in the archive; run a real jev "
                "decision first, or sign narrow/revoke"
            )
        else:
            problems.append(
                f"N=0: {len(facts.rows)} decide row(s) for this key but none is "
                "available (every one escalated); run a real jev decision first, "
                "or sign narrow/revoke"
            )
    for row in facts.rows:
        engine = _engine_key(row)
        if engine != _TRUE_ENGINE_KEY:
            problems.append(
                f"engine mismatch at seq {row.get('seq')} (dp={row.get('dp')}): "
                f"{engine} != {_TRUE_ENGINE_KEY} (only the real jev transport counts)"
            )
    return (not problems), problems


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------


def _now_ts() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _counts_by(rows: Iterable[Mapping], name: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = row.get(name)
        label = value if isinstance(value, str) and value else "-"
        counts[label] = counts.get(label, 0) + 1
    return counts


def render(
    facts: SignoffFacts,
    conclusion: str,
    reason: str | None,
    key: str,
    claim: str | None,
    *,
    allow_empty: bool = False,
    ts: str | None = None,
    signed_via: str | None = "auto-decide",
    decide_fallback: str | None = None,
    result: decision_signoff_result.SignoffResult | None = None,
) -> str:
    """Markdown sign-off file: column-0 machine lines + the human tables.

    ``result`` is the minimal dp25 result record of the new ``sign --stdin``
    path. When present, the file carries the exact ``logical_id`` + snapshot it
    signs (``decision_signoff_result.validate_signoff`` is the reader). The
    legacy count-based fields stay untouched for old call sites, so already
    signed files keep parsing and the done gate sees the same shape it always
    did.

    ``conclusion:`` is written at column 0 on its own line because the done
    gate matches ``(?m)^conclusion:\\s*(continue|narrow|revoke)\\s*$``;
    ``promote`` / ``demote`` / ``p0-open`` are the machine lines the existing
    ``mw decide dp apply`` parser consumes (``sign`` never widens authority, so
    both lists stay ``-``; ``p0-open`` echoes the currently enabled P0 set, as
    ``apply`` requires an exact match).

    ``signed_via`` (always ``auto-decide`` now) and the legacy
    ``decide_fallback`` column are machine lines too (column 0, ``name: value``)
    so :func:`parse_signoff` reads them back without a second parser and old
    files keep parsing; ``mw decide dp apply`` ignores unknown names.
    """
    p0_machine = ", ".join(facts.p0_open) if facts.p0_open else "-"
    if facts.p0_source == "missing":
        p0_human = "none (.mw/decide-points.json 缺失)"
    elif facts.p0_open:
        p0_human = ", ".join(facts.p0_open)
    else:
        p0_human = "-"

    lines = [
        f"# 决策签收 / Decision sign-off: {key or '-'}",
        "",
        "> 由 `mw decide sign` 生成的人类签收记录；`conclusion:` 等机器行为列 0 单行。",
        "> done 门禁（`advance_phase.py` 的 `decision_signoff` 检查）对该 key 无条件执行",
        "> （无 `kind=decide` 行时跳过），并按 `rows_sha256` 重算比对档案。",
        "",
        f"conclusion: {conclusion}",
        f"counted_rows: {len(facts.rows)}",
        f"rows_sha256: {facts.sha256}",
        f"engine: {_TRUE_ENGINE_KEY}",
        f"allow_empty: {'true' if allow_empty else 'false'}",
        f"key: {key or '-'}",
        f"claim: {claim or '-'}",
        f"ts: {ts or _now_ts()}",
        f"reason: {reason or '-'}",
        "promote: -",
        "demote: -",
        f"p0-open: {p0_machine}",
    ]
    if result is not None:
        # New (approved) snapshot association. The row hash above is part of the
        # snapshot, so an archive append after the model call also invalidates
        # this conclusion. No second approval is implied by any of these lines.
        if result.rows_sha256 and result.rows_sha256 != facts.sha256:
            raise SignoffError(
                "sign-off snapshot does not match the archive it describes"
            )
        lines += [
            f"record_version: {result.record_version}",
            f"dp: {result.dp}",
            f"logical_id: {result.logical_id}",
            f"decision_id: {result.decision_id}",
            f"material_sha256: {result.material_sha256}",
            f"evidence_sha256: {result.evidence_sha256}",
            f"snapshot_sha256: {result.snapshot_sha256}",
            f"initiator_role: {result.initiator_role or 'unknown'}",
            f"retry_of: {result.retry_of or '-'}",
        ]
        for name in ("transport", "model", "confidence_source"):
            value = getattr(result, name)
            if isinstance(value, str) and value:
                lines.append(f"{name}: {value}")
    if signed_via:
        lines.append(f"signed_via: {signed_via}")
    if decide_fallback:
        # One physical line only: the reason carries an escalated detail, and a
        # newline would forge a second machine line.
        lines.append("decide_fallback: " + " ".join(str(decide_fallback).split()))
    lines += [
        "",
        "## 计数表（按 dp）",
        "",
        "| dp | rows | available | acted | escalated |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    by_dp: dict[str, list[Mapping]] = {}
    for row in facts.rows:
        dp = row.get("dp")
        label = dp if isinstance(dp, str) and dp else "-"
        by_dp.setdefault(label, []).append(row)
    if by_dp:
        for dp in sorted(by_dp):
            group = by_dp[dp]
            lines.append(
                f"| {dp} | {len(group)} | "
                f"{sum(1 for r in group if r.get('available') is True)} | "
                f"{sum(1 for r in group if r.get('acted') is True)} | "
                f"{sum(1 for r in group if r.get('escalated_reason') is not None)} |"
            )
    else:
        lines.append("| - | 0 | 0 | 0 | 0 |")

    lines += [
        "",
        "## 引擎（transport/model/confidence_source）",
        "",
        "| engine | rows |",
        "| --- | ---: |",
    ]
    if facts.engines:
        lines += [f"| {engine} | {count} |" for engine, count in facts.engines.items()]
    else:
        lines.append(f"| {_TRUE_ENGINE_KEY} | 0 |")

    lines += [
        "",
        "## 上抛原因分布",
        "",
        "| escalated_reason | rows |",
        "| --- | ---: |",
    ]
    escalated = _counts_by(
        (row for row in facts.rows if row.get("escalated_reason") is not None),
        "escalated_reason",
    )
    if escalated:
        lines += [f"| {name} | {count} |" for name, count in sorted(escalated.items())]
    else:
        lines.append("| - | 0 |")

    lines += [
        "",
        "## 已开 P0",
        "",
        p0_human,
        "",
        "## 依据",
        "",
        f"- archive: `{facts.archive}`",
        f"- chain_ok: {'true' if facts.chain_ok else 'false'}",
        f"- p0 source: {facts.p0_source}",
        f"- n_available: {facts.n_available} / counted_rows: {len(facts.rows)}",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Parse / write
# ---------------------------------------------------------------------------


def parse_signoff(text: str) -> dict[str, str]:
    """Machine lines of a sign-off file as ``{name: value}`` (first line wins).

    Only whole-line ``name: value`` forms at column 0 are recognised, matching
    the done gate's anchored regex and ``mw decide dp apply``'s parser.
    """
    found: dict[str, str] = {}
    for match in _MACHINE_LINE_RE.finditer(text):
        found.setdefault(match.group(1), match.group(2))
    return found


def agent_session_vars() -> list[str]:
    """The agent-session env vars that are set right now (empty = human session)."""
    return [name for name in AGENT_SESSION_ENV_VARS if os.environ.get(name)]


def write_signoff(
    project_dir: pathlib.Path | str,
    key: str,
    text: str,
) -> pathlib.Path:
    """Write ``<key>/evidence/review/sign-final.md`` (parents created, atomic).

    No agent-session gate any more (spec §2 / design §3.3): the sign-off is
    written whenever the decision model produced a conclusion, and the authority
    is the decision model rather than the process running the command.
    :data:`AGENT_SESSION_ENV_VARS` stays exported because ``mw.py`` still uses
    it for the ``dp apply`` guard, not for this write.
    """
    # The result module owns the safe atomic publish (parent-chain containment,
    # no symbolic link, temp write, fsync, replace). The file's success is the
    # sign-off success; any logging/feedback failure is reported separately.
    return decision_signoff_result.write_signoff_text(key_dir(project_dir, key), text)
