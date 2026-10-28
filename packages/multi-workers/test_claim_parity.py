"""test_claim_parity.py — claim-driven-review T-06: TS <-> Python claims parity.

`shared/dispatch-card.ts` (TS) and `autopilot/dispatch.py` (Python) cannot share
code, so design §2.3 declares four constants a *single source* and this module
makes "same value" a measured fact instead of a comment:

  * ``CLAIM_TYPES``         — order-exact (the 类型 vocabulary the card gate and
                              the settle side both index by position);
  * ``UNVERIFIED_REASONS``  — order-exact (the 7-word 原因 closed set);
  * ``CLAIM_GATE_DEFAULT``  — value-exact (``advisory``; D-006 grey release);
  * ``CLAIM_BUDGET``        — all five keys (``perClaim/callCap/hardCap/
                              claimByteCap/byteCapMax``) value-exact.

The TS literals are read out of the source text with a regex (there is no
importable TS surface for a Python process); the Python side is the real module
attribute, so the comparison is TS-source vs Python-runtime, not two copies of
the same literal.

The fifth lock is the env name: ``MW_CLAIM_GATE`` must appear exactly once in
each side's module (``dispatch-card.ts`` doc block, ``dispatch.py`` env read) and
the runtime read sites must exist (``process.env.MW_CLAIM_GATE`` in
``pm/ui-bridge.ts``, ``os.environ.get("MW_CLAIM_GATE")`` in ``dispatch.py``) —
a rename on one side is exactly the drift the ``ESCALATED_REASONS`` precedent
(``decision_points.py:111-120``) records.

Fail-closed: a missing source file, a renamed/duplicated declaration or a parser
that yields no literals is a hard failure, never a skip or an empty comparison
(a hollow "all lists equal [] == []" is not a measurement).

Run: cd packages/multi-workers && python -X utf8 -m pytest -q test_claim_parity.py
Evidence channel is stdout: run with ``-s`` for the ``[VERIFY]`` lines.
"""
from __future__ import annotations

import pathlib
import re
import sys

import pytest

MODULE_DIR = pathlib.Path(__file__).resolve().parent
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

from autopilot import dispatch as dispatch_mod  # noqa: E402

REPO = MODULE_DIR.parent.parent
TS_CARD = (
    REPO
    / "packages"
    / "coding-agent"
    / "src"
    / "extensions"
    / "agent-team-loop"
    / "shared"
    / "dispatch-card.ts"
)
TS_UI_BRIDGE = (
    REPO
    / "packages"
    / "coding-agent"
    / "src"
    / "extensions"
    / "agent-team-loop"
    / "pm"
    / "ui-bridge.ts"
)
PY_DISPATCH = REPO / "packages" / "multi-workers" / "autopilot" / "dispatch.py"

ENV_NAME = "MW_CLAIM_GATE"

#: Design §2.3 literal: every key must exist, none may be added (a new key on
#: one side only is drift even when the five shared keys still agree).
BUDGET_KEYS = ("perClaim", "callCap", "hardCap", "claimByteCap", "byteCapMax")
#: Sanity floors so a regex that silently stops matching cannot pass the
#: comparisons above with two empty values.
CLAIM_TYPES_SIZE = 4
UNVERIFIED_REASONS_SIZE = 7


def _verify(tag: str, **kv: object) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()))


def _read(path: pathlib.Path, label: str) -> str:
    if not path.is_file():
        pytest.fail(f"{label} missing: {path} (fail-closed, T-06 parity cannot be measured)")
    return path.read_text(encoding="utf-8")


# ── TS literal extraction (design §2.3: one exporting module) ───────────────

def _ts_declaration_count(src: str, name: str) -> int:
    return len(re.findall(rf"export\s+const\s+{name}\b", src))


def _ts_array(src: str, name: str) -> list[str]:
    """`export const NAME = ["a", ...] as const;` -> ordered list of literals."""
    match = re.search(
        rf"export\s+const\s+{name}\b[^=]*=\s*\[(.*?)\]\s*(?:as\s+const\s*)?;",
        src,
        re.DOTALL,
    )
    if match is None:
        pytest.fail(f"TS literal block for {name} not found in {TS_CARD.name} (fail-closed)")
    body = match.group(1)
    values = re.findall(r'"([^"]*)"', body)
    # Anything that is not a plain string literal (spread, identifier, call)
    # would make the extracted list a lie; fail instead of comparing a subset.
    leftover = re.sub(r'"[^"]*"', "", body)
    leftover = re.sub(r"[\s,]", "", leftover)
    if leftover:
        pytest.fail(f"TS {name} carries non-literal content {leftover!r} (parser cannot lock it)")
    return values


