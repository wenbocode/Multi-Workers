"""Tests for the claim-coverage metrics (claim-driven-review T-05, design §3.4).

One ``[CLAIMS]`` trace line per run (T-04) plus the existing session join give
``tokens_per_closed_claim``. The invariants under test:

* the line parser is strict (fixed field order, all five fields, extra fields
  ignored) and a repeated line settles on the last one;
* an unattributable session (no join / no usage rows) yields ``tokens=None``,
  ``attributable=False`` and ``tokens_per_closed_claim="n/a"`` — never ``0``;
* ``closed == 0`` also yields ``"n/a"`` (no division, no fabricated 0);
* a run without any ``[CLAIMS]`` line yields ``None`` as a whole (no inference),
  and the report row keeps its pre-T-05 key set (byte-identical output).

Every fixture is built in memory or under ``tmp_path``; no test reads a real
ledger or session tree.
"""

from __future__ import annotations

import json
import pathlib
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # noqa: E402

import usage  # noqa: E402

NOW = datetime.now(timezone.utc).replace(microsecond=0)
SINCE = NOW - timedelta(days=7)
TS = "2026-10-21T10:00:00Z"


def _claims_line(
    claims: int = 12,
    closed: int = 8,
    partial: int = 2,
    unverified: int = 2,
    fetches: int = 30,
    stamp: str = TS,
) -> str:
    """The T-04 trace line, verbatim shape."""
    return (
        f"[CLAIMS] {stamp} claims={claims} closed={closed}"
        f" partial={partial} unverified={unverified} fetches={fetches}"
    )


def _session(*usages: tuple[int, int, int, int], stamp: str = TS) -> dict:
    """Minimal joined-session scan: ``events`` is all the metrics read."""
    return {
        "session_id": "mw-alpha-1-1",
        "started_at": stamp,
        "ended_at": stamp,
        "models": {"timi/glm-5.3-flashx": {}},
        "events": [
            (
                stamp,
                "timi/glm-5.3-flashx",
                {"input": inp, "output": out, "cache_read": cached, "cache_write": write},
            )
            for inp, out, cached, write in usages
        ],
    }


def _run(line: str | None = None, **overrides) -> dict:
    """One ledger-shaped run mapping; ``trace`` carries the trace text."""
    run = {"run_id": "r1", "key": "alpha", "session_id": "mw-alpha-1-1"}
    if line is not None:
        run["claims_line"] = line
    run.update(overrides)
    return run


def _write_ledger(usage_dir: pathlib.Path, records: list[dict]) -> None:
    usage_dir.mkdir(parents=True, exist_ok=True)
    with (usage_dir / "runs.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")


