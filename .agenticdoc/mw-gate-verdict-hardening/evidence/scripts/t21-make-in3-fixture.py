#!/usr/bin/env python -X utf8
"""Build the T-21 IN-3 queue fixture from the real incident rows (de-sensitised).

Source : <project>/.agenticdoc/_workers.parallel  (gitignored, local only)
Filter : rows whose dispatched_at is the IN-3 burst second (2026-10-10T02:50:05)
Shape  : 9 columns  task_key|status|cli|provider|task_path|dispatched_at|updated_at|model|origin
Output : packages/multi-workers/test/fixtures/in3-queue-9col-burst.txt

De-sensitising
  * owner directory segment  -> pk01..pkNN (first-appearance order == ASCII order of the real keys)
  * task_key                 -> <owner>-t<NN>
  * task_path                -> H:/proj/.agenticdoc/<owner>/workers/<task>/task.md
  * columns 1..8 are otherwise byte-identical (status/cli/provider/timestamps/model survive)
  * column 9 `origin` is RECONSTRUCTED as `manual`: the pre-rebuild rows carried the 9th column
    (new codec always writes it, post-mortem 01-... §4.2 step 1) while the *post*-rebuild rows that
    survived on disk are the old codec's 8-column output. Assertions only depend on the column
    count / row count / timestamp format, so the restored value carries no claim.

Run: cd H:/git/Multi-Workers && python -X utf8 .agenticdoc/mw-gate-verdict-hardening/evidence/scripts/t21-make-in3-fixture.py
"""

from __future__ import annotations

import hashlib
import pathlib
import sys

BURST_PREFIX = "2026-10-10T02:50:05"
QUEUE = pathlib.Path(".agenticdoc/_workers.parallel")
OUT = pathlib.Path("packages/multi-workers/test/fixtures/in3-queue-9col-burst.txt")


def main() -> int:
    lines = [
        line
        for line in QUEUE.read_text(encoding="utf-8").splitlines()
        if line.strip() and BURST_PREFIX in line.split("|")[5]
    ]

    owners: dict[str, str] = {}
    seen: dict[str, int] = {}
    rows: list[str] = []
    for line in lines:
        cols = [c.strip() for c in line.split("|")]
        while len(cols) < 9:
            cols.append("")
        cols = cols[:9]

        path = cols[4].replace("/", "\\")
        real_owner = path.split("\\workers\\")[0].split("\\")[-1]
        owner = owners.setdefault(real_owner, f"pk{len(owners) + 1:02d}")

        seen[owner] = seen.get(owner, 0) + 1
        task = f"{owner}-t{seen[owner]:02d}"

        cols[0] = task
        cols[4] = f"H:/proj/.agenticdoc/{owner}/workers/{task}/task.md"
        cols[8] = "manual"
        rows.append(" | ".join(cols))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(rows) + "\n"
    OUT.write_text(body, encoding="utf-8", newline="\n")

    fields = {len(r.split("|")) for r in rows}
    print(f"source rows   : {len(lines)}")
    print(f"owners        : {len(owners)}")
    print(f"fixture rows  : {len(rows)}")
    print(f"fields/row    : {sorted(fields)}")
    print(f"bytes         : {len(body.encode('utf-8'))}")
    print(f"sha256        : {hashlib.sha256(body.encode('utf-8')).hexdigest()}")
    print(f"out           : {OUT.as_posix()}")
    leak = [
        line
        for line in rows
        if any(token in line for token in ("Multi-Workers", "E2Feature", "msc-", "ap-", "mw-"))
    ]
    print(f"leak check    : {len(leak)} suspicious row(s)")
    return 0 if rows and fields == {9} and not leak else 1


if __name__ == "__main__":
    sys.exit(main())