def _ts_string(src: str, name: str) -> str:
    """`export const NAME = "value" as const;` -> "value"."""
    match = re.search(
        rf"export\s+const\s+{name}\b[^=]*=\s*\"([^\"]*)\"\s*(?:as\s+const\s*)?;",
        src,
    )
    if match is None:
        pytest.fail(f"TS string const {name} not found in {TS_CARD.name} (fail-closed)")
    return match.group(1)


def _ts_int_object(src: str, name: str) -> dict[str, int]:
    """`export const NAME = { key: 1, ... } as const;` -> {key: 1, ...}."""
    match = re.search(
        rf"export\s+const\s+{name}\b[^=]*=\s*\{{(.*?)\}}\s*(?:as\s+const\s*)?;",
        src,
        re.DOTALL,
    )
    if match is None:
        pytest.fail(f"TS object const {name} not found in {TS_CARD.name} (fail-closed)")
    body = match.group(1)
    # Comments carry prose, never values: drop them before the pair scan so a
    # commented-out key cannot be read as one, and a real key cannot hide in a
    # comment-only tail.
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.DOTALL)
    body = re.sub(r"//[^\n]*", "", body)
    pair_re = re.compile(r"([A-Za-z_$][\w$]*)\s*:\s*(-?\d+)\s*,?")
    pairs = pair_re.findall(body)
    leftover = re.sub(r"[\s,]", "", pair_re.sub("", body))
    if leftover:
        pytest.fail(f"TS {name} carries non-literal content {leftover!r} (parser cannot lock it)")
    return {key: int(value) for key, value in pairs}


def _ts_constants() -> dict[str, object]:
    src = _read(TS_CARD, "TS dispatch-card module")
    for name in ("CLAIM_TYPES", "UNVERIFIED_REASONS", "CLAIM_GATE_DEFAULT", "CLAIM_BUDGET"):
        count = _ts_declaration_count(src, name)
        if count != 1:
            pytest.fail(f"TS {name} must be declared exactly once, found {count} (single source)")
    return {
        "CLAIM_TYPES": _ts_array(src, "CLAIM_TYPES"),
        "UNVERIFIED_REASONS": _ts_array(src, "UNVERIFIED_REASONS"),
        "CLAIM_GATE_DEFAULT": _ts_string(src, "CLAIM_GATE_DEFAULT"),
        "CLAIM_BUDGET": _ts_int_object(src, "CLAIM_BUDGET"),
    }


def _py_constants() -> dict[str, object]:
    names = ("CLAIM_TYPES", "UNVERIFIED_REASONS", "CLAIM_GATE_DEFAULT", "CLAIM_BUDGET")
    missing = [name for name in names if not hasattr(dispatch_mod, name)]
    if missing:
        pytest.fail(f"Python dispatch.py lost claims constants {missing} (single source)")
    return {
        "CLAIM_TYPES": list(dispatch_mod.CLAIM_TYPES),
        "UNVERIFIED_REASONS": list(dispatch_mod.UNVERIFIED_REASONS),
        "CLAIM_GATE_DEFAULT": dispatch_mod.CLAIM_GATE_DEFAULT,
        "CLAIM_BUDGET": dict(dispatch_mod.CLAIM_BUDGET),
    }


_MEASURED: dict[str, dict[str, object]] | None = None


def _measured() -> dict[str, dict[str, object]]:
    """Extract both sides exactly once per session."""
    global _MEASURED
    if _MEASURED is None:
        _MEASURED = {"ts": _ts_constants(), "py": _py_constants()}
    return _MEASURED


# ── extraction shape (a lock that matches nothing must not pass) ────────────

