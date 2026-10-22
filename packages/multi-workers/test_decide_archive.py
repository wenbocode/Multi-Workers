"""test_decide_archive.py — T-03: decision archive writer + fold.

Hermetic pytest suite for ``packages/multi-workers/decide_archive.py`` (key
mw-decision-substitution, AC-006/007). Contract source:
``evidence/research/design-decision-archive-20261019.md`` Q1..Q6.

Coverage map (card T-03 requirement 5):
- chain integrity (seq 1..N, genesis prev_sha, canonical sha of the previous row)
- half-line tail recovery (terminate-and-preserve, never truncate)
- duplicate ``decide`` rejection (and the ``duplicate="existing"`` replay path)
- field validation for all four kinds (Q4 matrix)
- fold merging (group by decision_id, last settle wins, override flag, bad rows)
- two concurrent writers never produce a duplicate seq
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # noqa: E402
import decide_archive  # noqa: E402

MODULE_DIR = pathlib.Path(__file__).parent

QP = "q-0123abcd"
OK_ANSWERS = {"q1": {"value": "yes", "confidence": 0.9}}


def _archive(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / "decisions.jsonl"


def _decide_kwargs(**overrides):
    kwargs = {
        "dp": "dp1",
        "key": "k",
        "task_key": "t",
        "trigger_id": "t",
        "state": {"prompt": "x"},
        "questions_version": QP,
        "available": True,
        "answer": OK_ANSWERS,
        "authority": "advisory",
    }
    kwargs.update(overrides)
    return kwargs


def _read_rows(path: pathlib.Path) -> list[dict]:
    return [row for _lineno, row in decide_archive.iter_rows(path)]


def _canonical_sha(row: dict) -> str:
    payload = json.dumps(
        row, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8", errors="replace")
    return hashlib.sha256(payload).hexdigest()[:16]


def _assert_chain_intact(rows: list[dict]) -> None:
    assert rows, "archive must not be empty"
    assert rows[0]["seq"] == 1
    assert rows[0]["prev_sha"] == decide_archive._GENESIS_PREV
    for expected_seq, row in enumerate(rows, start=1):
        assert row["seq"] == expected_seq, f"seq gap at {row['decision_id']}"
    for previous, current in zip(rows, rows[1:]):
        assert current["prev_sha"] == _canonical_sha(previous)


# ---------------------------------------------------------------------------
# state_digest / iter_rows
# ---------------------------------------------------------------------------


def test_state_digest_reuses_decision_encode_state():
    import decision

    state = {"b": [1, 2], "a": "x"}
    expected = hashlib.sha256(decision._encode_state(state)).hexdigest()[:16]
    assert decide_archive.state_digest(state) == expected
    assert len(expected) == 16


def test_state_digest_is_key_order_independent():
    import decision

    assert decide_archive.state_digest({"a": 1, "b": 2}) == decide_archive.state_digest(
        {"b": 2, "a": 1}
    )
    assert decide_archive.state_digest({"a": 1}) == hashlib.sha256(
        decision._encode_state({"a": 1})
    ).hexdigest()[:16]


def test_iter_rows_reports_physical_line_numbers_and_skips_bad_lines(tmp_path):
    archive = _archive(tmp_path)
    archive.write_text(
        '{"seq": 1}\n'
        "\n"
        "not json\n"
        "[1, 2]\n"
        '{"seq": 2}\n',
        encoding="utf-8",
    )
    assert list(decide_archive.iter_rows(archive)) == [(1, {"seq": 1}), (5, {"seq": 2})]


def test_iter_rows_missing_file_is_empty(tmp_path):
    assert list(decide_archive.iter_rows(_archive(tmp_path))) == []


# ---------------------------------------------------------------------------
# append_decide / chain integrity
# ---------------------------------------------------------------------------


def test_append_decide_writes_full_row_without_raw_state(tmp_path):
    archive = _archive(tmp_path)
    row, created = decide_archive.append_decide(
        archive,
        now="2026-10-20T10:00:00+00:00",
        **_decide_kwargs(state={"prompt": "SECRET-RAW-STATE"}),
    )

    assert created is True
    assert row["kind"] == "decide"
    assert row["seq"] == 1
    assert row["prev_sha"] == decide_archive._GENESIS_PREV
    assert row["decision_id"] == "dp1:t"
    assert row["ts"] == "2026-10-20T10:00:00+00:00"
    assert row["outcome"] == "pending"
    assert row["state_digest"] == decide_archive.state_digest({"prompt": "SECRET-RAW-STATE"})
    assert set(decide_archive._ROW_FIELDS) <= set(row)

    raw = archive.read_text(encoding="utf-8")
    assert "SECRET-RAW-STATE" not in raw
    assert raw.endswith("\n")



def test_decide_row_carries_policy_echo(tmp_path):
    """D-051: the decide row records the effective per-dp policy (disk + reload)."""
    archive = _archive(tmp_path)
    policy = {"min_confidence": 0.5, "max_questions": 4, "timeout_s": 45}
    row, created = decide_archive.append_decide(
        archive, **_decide_kwargs(trigger_id="p1"), policy=policy
    )
    assert created is True
    assert row["policy"] == policy

    reloaded = [row for _, row in decide_archive.iter_rows(archive)]
    assert reloaded[-1]["policy"] == policy
    stats = decide_archive.fold(reloaded).stats
    assert stats.chain_breaks == 0 and stats.seq_breaks == 0


def test_decide_row_policy_is_optional_and_validated(tmp_path):
    archive = _archive(tmp_path)
    row, _ = decide_archive.append_decide(archive, **_decide_kwargs(trigger_id="p2"))
    assert row["policy"] is None

    with pytest.raises(decide_archive.DecisionArchiveError, match="unknown keys"):
        decide_archive.append_decide(
            archive, **_decide_kwargs(trigger_id="p3"), policy={"bogus": 1}
        )
    with pytest.raises(decide_archive.DecisionArchiveError, match="min_confidence"):
        decide_archive.append_decide(
            archive, **_decide_kwargs(trigger_id="p4"), policy={"min_confidence": 1.5}
        )
    with pytest.raises(decide_archive.DecisionArchiveError, match="timeout_s"):
        decide_archive.append_decide(
            archive, **_decide_kwargs(trigger_id="p5"), policy={"timeout_s": 0}
        )


def test_non_decide_kinds_must_not_carry_policy(tmp_path):
    archive = _archive(tmp_path)
    decide_archive.append_decide(archive, **_decide_kwargs(trigger_id="p6"))
    row = dict([row for _, row in decide_archive.iter_rows(archive)][-1])
    for not_applicable in decide_archive._NOT_APPLICABLE["settle"]:
        if not_applicable != "policy":
            row[not_applicable] = None
    row["kind"] = "settle"
    row["policy"] = {"min_confidence": 0.5}
    with pytest.raises(decide_archive.DecisionArchiveError, match="settle row must not carry policy"):
        decide_archive._validate_row(row)

def test_chain_integrity_across_all_four_kinds(tmp_path):
    archive = _archive(tmp_path)
    decide_archive.append_decide(archive, **_decide_kwargs(trigger_id="t1"))
    decide_archive.append_override(
        archive,
        decision_id="dp1:t1",
        dp="dp1",
        key="k",
        override_by="human",
        override_reason="wrong",
        ref_seq=1,
        now="2026-10-20T10:01:00+00:00",
    )
    decide_archive.append_settle(
        archive,
        decision_id="dp1:t1",
        dp="dp1",
        key="k",
        task_key="t",
        outcome="rework",
        settled_by="pm-auto",
        evidence_ref="workers/k/run.json#r1",
        now="2026-10-20T10:02:00+00:00",
    )
    decide_archive.append_authority_change(
        archive,
        dp="dp1",
        key="k",
        by="human",
        change="dp1 enabled=false mode=auto",
        now="2026-10-20T10:03:00+00:00",
    )

    rows = _read_rows(archive)
    assert [row["kind"] for row in rows] == ["decide", "override", "settle", "authority-change"]
    _assert_chain_intact(rows)
    assert rows[3]["decision_id"] == "dp1:2026-10-20T10:03:00+00:00"
    assert rows[3]["task_key"] is None


# ---------------------------------------------------------------------------
# Half-line tail (Q2.4 terminate-and-preserve)
# ---------------------------------------------------------------------------


def test_half_line_tail_is_preserved_and_chain_recovers(tmp_path):
    archive = _archive(tmp_path)
    first, _ = decide_archive.append_decide(archive, **_decide_kwargs(trigger_id="t1"))
    before = archive.read_bytes()

    dangling = b'{"seq": 99, "kind": "decid'
    with archive.open("ab") as handle:
        handle.write(dangling)

    second, created = decide_archive.append_decide(archive, **_decide_kwargs(trigger_id="t2"))
    assert created is True

    after = archive.read_bytes()
    # No truncate: the original bytes are still a prefix and the dangling
    # prefix survives verbatim as forensic evidence.
    assert after.startswith(before)
    assert dangling in after
    assert len(after) > len(before) + len(dangling)

    # The dangling line was terminated, so the next row chains from row 1.
    assert second["seq"] == 2
    assert second["prev_sha"] == _canonical_sha(first)

    rows = _read_rows(archive)
    assert [row["seq"] for row in rows] == [1, 2]
    _assert_chain_intact(rows)


def test_complete_json_tail_missing_newline_becomes_chain_head(tmp_path):
    archive = _archive(tmp_path)
    first, _ = decide_archive.append_decide(archive, **_decide_kwargs(trigger_id="t1"))
    raw = first
    complete_without_newline = json.dumps(
        {
            **raw,
            "seq": 2,
            "prev_sha": _canonical_sha(raw),
        },
        ensure_ascii=False,
    ).encode("utf-8")
    with archive.open("ab") as handle:
        handle.write(complete_without_newline)

    third, _ = decide_archive.append_decide(archive, **_decide_kwargs(trigger_id="t2"))
    rows = _read_rows(archive)
    assert [row["seq"] for row in rows] == [1, 2, 3]
    assert third["prev_sha"] == _canonical_sha(rows[1])
    _assert_chain_intact(rows)


# ---------------------------------------------------------------------------
# Duplicate decide (Q3)
# ---------------------------------------------------------------------------


def test_duplicate_decide_raises_and_writes_nothing(tmp_path):
    archive = _archive(tmp_path)
    decide_archive.append_decide(archive, **_decide_kwargs())
    size_before = archive.stat().st_size

    with pytest.raises(decide_archive.DecisionArchiveDuplicate) as excinfo:
        decide_archive.append_decide(
            archive, **_decide_kwargs(state={"prompt": "conflict"}, answer={"q1": {"value": "no"}})
        )
    assert isinstance(excinfo.value, decide_archive.DecisionArchiveError)
    assert isinstance(excinfo.value, ValueError)
    assert "dp1:t" in str(excinfo.value)
    assert archive.stat().st_size == size_before
    assert len(_read_rows(archive)) == 1


def test_duplicate_existing_returns_prior_row_without_appending(tmp_path):
    archive = _archive(tmp_path)
    first, _ = decide_archive.append_decide(archive, **_decide_kwargs())
    size_before = archive.stat().st_size

    again, created = decide_archive.append_decide(
        archive,
        duplicate="existing",
        **_decide_kwargs(answer={"q1": {"value": "no", "confidence": 0.1}}),
    )
    assert created is False
    assert again["seq"] == first["seq"]
    assert again["answer"] == OK_ANSWERS
    assert archive.stat().st_size == size_before


def test_different_trigger_ids_are_not_duplicates(tmp_path):
    archive = _archive(tmp_path)
    decide_archive.append_decide(archive, **_decide_kwargs(trigger_id="t1"))
    decide_archive.append_decide(archive, **_decide_kwargs(key="k2", trigger_id="t2"))
    assert [row["seq"] for row in _read_rows(archive)] == [1, 2]


def test_invalid_duplicate_mode_is_rejected(tmp_path):
    archive = _archive(tmp_path)
    with pytest.raises(decide_archive.DecisionArchiveError):
        decide_archive.append_decide(archive, duplicate="ignore", **_decide_kwargs())
    assert not archive.exists()


# ---------------------------------------------------------------------------
# Field validation (Q4 matrix)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides, needle",
    [
        ({"authority": "robot"}, "authority"),
        ({"available": False}, "reason"),
        ({"available": False, "answer": None, "reason": "made-up", "authority": "human"}, "REASON_CODES"),
        ({"available": False, "answer": OK_ANSWERS, "reason": "timeout"}, "answer"),
        ({"authority": "human"}, "escalated_reason"),
        ({"escalated_reason": "p0"}, "escalated_reason"),
        ({"authority": "human", "escalated_reason": "because"}, "escalated_reason"),
        ({"acted": True}, "authority=binding"),
        (
            {"acted": True, "authority": "binding", "actual_action": ""},
            "actual_action",
        ),
        ({"mode": "sometimes"}, "mode"),
        (
            {"mode": "suggest", "acted": True, "authority": "binding", "actual_action": "dispatch"},
            "AC-015",
        ),
        ({"questions_version": "v1"}, "questions_version"),
        ({"confidence_source": "guessed"}, "confidence_source"),
        ({"confidence": "high"}, "confidence"),
        ({"attempts": -1}, "attempts"),
        ({"answer": "yes"}, "answer"),
        ({"answer": {"q1": {"confidence": 0.5}}}, "value"),
        ({"task_key": 5}, "task_key"),
        ({"evidence_line": 0}, "evidence_line"),
        ({"cost_tokens": -2}, "cost_tokens"),
    ],
)
def test_decide_field_validation(tmp_path, overrides, needle):
    archive = _archive(tmp_path)
    with pytest.raises(decide_archive.DecisionArchiveError) as excinfo:
        decide_archive.append_decide(archive, **_decide_kwargs(**overrides))
    assert needle in str(excinfo.value)
    assert not archive.exists()


@pytest.mark.parametrize(
    "reason",
    [
        "disabled",
        "unavailable",
        "input-incomplete",
        "input-oversize",
        "low-confidence",
        "over-authority",
        "p0",
        "input-invalid",
    ],
)
def test_human_rows_accept_the_shared_escalated_reason_vocabulary(tmp_path, reason):
    """design D-030: one vocabulary; ``input-invalid`` survives for old rows only."""
    archive = _archive(tmp_path)
    row, _created = decide_archive.append_decide(
        archive,
        **_decide_kwargs(
            trigger_id=f"human-{reason}", authority="human", escalated_reason=reason
        ),
    )
    assert row["escalated_reason"] == reason


def test_legacy_escalated_reason_is_read_only_compatibility():
    assert decide_archive._ESCALATED_REASONS_LEGACY == frozenset({"input-invalid"})
    assert decide_archive._ESCALATED_REASONS - decide_archive._ESCALATED_REASONS_LEGACY == frozenset(
        {
            "disabled",
            "unavailable",
            "input-incomplete",
            "input-oversize",
            "low-confidence",
            "over-authority",
            "p0",
        }
    )


def test_decide_human_escalation_and_unavailable_row_are_valid(tmp_path):
    archive = _archive(tmp_path)
    row, _ = decide_archive.append_decide(
        archive,
        **_decide_kwargs(
            trigger_id="human",
            available=False,
            answer=None,
            reason="timeout",
            authority="human",
            escalated_reason="unavailable",
        ),
    )
    assert row["authority"] == "human"
    assert row["escalated_reason"] == "unavailable"
    assert row["answer"] is None


def test_decide_binding_acted_row_is_valid_and_suggest_is_not_acted(tmp_path):
    archive = _archive(tmp_path)
    acted, _ = decide_archive.append_decide(
        archive,
        **_decide_kwargs(
            trigger_id="acted",
            authority="binding",
            acted=True,
            actual_action="dispatch type=coding",
        ),
    )
    assert acted["acted"] is True
    assert acted["actual_action"] == "dispatch type=coding"

    suggest, _ = decide_archive.append_decide(
        archive,
        **_decide_kwargs(trigger_id="suggest", mode="suggest", authority="binding"),
    )
    assert suggest["mode"] == "suggest"
    assert suggest["acted"] is False


def test_override_validation_and_ref_seq(tmp_path):
    archive = _archive(tmp_path)
    decide_archive.append_decide(archive, **_decide_kwargs())

    with pytest.raises(decide_archive.DecisionArchiveError):
        decide_archive.append_override(
            archive,
            decision_id="dp1:t",
            dp="dp1",
            key="k",
            override_by="agent:pm",
            override_reason="not allowed",
        )
    with pytest.raises(decide_archive.DecisionArchiveError):
        decide_archive.append_override(
            archive,
            decision_id="dp1:t",
            dp="dp1",
            key="k",
            override_by="human",
            override_reason="",
        )
    with pytest.raises(decide_archive.DecisionArchiveError):
        decide_archive.append_override(
            archive,
            decision_id="dp1:t",
            dp="dp1",
            key="k",
            override_by="human",
            override_reason="wrong",
            ref_seq=7,
        )
    with pytest.raises(decide_archive.DecisionArchiveError):
        decide_archive.append_override(
            archive,
            decision_id="dp2:t",
            dp="dp1",
            key="k",
            override_by="human",
            override_reason="wrong",
        )

    row = decide_archive.append_override(
        archive,
        decision_id="dp1:t",
        dp="dp1",
        key="k",
        override_by="human:jev",
        override_reason="wrong",
        ref_seq=1,
        now="2026-10-20T11:00:00+00:00",
    )
    assert row["kind"] == "override"
    assert row["override_by"] == "human:jev"
    assert row["ref_seq"] == 1
    assert row["task_key"] is None
    assert row["outcome"] is None


def test_settle_validation_and_pending_registration(tmp_path):
    archive = _archive(tmp_path)
    decide_archive.append_decide(archive, **_decide_kwargs())

    with pytest.raises(decide_archive.DecisionArchiveError):
        decide_archive.append_settle(
            archive,
            decision_id="dp1:t",
            dp="dp1",
            key="k",
            task_key="t",
            outcome="weird",
            settled_by="pm-auto",
        )
    with pytest.raises(decide_archive.DecisionArchiveError):
        decide_archive.append_settle(
            archive,
            decision_id="dp1:t",
            dp="dp1",
            key="k",
            task_key="t",
            outcome="ok",
            settled_by="model",
        )
    with pytest.raises(decide_archive.DecisionArchiveError):
        decide_archive.append_settle(
            archive,
            decision_id="dp1:t",
            dp="dp1",
            key="k",
            task_key="t",
            outcome="pending",
            settled_by="pm-auto",
        )

    lost = decide_archive.append_settle(
        archive,
        decision_id="dp1:t",
        dp="dp1",
        key="k",
        task_key="t",
        outcome="pending",
        settled_by="pm-auto",
        note="lost",
        now="2026-10-20T11:00:00+00:00",
    )
    assert lost["outcome"] == "pending"
    assert lost["note"] == "lost"
    assert lost["evidence_ref"] is None


def test_authority_change_validation_and_default_triggers(tmp_path):
    archive = _archive(tmp_path)

    with pytest.raises(decide_archive.DecisionArchiveError):
        decide_archive.append_authority_change(archive, dp="dp1", key="k", by="agent", change="x")
    with pytest.raises(decide_archive.DecisionArchiveError):
        decide_archive.append_authority_change(
            archive, dp="dp1", key="k", by="human", change=""
        )
    with pytest.raises(decide_archive.DecisionArchiveError):
        decide_archive.append_authority_change(
            archive, dp="dp1", key="k", by="human", change="a\nb"
        )
    with pytest.raises(decide_archive.DecisionArchiveError):
        decide_archive.append_authority_change(
            archive, dp="dp1", key="k", by="signoff:revoke", change="conclusion=revoke"
        )
    with pytest.raises(decide_archive.DecisionArchiveError):
        decide_archive.append_authority_change(
            archive, dp="dp1", key="k", by="human", change="x", conclusion="revoke"
        )
    with pytest.raises(decide_archive.DecisionArchiveError):
        decide_archive.append_authority_change(
            archive, dp="dp1", key="k", by="human", change="x", config_sha_after="zz"
        )

    plain = decide_archive.append_authority_change(
        archive,
        dp="dp1",
        key="k",
        by="human",
        change="dp1 enabled=false",
        now="2026-10-20T12:00:00+00:00",
    )
    assert plain["decision_id"] == "dp1:2026-10-20T12:00:00+00:00"
    assert plain["task_key"] is None
    assert plain["conclusion"] is None

    signoff = decide_archive.append_authority_change(
        archive,
        dp="dp1",
        key="k",
        by="signoff:revoke",
        change="conclusion=revoke",
        conclusion="revoke",
        config_sha_after="0123456789abcdef",
        now="2026-10-20T12:01:00+00:00",
    )
    assert signoff["decision_id"] == "dp1:signoff@k@2026-10-20T12:01:00+00:00"
    assert signoff["conclusion"] == "revoke"

    refresh = decide_archive.append_authority_change(
        archive,
        dp="dp1",
        key="k",
        by="refresh",
        change="refresh added=3 kept=21",
        now="2026-10-20T12:02:00+00:00",
    )
    assert refresh["decision_id"] == "dp1:refresh@2026-10-20T12:02:00+00:00"

    _assert_chain_intact(_read_rows(archive))


# ---------------------------------------------------------------------------
# fold (Q5)
# ---------------------------------------------------------------------------


def test_fold_merges_decide_override_and_last_settle(tmp_path):
    archive = _archive(tmp_path)
    decide_archive.append_decide(archive, **_decide_kwargs(trigger_id="t1"))
    decide_archive.append_override(
        archive,
        decision_id="dp1:t1",
        dp="dp1",
        key="k",
        override_by="human",
        override_reason="first",
        ref_seq=1,
        now="2026-10-20T10:01:00+00:00",
    )
    decide_archive.append_settle(
        archive,
        decision_id="dp1:t1",
        dp="dp1",
        key="k",
        task_key="t",
        outcome="rework",
        settled_by="pm-auto",
        evidence_ref="run#1",
        now="2026-10-20T10:02:00+00:00",
    )
    decide_archive.append_override(
        archive,
        decision_id="dp1:t1",
        dp="dp1",
        key="k",
        override_by="human:p0",
        override_reason="second",
        now="2026-10-20T10:03:00+00:00",
    )
    decide_archive.append_settle(
        archive,
        decision_id="dp1:t1",
        dp="dp1",
        key="k",
        task_key="t",
        outcome="ok",
        settled_by="human",
        evidence_ref="run#2",
        now="2026-10-20T10:04:00+00:00",
    )

    results = [row for _lineno, row in decide_archive.iter_rows(archive)]
    result = decide_archive.fold(results)

    assert result.stats == decide_archive.FoldStats(
        rows_total=5,
        parsed=5,
        skipped_unparsable=0,
        skipped_non_dict=0,
        chain_breaks=0,
        seq_breaks=0,
        groups=1,
    )
    folded = result.groups["dp1:t1"]
    assert folded.base is not None
    assert folded.base["kind"] == "decide"
    assert folded.outcome == "ok"  # last settle by seq wins
    assert folded.settled_by == "human"
    assert folded.evidence_ref == "run#2"
    assert folded.human_override is True
    assert folded.override_count == 2
    assert folded.override_by == "human:p0"
    assert folded.override_reason == "second"
    assert folded.base_missing is False
    assert folded.dp == "dp1"
    assert folded.task_key == "t"
    assert folded.authority_last is None


def test_fold_keeps_decide_pending_and_registers_lost(tmp_path):
    archive = _archive(tmp_path)
    decide_archive.append_decide(archive, **_decide_kwargs(trigger_id="t1"))
    decide_archive.append_decide(archive, **_decide_kwargs(trigger_id="t2"))
    decide_archive.append_settle(
        archive,
        decision_id="dp1:t2",
        dp="dp1",
        key="k",
        task_key="t",
        outcome="pending",
        settled_by="pm-auto",
        note="lost",
        now="2026-10-20T10:01:00+00:00",
    )

    result = decide_archive.fold(_read_rows(archive))
    assert result.groups["dp1:t1"].outcome == "pending"
    assert result.groups["dp1:t1"].note is None
    assert result.groups["dp1:t2"].outcome == "pending"
    assert result.groups["dp1:t2"].note == "lost"
    assert result.stats.groups == 2


def test_fold_marks_base_missing_and_exposes_authority_last(tmp_path):
    archive = _archive(tmp_path)
    decide_archive.append_settle(
        archive,
        decision_id="dp9:orphan",
        dp="dp9",
        key="k",
        task_key=None,
        outcome="ok",
        settled_by="pm-auto",
        now="2026-10-20T10:00:00+00:00",
    )
    decide_archive.append_authority_change(
        archive,
        dp="dp9",
        key="k",
        by="human:p0-confirm",
        change="dp9 enabled=true mode=auto",
        now="2026-10-20T10:01:00+00:00",
    )

    result = decide_archive.fold(_read_rows(archive))
    orphan = result.groups["dp9:orphan"]
    assert orphan.base is None
    assert orphan.base_missing is True
    assert orphan.outcome == "ok"
    assert orphan.task_key is None

    change = result.groups["dp9:2026-10-20T10:01:00+00:00"]
    assert change.base_missing is True
    assert change.authority_last is not None
    assert change.authority_last["by"] == "human:p0-confirm"


def test_fold_counts_bad_rows_without_dropping_good_groups(tmp_path):
    archive = _archive(tmp_path)
    decide_archive.append_decide(archive, **_decide_kwargs(trigger_id="t1"))
    good = _read_rows(archive)
    rows = [
        "not json",
        42,
        '{"no": "identity"}',
        *good,
        {"decision_id": "dp1:t2", "seq": 2, "kind": "settle"},  # parsed, chain-broken
    ]
    result = decide_archive.fold(rows)
    assert result.stats.rows_total == 5
    assert result.stats.parsed == 2
    assert result.stats.skipped_unparsable == 2
    assert result.stats.skipped_non_dict == 1
    assert result.stats.chain_breaks == 1  # t2 claims seq 2 without genesis prev_sha
    assert result.stats.seq_breaks == 0
    assert result.groups["dp1:t1"].outcome == "pending"
    assert result.groups["dp1:t2"].base_missing is True


def test_fold_reports_tampered_prev_sha_and_seq_gaps(tmp_path):
    archive = _archive(tmp_path)
    decide_archive.append_decide(archive, **_decide_kwargs(trigger_id="t1"))
    decide_archive.append_decide(archive, **_decide_kwargs(trigger_id="t2"))
    decide_archive.append_override(
        archive,
        decision_id="dp1:t1",
        dp="dp1",
        key="k",
        override_by="human",
        override_reason="wrong",
        ref_seq=1,
        now="2026-10-20T10:01:00+00:00",
    )
    decide_archive.append_settle(
        archive,
        decision_id="dp1:t1",
        dp="dp1",
        key="k",
        task_key="t",
        outcome="ok",
        settled_by="human",
        now="2026-10-20T10:02:00+00:00",
    )
    rows = _read_rows(archive)

    tampered = [dict(row) for row in rows]
    tampered[1]["prev_sha"] = "f" * 16
    tampered[2]["seq"] = 99
    result = decide_archive.fold(tampered)
    # Re-hashing a tampered row invalidates it *and* every downstream link, so
    # one edit reports one break per affected row (3 of 4 rows here).
    assert result.stats.chain_breaks == 3
    assert result.stats.seq_breaks == 2  # 99 breaks the run, then 4 breaks it again


def test_fold_genesis_mismatch_on_first_row():
    result = decide_archive.fold(
        [{"seq": 5, "prev_sha": "f" * 16, "decision_id": "dp1:t", "kind": "decide"}]
    )
    assert result.stats.chain_breaks == 1
    assert result.stats.seq_breaks == 1
    assert result.groups["dp1:t"].base_missing is False


# ---------------------------------------------------------------------------
# Failure model / lock hygiene
# ---------------------------------------------------------------------------


def test_append_io_failure_raises_and_releases_lock(tmp_path):
    archive = tmp_path / "archive-is-a-dir"
    archive.mkdir()
    with pytest.raises(decide_archive.DecisionArchiveError):
        decide_archive.append_decide(archive, **_decide_kwargs())
    assert not archive.with_name(archive.name + decide_archive._LOCK_SUFFIX).exists()


def test_size_recheck_detects_lock_bypassing_writer(tmp_path, monkeypatch):
    archive = _archive(tmp_path)
    decide_archive.append_decide(archive, **_decide_kwargs(trigger_id="t1"))

    monkeypatch.setattr(decide_archive, "_chain_head", lambda _path: (None, 0))
    with pytest.raises(decide_archive.DecisionArchiveError) as excinfo:
        decide_archive.append_decide(archive, **_decide_kwargs(trigger_id="t2"))
    assert "kept changing" in str(excinfo.value)
    assert not archive.with_name(archive.name + decide_archive._LOCK_SUFFIX).exists()
    assert len(_read_rows(archive)) == 1


def test_lock_is_released_after_success(tmp_path):
    archive = _archive(tmp_path)
    decide_archive.append_decide(archive, **_decide_kwargs())
    assert not archive.with_name(archive.name + decide_archive._LOCK_SUFFIX).exists()


# ---------------------------------------------------------------------------
# Concurrency: two writers, no duplicate seq
# ---------------------------------------------------------------------------

_CHILD_WRITER = """\
import pathlib
import sys

