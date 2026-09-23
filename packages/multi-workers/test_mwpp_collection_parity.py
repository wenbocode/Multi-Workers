"""
test_mwpp_collection_parity.py — 10-key TOOL_ALLOWLISTS snapshot parity
(mw-worker-progress-persist T-3; AC-008, VC-008).

The L0 parity case (`test_autopilot_l0.py::test_vc023_registry_parity`) only
checks the 6 keys the Python REGISTRY owns; the TS-side legacy buckets
(coding/review/research) and the internal `fallback` bucket values are not
locked anywhere. This module freezes the whole pre-change TS table (2026-09-23)
as a literal and asserts the parsed source equals it item-by-item, order
included, via the shared `_parse_ts_allowlists` helper — never a copy of it
(the same "shared helper, no copy" contract `test_rag_research.py` follows).

A value or ordering drift in `worker-mode.ts::TOOL_ALLOWLISTS` fails this
case; a parse failure (missing/renamed block) fails inside the helper.

`test_autopilot_l0.py` is the locked acceptance file and stays untouched.

Run: python -m pytest test_mwpp_collection_parity.py -q -s
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from test_autopilot_l0 import _parse_ts_allowlists  # noqa: E402  (shared helper, no copy)


def _verify(tag: str, **kv) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()), flush=True)


# Frozen 2026-09-23 snapshot of `worker-mode.ts::TOOL_ALLOWLISTS` before the
# mw-worker-progress-persist change (RQ-D2 F5). Order-exact by construction.
_EXPECTED_ALLOWLISTS: dict[str, list[str]] = {
    "coding": ["read", "write", "edit", "bash", "find", "grep", "ls"],
    "review": ["read", "find", "grep", "ls"],
    "research": ["read", "find", "grep", "ls", "bash"],
    "roadmap-writer": ["read", "write", "edit", "find", "grep", "ls"],
    "phase-writer": ["read", "write", "edit", "bash", "find", "grep", "ls"],
    "verifier": ["read", "find", "grep", "ls"],
    "reviewer": ["read", "find", "grep", "ls"],
    "repair": ["read", "write", "edit", "bash", "find", "grep", "ls"],
    "rag-research": [
        "read",
        "find",
        "grep",
        "ls",
        "rag_search",
        "rag_symbol",
        "rag_graph",
        "rag_impact",
        "rag_sources",
        "rag_feedback",
        "rag_chat",
    ],
    "fallback": ["read", "write", "edit", "bash", "find", "grep", "ls"],
}


def test_vc008_allowlist_snapshot_unchanged() -> None:
    parsed = _parse_ts_allowlists()
    assert set(parsed) == set(_EXPECTED_ALLOWLISTS), (
        f"TS key drift: extra={sorted(set(parsed) - set(_EXPECTED_ALLOWLISTS))} "
        f"missing={sorted(set(_EXPECTED_ALLOWLISTS) - set(parsed))}"
    )
    for name, expected in _EXPECTED_ALLOWLISTS.items():
        assert parsed[name] == expected, (
            f"{name}: ts={parsed[name]} expected={expected} (order-exact required)"
        )
    _verify(
        "VC-008",
        parity_pass="true",
        snapshot_equal="true",
        keys=len(parsed),
    )
