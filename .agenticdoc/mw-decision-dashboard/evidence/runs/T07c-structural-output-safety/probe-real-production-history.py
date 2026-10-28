"""T07c read-only probe over the *real* project history.

Reads the production carriers through ``load_history`` exactly like the monitor
does, with a redactor whose known-secret set is a dummy value (so nothing real
is claimed to be a secret). Prints fold statistics and whether any record
reports a structural omission (expected 0: the dummy set matches nothing), and
that every record serializes for the page and detail routes.

Read-only: no carrier byte is written, no directory is created. Exit 0 when the
fold completes and no error path was hit.
"""
from __future__ import annotations

import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "packages" / "multi-workers"))

import decision_history  # noqa: E402
import decision_wire  # noqa: E402

DUMMY = decision_wire.SubstringRedactor(("zzz-not-a-real-secret-value",))


def main() -> int:
    snapshot = decision_history.load_history(REPO, redact=DUMMY)
    stats = snapshot.stats.as_dict()
    print("control_root        :", snapshot.control_root)
    print("records             :", len(snapshot.records))
    print(
        "archive rows        :",
        stats["archive_rows"],
        "damaged:",
        stats["archive_damaged"],
        "chain_breaks:",
        stats["chain_breaks"],
        "seq_breaks:",
        stats["seq_breaks"],
    )
    print(
        "wire/lifecycle      :",
        stats["wire_events"],
        "/",
        stats["lifecycle_events"],
        "damaged:",
        stats["wire_damaged"],
        "/",
        stats["lifecycle_damaged"],
    )
    print(
        "dropped/invalid keys:",
        sum(record.redaction.dropped_fields for record in snapshot.records),
        "/",
        stats["invalid_keys"],
    )
    withheld = sum(record.redaction.structural_withheld for record in snapshot.records)
    print("structural_withheld :", withheld, "(dummy secret set matches nothing)")
    flags = sorted(
        {flag for record in snapshot.records for flag in record.flags if flag.startswith("structural")}
    )
    print("structural flags    :", flags or "none")
    print("warnings            :", len(snapshot.warnings))
    page = snapshot.page(limit=decision_history.MAX_PAGE_LIMIT)
    rendered = json.dumps([record.as_dict() for record in page.records])
    detail_errors: list[str] = []
    for record in snapshot.records:
        try:
            json.dumps(record.as_dict(detail=True))
        except (TypeError, ValueError) as exc:  # a non-serialisable payload is a defect
            detail_errors.append(f"{record.opaque_id}: {type(exc).__name__}")
    print("page records        :", len(page.records), "has_more:", page.has_more)
    print("page payload bytes  :", len(rendered))
    print("detail errors       :", detail_errors or "none")
    print("secret_marker_echoed:", DUMMY.secrets[0] in rendered)
    failures = []
    if withheld:
        failures.append("a dummy secret set produced structural omissions")
    if detail_errors:
        failures.append("an unmodified record failed to serialize")
    if DUMMY.secrets[0] in rendered:
        failures.append("the dummy marker was echoed (impossible unless a carrier holds it)")
    print("FAILURES:", failures or "none")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
