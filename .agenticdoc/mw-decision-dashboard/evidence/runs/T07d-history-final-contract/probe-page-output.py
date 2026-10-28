#!/usr/bin/env python3
"""T07d probe: the *whole* page output (filters included) never echoes a known secret.

Read-only: builds an isolated tmp control root through the real writers, then
folds the real project history once and compares the ledger hashes before and
after to prove the read path writes nothing.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sys
import tempfile
import types

HERE = pathlib.Path(__file__).resolve()
MW = HERE.parents[5] / "packages" / "multi-workers"
sys.path.insert(0, str(MW))

import decision_history as history  # noqa: E402
import decision_wire as wire  # noqa: E402
import test_decision_history as harness  # noqa: E402

SECRET = harness.SECRET


def full_page(page: history.HistoryPage) -> str:
    """Everything a consumer can serialise from one page, filters included."""
    return json.dumps(
        {
            "records": [record.as_dict(detail=True) for record in page.records],
            "filters": page.filters,
            "filters_withheld": list(page.filters_withheld),
            "filters_basis": list(page.filters_basis),
            "total": page.total,
            "limit": page.limit,
            "offset": page.offset,
            "has_more": page.has_more,
        },
        sort_keys=True,
    )


def main() -> int:
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="t07d-probe-"))

    def _delenv(name: str, raising: bool = False) -> None:
        del raising
        os.environ.pop(name, None)

    shim = types.SimpleNamespace(delenv=_delenv)
    root, shaped, _unreachable, _model_only = harness._structural_fixture(tmp, shim)

    snapshot = harness._snapshot(root, redact=harness.REDACTOR)
    pages = {
        "unfiltered": snapshot.page(),
        "key=known-secret": snapshot.page(key=SECRET),
        "dp=known-secret": snapshot.page(dp=SECRET),
        "legal": snapshot.page(key="mw-model", source="model"),
        "legal+status": snapshot.page(status="pending", scope="production"),
    }
    counts = {name: full_page(page).count(SECRET) for name, page in pages.items()}
    print("known-secret occurrences in complete page output:", json.dumps(counts))
    assert counts["key=known-secret"] == 0
    assert counts["dp=known-secret"] == 0
    assert counts["unfiltered"] == 0
    assert counts["legal"] == 0

    filtered = pages["key=known-secret"]
    print("page(key=<secret>): total =", filtered.total, "filters =", json.dumps(filtered.filters))
    print("filters_withheld =", list(filtered.filters_withheld))
    print("filters_basis =", list(filtered.filters_basis))
    assert filtered.total == 1, "selection still uses the raw value"
    assert filtered.filters["key"] is None
    assert filtered.filters_withheld == ("key",)
    assert all(SECRET not in name for name in filtered.filters_withheld)

    legal = pages["legal"]
    print("legal filters =", json.dumps(legal.filters), "total =", legal.total)
    assert legal.filters == {
        "key": "mw-model",
        "dp": "",
        "source": "model",
        "status": "",
        "scope": "production",
    }

    # Same page twice: the output policy is stateless (no accumulation).
    assert full_page(snapshot.page(key=SECRET)) == full_page(filtered)

    # Documented boundary: without a redactor the filters stay raw on purpose.
    raw_page = harness._snapshot(root).page(key=SECRET)
    print(
        "no-redactor page: total =",
        raw_page.total,
        "filters.key raw =",
        raw_page.filters["key"] == SECRET,
        "withheld =",
        list(raw_page.filters_withheld),
        "basis =",
        list(raw_page.filters_basis),
    )
    assert raw_page.filters["key"] == SECRET
    assert raw_page.filters_withheld == ()

    # Real production fold, read-only. An empty known-secret set is used because
    # no real credential may be injected here.
    repo = HERE.parents[5]
    ledger_dir = repo / ".agenticdoc" / "_autopilot"

    def inventory() -> dict[str, str]:
        found: dict[str, str] = {}
        for path in sorted(ledger_dir.glob("*.jsonl")):
            found[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        return found

    before = inventory()
    real = history.load_history(repo, redact=wire.SubstringRedactor(()))
    after = inventory()
    real_page = real.page(limit=200)
    print(
        "real production fold: records =",
        len(real.records),
        "page total =",
        real_page.total,
        "archive_damaged =",
        real.stats.archive_damaged,
        "wire_damaged =",
        real.stats.wire_damaged,
        "lifecycle_damaged =",
        real.stats.lifecycle_damaged,
        "warnings =",
        len(real.warnings),
        "filters_withheld =",
        list(real_page.filters_withheld),
    )
    assert before == after, "the history read never writes a ledger"
    assert real_page.filters["key"] == "" and real_page.filters["dp"] == ""
    assert real_page.filters_withheld == ()
    print("PROBE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