sys.path.insert(0, sys.argv[1])
import decide_archive

archive = pathlib.Path(sys.argv[2])
tag = sys.argv[3]
count = int(sys.argv[4])

for index in range(count):
    decide_archive.append_decide(
        archive,
        dp="dp1",
        key="k",
        task_key="t",
        trigger_id=f"{tag}-{index}",
        state={"index": index, "tag": tag},
        questions_version="q-0123abcd",
        available=True,
        answer={"q1": {"value": "yes", "confidence": 0.9}},
        authority="advisory",
        now=f"2026-10-20T10:00:{index:02d}+00:00",
    )
"""


def test_concurrent_writers_never_duplicate_seq(tmp_path):
    archive = _archive(tmp_path)
    script = tmp_path / "concurrent_writer.py"
    script.write_text(_CHILD_WRITER, encoding="utf-8")
    per_writer = 12

    children = [
        subprocess.Popen(
            [sys.executable, str(script), str(MODULE_DIR), str(archive), tag, str(per_writer)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for tag in ("w1", "w2")
    ]
    for child in children:
        stdout, stderr = child.communicate(timeout=180)
        assert child.returncode == 0, stderr.decode("utf-8", errors="replace") + stdout.decode(
            "utf-8", errors="replace"
        )

    rows = _read_rows(archive)
    assert len(rows) == 2 * per_writer
    seqs = [row["seq"] for row in rows]
    assert len(set(seqs)) == len(seqs), "duplicate seq under concurrent writers"
    assert sorted(seqs) == list(range(1, 2 * per_writer + 1))
    _assert_chain_intact(rows)
    assert len({row["decision_id"] for row in rows}) == 2 * per_writer
