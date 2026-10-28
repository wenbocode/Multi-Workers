"""T07b read-only probe over the *real* production history (no writes, no secrets).

Two runs of ``decision_history.load_history`` on this repository:

* without a redactor (the fail-closed path), and
* with a dummy known-secret redactor (the injected path shape T10 uses).

It prints the structural-schema outcome (dropped/invalid) so a false-positive
schema classification on real data is visible, and it proves the fail-closed run
echoes no free text. No credential is read, no file is written.
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[4]
PACKAGE = REPO / "packages" / "multi-workers"
sys.path.insert(0, str(PACKAGE))

import decision_history  # noqa: E402
import decision_wire  # noqa: E402


def probe(label: str, redact) -> list[str]:
    snapshot = decision_history.load_history(REPO, redact=redact)
    dropped = sum(record.redaction.dropped_fields for record in snapshot.records)
    invalid = sum(record.redaction.invalid_fields for record in snapshot.records)
    withheld = sum(1 for record in snapshot.records if record.redaction.omitted_fields)
    redacted = sum(1 for record in snapshot.records if record.redaction.substitutions)
    lines = [
        f"run={label}",
        f"records={len(snapshot.records)}",
        f"invalid_keys={snapshot.stats.invalid_keys}",
        f"blocked_reads={snapshot.stats.blocked_reads}",
        f"gates_recorded={snapshot.stats.gates_recorded}",
        f"dropped_fields={dropped}",
        f"invalid_fields={invalid}",
        f"records_with_omissions={withheld}",
        f"records_with_substitutions={redacted}",
        f"warnings={len(snapshot.warnings)}",
    ]
    return lines


def main() -> int:
    lines = probe("no-redactor (fail-closed)", None)
    lines += probe("dummy-redactor", decision_wire.SubstringRedactor(("not-a-real-secret",)))
    text = "\n".join(lines)
    (HERE / "real-history-probe.txt").write_text(text + "\n", encoding="utf-8", newline="\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