def test_extraction_shape() -> None:
    measured = _measured()
    ts, py = measured["ts"], measured["py"]
    assert len(ts["CLAIM_TYPES"]) == CLAIM_TYPES_SIZE, ts["CLAIM_TYPES"]
    assert len(py["CLAIM_TYPES"]) == CLAIM_TYPES_SIZE, py["CLAIM_TYPES"]
    assert len(ts["UNVERIFIED_REASONS"]) == UNVERIFIED_REASONS_SIZE, ts["UNVERIFIED_REASONS"]
    assert len(py["UNVERIFIED_REASONS"]) == UNVERIFIED_REASONS_SIZE, py["UNVERIFIED_REASONS"]
    assert tuple(ts["CLAIM_BUDGET"]) == BUDGET_KEYS, ts["CLAIM_BUDGET"]
    assert tuple(py["CLAIM_BUDGET"]) == BUDGET_KEYS, py["CLAIM_BUDGET"]
    assert ts["CLAIM_GATE_DEFAULT"] != "", ts["CLAIM_GATE_DEFAULT"]
    # Order-preserving on the TS side: the regex reads the literal left to right.
    assert ts["CLAIM_TYPES"] != sorted(ts["CLAIM_TYPES"]), "fixture no longer exercises order"
    _verify(
        "shape",
        ts_types=len(ts["CLAIM_TYPES"]),
        ts_reasons=len(ts["UNVERIFIED_REASONS"]),
        ts_budget_keys=len(ts["CLAIM_BUDGET"]),
        gate=ts["CLAIM_GATE_DEFAULT"],
    )


# ── the four comparisons (design §2.3) ─────────────────────────────────────

def test_claim_types_order_exact() -> None:
    measured = _measured()
    ts, py = measured["ts"]["CLAIM_TYPES"], measured["py"]["CLAIM_TYPES"]
    assert py == ts, f"CLAIM_TYPES order drift: py={py} ts={ts}"
    _verify("CLAIM_TYPES", values=",".join(ts), order="exact", equal=True)


def test_unverified_reasons_order_exact() -> None:
    measured = _measured()
    ts, py = measured["ts"]["UNVERIFIED_REASONS"], measured["py"]["UNVERIFIED_REASONS"]
    assert py == ts, f"UNVERIFIED_REASONS order drift: py={py} ts={ts}"
    _verify("UNVERIFIED_REASONS", values=len(ts), order="exact", equal=True)


def test_claim_gate_default_exact() -> None:
    measured = _measured()
    ts = measured["ts"]["CLAIM_GATE_DEFAULT"]
    py = measured["py"]["CLAIM_GATE_DEFAULT"]
    assert py == ts, f"CLAIM_GATE_DEFAULT drift: py={py!r} ts={ts!r}"
    # D-006: the default itself must be the advisory (grey) mode; `enforce` is
    # opt-in via the env var, never the shipped default.
    assert ts == "advisory", f"CLAIM_GATE_DEFAULT must default to advisory, got {ts!r}"
    _verify("CLAIM_GATE_DEFAULT", value=ts, default="advisory", equal=True)


def test_claim_budget_values_exact() -> None:
    measured = _measured()
    ts, py = measured["ts"]["CLAIM_BUDGET"], measured["py"]["CLAIM_BUDGET"]
    assert tuple(ts) == BUDGET_KEYS, f"TS CLAIM_BUDGET keys drifted: {list(ts)}"
    assert tuple(py) == BUDGET_KEYS, f"Python CLAIM_BUDGET keys drifted: {list(py)}"
    for key in BUDGET_KEYS:
        assert py[key] == ts[key], f"CLAIM_BUDGET[{key!r}] drift: py={py[key]} ts={ts[key]}"
        assert py[key] >= 0, f"CLAIM_BUDGET[{key!r}] must be a non-negative integer, got {py[key]}"
    _verify("CLAIM_BUDGET", pairs=",".join(f"{k}={ts[k]}" for k in BUDGET_KEYS), equal=True)


# ── env name: one spelling on each side (D-006) ─────────────────────────────