def _write_pi_session(pi_root: pathlib.Path, session_id: str, started: datetime) -> None:
    path = pi_root / "H--git-ProjA" / f"2026-10-21T09-30-00-000Z_{session_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = started.strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = [
        {"type": "session", "version": 3, "id": session_id, "timestamp": stamp, "cwd": "H:/git/ProjA"},
        {
            "type": "message",
            "id": "msg-1",
            "timestamp": stamp,
            "message": {
                "role": "assistant",
                "provider": "timi",
                "model": "glm-5.3-flashx",
                "usage": {"input": 10, "output": 2, "cacheRead": 0, "cacheWrite": 0},
            },
        },
    ]
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def _ledger_run(**overrides) -> list[dict]:
    """One worker run: start + end, ``overrides`` land on both events."""
    started = NOW - timedelta(minutes=30)
    start = {
        "event": "start",
        "run_id": "r1",
        "ts": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "worker",
        "project": "H:/git/ProjA",
        "key": "alpha",
        "type": "review",
        "cli": "pi",
        "session_id": "mw-alpha-1-1",
        "model": "timi/glm-5.3-flashx",
    }
    end = {
        "event": "end",
        "run_id": "r1",
        "ts": (started + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "exit": 0,
        "wall_s": 300.0,
        "status": "done",
    }
    return [{**start, **overrides}, {**end, **overrides}]


# ── (1) [CLAIMS] line parsing ────────────────────────────────────────────────


def test_parse_claims_line_reads_all_five_counters() -> None:
    assert usage.parse_claims_line(_claims_line()) == {
        "claims": 12,
        "closed": 8,
        "partial": 2,
        "unverified": 2,
        "fetches": 30,
    }
    # Trailing fields are ignored; the shape is still the same measurement.
    assert usage.parse_claims_line(_claims_line() + " note=extra") == {
        "claims": 12,
        "closed": 8,
        "partial": 2,
        "unverified": 2,
        "fetches": 30,
    }
    # A timestamp token is optional (the design writes `ts`, T-04 writes ISO-Z).
    assert usage.parse_claims_line("claims=1 closed=1 partial=0 unverified=0 fetches=3") is None
    assert usage.parse_claims_line("[CLAIMS] claims=1 closed=1 partial=0 unverified=0 fetches=3") == {
        "claims": 1,
        "closed": 1,
        "partial": 0,
        "unverified": 0,
        "fetches": 3,
    }


def test_parse_claims_line_rejects_missing_field() -> None:
    assert usage.parse_claims_line("[CLAIMS] ts claims=3 closed=2 partial=1 fetches=9") is None
    # A half-written counter is not a number either.
    assert usage.parse_claims_line(_claims_line().replace("fetches=30", "fetches=")) is None
    assert usage.parse_claims_line(_claims_line().replace("fetches=30", "fetches=3x")) is None


def test_parse_claims_line_rejects_reordered_fields() -> None:
    reordered = "[CLAIMS] 2026-10-21T10:00:00Z closed=8 claims=12 partial=2 unverified=2 fetches=30"
    assert usage.parse_claims_line(reordered) is None
    swapped = "[CLAIMS] 2026-10-21T10:00:00Z claims=12 partial=2 closed=8 unverified=2 fetches=30"
    assert usage.parse_claims_line(swapped) is None


def test_parse_claims_lines_keeps_the_last_line() -> None:
    first = _claims_line(claims=9, closed=4, partial=3, unverified=2, fetches=20, stamp="2026-10-21T09:00:00Z")
    last = _claims_line(claims=9, closed=7, partial=1, unverified=1, fetches=24, stamp="2026-10-21T09:30:00Z")
    lines = ["[FLOW] tool_call read a.py", first, "[END] status=done exit=0", last]
    parsed = usage.parse_claims_lines(lines)
    assert parsed == {"claims": 9, "closed": 7, "partial": 1, "unverified": 1, "fetches": 24}
    assert usage.parse_claims_lines(["[FLOW] tool_call read a.py", "[END] status=done"]) is None


# ── (2) unattributable session -> n/a ────────────────────────────────────────


def test_claims_metrics_unattributable_session_is_na() -> None:
    line = _claims_line()

    # No session join at all (the 109/115 attempts the corpus calls unattributable).
    missing = usage.claims_metrics(_run(line), None)
    assert missing == {
        "claims": 12,
        "closed": 8,
        "partial": 2,
        "unverified": 2,
        "fetches": 30,
        "tokens": None,
        "tokens_per_closed_claim": usage.CLAIMS_NA,
        "attributable": False,
    }
    # A log that exists but carries no usage rows is equally unattributable.
    empty = usage.claims_metrics(_run(line), {"session_id": "mw-alpha-1-1", "events": []})
    assert empty is not None
    assert empty["tokens"] is None
    assert empty["attributable"] is False
    assert empty["tokens_per_closed_claim"] == usage.CLAIMS_NA

    # And the joined case: Σtokens / Σclosed over the same counters.
    joined = usage.claims_metrics(_run(line), _session((1_000, 200, 3_000, 0), (10, 20, 30, 40)))
    assert joined is not None
    assert joined["tokens"] == 4_300
    assert joined["attributable"] is True
    assert joined["tokens_per_closed_claim"] == 537.5


def test_claims_metrics_reads_a_preparsed_claims_subobject() -> None:
    """The run.json / ledger subobject path wins over a trace line."""
    run = _run(
        "[CLAIMS] 2026-10-21T10:00:00Z claims=99 closed=99 partial=0 unverified=0 fetches=99",
        claims={"total": 12, "closed": 8, "partial": 2, "unverified": 2, "fetches": 30,
                "tokens": None},
    )
    metrics = usage.claims_metrics(run, _session((2_000, 0, 0, 0)))
    assert metrics is not None
    assert metrics["claims"] == 12
    assert metrics["closed"] == 8
    assert metrics["fetches"] == 30
    assert metrics["tokens"] == 2_000
    assert metrics["tokens_per_closed_claim"] == 250.0

    # A subobject missing a counter is unparseable, not partially believed.
    broken = _run(claims={"total": 12, "closed": 8, "partial": 2, "fetches": 30})
    assert usage.claims_metrics(broken, _session((1, 1, 1, 1))) is None


# ── (3) closed == 0 -> n/a, tokens still reported ───────────────────────────


def test_claims_metrics_zero_closed_is_na_not_zero() -> None:
    line = _claims_line(claims=4, closed=0, partial=1, unverified=3, fetches=5)
    metrics = usage.claims_metrics(_run(line), _session((5_000, 500, 0, 0)))
    assert metrics is not None
    assert metrics["closed"] == 0
    assert metrics["tokens"] == 5_500  # measured, so it stays
    assert metrics["attributable"] is True
    assert metrics["tokens_per_closed_claim"] == usage.CLAIMS_NA


# ── (4) no [CLAIMS] line -> None (no inference) ─────────────────────────────


def test_claims_metrics_without_claims_line_is_none() -> None:
    assert usage.claims_metrics(_run(), _session((1, 1, 1, 1))) is None
    assert usage.claims_metrics(_run("[FLOW] tool_call read a.py"), _session((1, 1, 1, 1))) is None
    # A trace with no [CLAIMS] line (an old bundle) is not a measurement either.
    trace = "\n".join(["[FLOW] tool_call read a.py", "[END] status=done exit=0"])
    assert usage.claims_metrics(_run(trace=trace), _session((1, 1, 1, 1))) is None


def test_report_row_without_claims_line_keeps_the_r9_key_set(tmp_path, monkeypatch) -> None:
    """Byte-invariance: no claims line -> no extra key on the run row."""
    usage_dir = tmp_path / "usage"
    pi_root = tmp_path / "pi"
    monkeypatch.setenv("MW_USAGE_DIR", str(usage_dir))
    monkeypatch.setenv("MW_PI_SESSIONS_DIR", str(pi_root))
    _write_ledger(usage_dir, _ledger_run())
    _write_pi_session(pi_root, "mw-alpha-1-1", NOW - timedelta(minutes=30))

    report = usage.build_report(NOW, SINCE, {})
    row = report["runs"][0]
    assert set(row) == set(usage.DETAIL_FIELDS)
    assert "claims" not in row
    text = usage.format_report_text(report, detail=True)
    assert "claims" not in text


def test_report_row_carries_claims_when_the_ledger_does(tmp_path, monkeypatch) -> None:
    """The attach point: ledger-side claims -> row ``claims`` with joined tokens."""
    usage_dir = tmp_path / "usage"
    pi_root = tmp_path / "pi"
    monkeypatch.setenv("MW_USAGE_DIR", str(usage_dir))
    monkeypatch.setenv("MW_PI_SESSIONS_DIR", str(pi_root))
    payload = {"total": 6, "closed": 4, "partial": 1, "unverified": 1, "fetches": 9, "tokens": None}
    _write_ledger(usage_dir, _ledger_run(claims=payload))
    _write_pi_session(pi_root, "mw-alpha-1-1", NOW - timedelta(minutes=30))

    row = usage.build_report(NOW, SINCE, {})["runs"][0]
    # Tokens come from the session join, not from the payload's own `tokens`.
    assert row["claims"] == {
        "claims": 6,
        "closed": 4,
        "partial": 1,
        "unverified": 1,
        "fetches": 9,
        "tokens": 12,
        "tokens_per_closed_claim": 3.0,
        "attributable": True,
    }
    assert set(row) == set(usage.DETAIL_FIELDS) | {"claims"}


# ── (5) two splits of the same task stay separately comparable ──────────────


def test_claims_metrics_split_variants_are_compared_per_run() -> None:
    """One 20-claim unit vs 4x5 claim units: each ratio stays its own.

    The point of the metric is comparison "before/after the split", so a run's
    ratio must never borrow another run's tokens or counters.
    """
    # Variant A: 1 unit, 20 claims, 20 closed, 200k tokens -> 10k tokens/claim.
    unit_a = usage.claims_metrics(
        _run(_claims_line(claims=20, closed=20, partial=0, unverified=0, fetches=30)),
        _session((150_000, 50_000, 0, 0), stamp="2026-10-21T10:00:00Z"),
    )
    # Variant B: 4 units of 5 claims, 20k tokens each -> 4k tokens/claim each.
    units_b = [
        usage.claims_metrics(
            _run(_claims_line(claims=5, closed=5, partial=0, unverified=0, fetches=8)),
            _session((15_000, 5_000, 0, 0), stamp=f"2026-10-21T11:0{index}:00Z"),
        )
        for index in range(4)
    ]

    assert unit_a is not None and all(unit is not None for unit in units_b)
    assert unit_a["tokens"] == 200_000
    assert unit_a["tokens_per_closed_claim"] == 10_000.0
    for unit in units_b:
        assert unit is not None
        assert unit["tokens"] == 20_000
        assert unit["tokens_per_closed_claim"] == 4_000.0
    # Side by side: same task, two splits, one comparable number per run.
    ratios = [unit_a["tokens_per_closed_claim"]] + [
        unit["tokens_per_closed_claim"] for unit in units_b if unit is not None
    ]
    assert ratios == [10_000.0, 4_000.0, 4_000.0, 4_000.0, 4_000.0]
