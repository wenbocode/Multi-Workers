"""Reconstruct the pre-T05k ``decision_points.py`` from the current file by
reversing exactly the three T05k edits, then prove the reconstruction by hash.

``hashes-baseline.txt`` recorded ``eceded4a19096c9176b77464c46f69fb1bf5e71206b8121624d3098f385f8078``
(216412 B) before the first edit. If the reversed copy hashes to that value, the
diff in ``diff.patch`` is the complete T05k source delta (no other writer touched
this file between the baseline and now).
"""

from __future__ import annotations

import difflib
import hashlib
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
SOURCE = HERE.parents[4] / "packages" / "multi-workers" / "decision_points.py"
BASELINE_HASH = "eceded4a19096c9176b77464c46f69fb1bf5e71206b8121624d3098f385f8078"

NEW_SPEC = '''        "p0_open": {
            "type": "array",
            "description": "Enabled P0 dp ids right now (string array; [] when none or the table is absent).",
            # The producer writes [] for "no P0 open": that empty array is the
            # real value of this field, not an unreplaced scaffold placeholder
            # (T05h). Field-level and book-only; no other field declares it.
            "empty_is_value": True,
            # The same unified array boundary every new array declares (design
            # \u00a74.5, T05k N5): sorted registry P0 dp ids, 10 today, longest 19 B,
            # so 32 items / string / 128 B is headroom, not a producer limit.
            # No enum: the element space is dp ids, not a closed set invented
            # here.
            "max_items": STATE_ARRAY_MAX_ITEMS,
            "item_type": "string",
            "item_max_bytes": STATE_ARRAY_ITEM_MAX_BYTES,
        },'''
OLD_SPEC = '''        "p0_open": {
            "type": "array",
            "description": "Enabled P0 dp ids right now (string array; [] when none or the table is absent).",
            # The producer writes [] for "no P0 open": that empty array is the
            # real value of this field, not an unreplaced scaffold placeholder
            # (T05h). Field-level and book-only; no other field declares it.
            "empty_is_value": True,
        },'''

NEW_BRANCH = '''    if missing:
        # A missing/null/blank required field is illegal material exactly like a
        # typed refusal (step 5b): it is never sent and never stored as a
        # snapshot, while the decision-end row keeps the refusal fact (T05k N1).
        capture.material_refused = True
        capture.remember_state(state, questions=None, state_digest=None)'''
OLD_BRANCH = '''    if missing:
        capture.remember_state(state, questions=None, state_digest=None)'''

NEW_DOC = '''    #: Set when the caller's material was refused as illegal (a missing/blank
    #: required field, the typed contract, the closed key set or the observation
    #: book). Refused material is never stored as a snapshot: only the refusal
    #: facts belong in the ledger (T05b F1/F2, T05k N1).'''
OLD_DOC = '''    #: Set when the caller's material was refused as illegal (typed contract,
    #: closed key set or observation book). Refused material is never stored as
    #: a snapshot: only the refusal facts belong in the ledger (T05b F1/F2).'''

REVERSALS = ((NEW_SPEC, OLD_SPEC), (NEW_BRANCH, OLD_BRANCH), (NEW_DOC, OLD_DOC))


def main() -> None:
    baseline = SOURCE.read_bytes().decode("utf-8")
    eol = "\r\n" if "\r\n" in baseline else "\n"
    for new, old in REVERSALS:
        anchor = new.replace("\n", eol)
        assert baseline.count(anchor) == 1, f"reversal anchor not found once: {new[:60]!r}"
        baseline = baseline.replace(anchor, old.replace("\n", eol))
    out = HERE / "baseline" / "decision_points.py"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(baseline.encode("utf-8"))
    digest = hashlib.sha256(baseline.encode("utf-8")).hexdigest()
    print(f"reconstructed sha256={digest} ({len(baseline.encode('utf-8'))} B)")
    print("matches recorded baseline:", digest == BASELINE_HASH)

    current = SOURCE.read_bytes().decode("utf-8")
    diff = list(
        difflib.unified_diff(
            baseline.splitlines(),
            current.splitlines(),
            fromfile="a/packages/multi-workers/decision_points.py",
            tofile="b/packages/multi-workers/decision_points.py",
            lineterm="",
        )
    )
    (HERE / "diff.patch").write_text("\n".join(diff) + "\n", encoding="utf-8", newline="\n")
    print(f"diff.patch: {len(diff)} lines")


main()