def test_mw_claim_gate_env_name_single_source() -> None:
    card_src = _read(TS_CARD, "TS dispatch-card module")
    py_src = _read(PY_DISPATCH, "Python dispatch module")
    bridge_src = _read(TS_UI_BRIDGE, "TS ui-bridge module")

    card_hits = card_src.count(ENV_NAME)
    py_hits = py_src.count(ENV_NAME)
    assert card_hits == 1, f"{ENV_NAME} must appear exactly once in dispatch-card.ts, found {card_hits}"
    assert py_hits == 1, f"{ENV_NAME} must appear exactly once in autopilot/dispatch.py, found {py_hits}"

    # Each side must actually read it, not just mention it: a rename at the read
    # site is the drift this lock exists to catch.
    py_read = f'os.environ.get("{ENV_NAME}"'
    assert py_src.count(py_read) == 1, f"Python no longer reads {ENV_NAME} through os.environ.get"
    ts_read = f"process.env.{ENV_NAME}"
    assert bridge_src.count(ts_read) == 1, f"TS no longer reads {ENV_NAME} through process.env"
    assert ENV_NAME in bridge_src, f"ui-bridge.ts lost the {ENV_NAME} name entirely"

    # The two legal values come from the same vocabulary on both sides.
    gate = str(_measured()["py"]["CLAIM_GATE_DEFAULT"])
    assert gate in ("advisory", "enforce"), f"unexpected gate default {gate!r}"
    assert f'raw === "enforce"' in bridge_src, "TS gate no longer recognises the enforce opt-in"
    _verify(
        "MW_CLAIM_GATE",
        card_hits=card_hits,
        py_hits=py_hits,
        ts_read=ts_read,
        py_read=py_read,
        default=gate,
    )


# ── the derived cap formula (D-014: perClaim × n, both sides同式) ─────────

def _ts_function_body(src: str, name: str) -> str:
    """Body of `export function NAME(...) { ... }` up to the first closing brace
    at column 0 — enough to lock the two Math.min expressions it returns."""
    match = re.search(rf"export\s+function\s+{name}\b[^{{]*\{{", src)
    if match is None:
        pytest.fail(f"TS function {name} not found in {TS_CARD.name} (fail-closed)")
    tail = src[match.end() :]
    end = tail.find("\n}\n")
    if end < 0:
        pytest.fail(f"TS function {name} body is unterminated (fail-closed)")
    return tail[:end]


def test_claim_budget_caps_formula_parity() -> None:
    """The cap is `min(callCap, perClaim × n)` on both sides, not Σ预算.

    T-07 measured the old `min(callCap, Σ预算)` shape starving a 5-claim card
    after five calls (`5/5 calls already allowed`): Σ预算 is a *weight* (manual
    counts double, gated at 40), never a fetch count. This locks the shape of
    the TS function and the numbers Python actually emits; a one-sided edit turns
    it red instead of silently re-pricing every dispatch.
    """
    card_src = _read(TS_CARD, "TS claims contract")
    body = _ts_function_body(card_src, "claimBudgetCaps")
    for needle in (
        "CLAIM_BUDGET.callCap",
        "CLAIM_BUDGET.perClaim * claims.length",
        "CLAIM_BUDGET.byteCapMax",
        "CLAIM_BUDGET.claimByteCap * claims.length",
    ):
        assert needle in body, f"claimBudgetCaps no longer derives {needle}"
    assert "CLAIM_BUDGET_SUM_MAX" not in body, "Σ预算 (a weight) must not price the read cap"

    ts_budget = _ts_int_object(card_src, "CLAIM_BUDGET")
    assert ts_budget["perClaim"] > 1, "perClaim = 1 would collapse the formula back into Σ预算"
    observed = []
    for n, want in ((0, (0, 0)), (1, (6, 65536)), (5, (30, 327680)), (8, (30, 393216))):
        claims = [{"type": "grep"}] * n
        got = dispatch_mod.claim_budget_caps(claims)
        derived = (
            (0, 0)
            if n == 0
            else (
                min(ts_budget["callCap"], ts_budget["perClaim"] * n),
                min(ts_budget["byteCapMax"], ts_budget["claimByteCap"] * n),
            )
        )
        assert got == want, f"n={n}: expected {want}, got {got}"
        assert got == derived, f"n={n}: Python {got} != TS constants {derived}"
        observed.append(f"{n}->{got[0]}/{got[1]}")
    _verify("claimBudgetCaps", pairs=",".join(observed), formula="min(cap, perClaim*n)")
