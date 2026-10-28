"""Add the missing [Unreleased] changelog entries for mw-write-face-guard (WFG)
and mw-dynamic-concurrency (MDC).

Rules honoured: append to the FIRST existing subsection of each name inside
`## [Unreleased]` (the coding-agent file already carries duplicate `### Added` /
`### Fixed` headings, so never create another one); preserve the file's dominant
EOL (P-010); idempotent (skips anything already present).
"""

import pathlib

REPO = pathlib.Path(r"H:\git\Multi-Workers")

ENTRIES = {
    "packages/coding-agent/CHANGELOG.md": [
        ("### Added", [
            "- Added the extension-side write-face guard (mw-write-face-guard): `shared/write-face.ts` is the single parser and overlap operator for the task.md `write_face:` head (single-`/` syntax, `[]`/`{}` sets, explicit case mode that is never inferred inside the operator), one renderer turns the dispatch card's `## 写入允许面` section into that head, and the PM dispatch path refuses a parse-invalid or provably overlapping face with zero side effects while a card-backed undeclared face stays serial-only. The runtime guard anchors every agent `write`/`edit`/`bash` target to the declared face, and `mw doctor` surfaces the refusals.",
            "- Added the `max_workers_per_key` per-key bound to the extension-side config mirror (mw-dynamic-concurrency) next to `max_parallel_keys`: defaults `8` / `4`, both ranged `[1, null]`, field-for-field identical to `autopilot/config.py`. The autopilot monitor now shows the configured bound, the dependency frontier size and this tick's effective concurrency (`cap` / `eff` / `frontier`), with `slotsUsed` counted in keys.",
        ]),
        ("### Changed", [
            "- Changed autopilot concurrency from a static key cap to a dependency frontier (mw-dynamic-concurrency): the conductor starts `min(max_parallel_keys, |key frontier|)` keys and `min(max_workers_per_key, |task frontier|)` workers per key, both derived from the roadmap `depends_on` column and the task cards' `deps:` header. Missing or unparseable dependency data falls that layer back to serial with an audit line, and roadmap dependency validation now runs inside the tick as observation only (it neither suppresses nor authorises a dispatch).",
            "- Changed the min/max parallel-key range from a frozen value to an upper bound (mw-dynamic-concurrency): setting the bound to `1` returns both layers to serial without restarting `serve`, since the effective concurrency is recomputed from the frontier on every tick.",
        ]),
        ("### Fixed", [
            "- Fixed a second dispatch of a live `task_key` silently overwriting the in-flight queue row and its task.md (mw-dynamic-concurrency): the dispatch path now refuses an identity whose queue row is still non-terminal, with zero side effects and a `duplicate-dispatch:` reason, and that refusal is treated as a wait-for-the-next-tick condition rather than a key failure. This is the mechanism behind the duplicate worker activation tracked as P-034.",
        ]),
    ],
    "packages/multi-workers/CHANGELOG.md": [
        ("### Added", [
            "- Added the write-face operator, its frozen corpus and the doctor surface (mw-write-face-guard): `autopilot/write_face.py` parses the task.md `write_face:` head and judges pairwise overlap with per-pair deferral for the inexact cases, `autopilot/dispatch.py` renders the dispatch card's `## 写入允许面` section into that head through a single renderer, and `mw doctor` reports refusals by code and by source.",
            "- Added the task dependency graph (mw-dynamic-concurrency): `autopilot/task_graph.py` reads the task cards' `deps:` header with its own parser (the existing `card_audit._header_value` cannot see a card head at all), joins dependency ids to card stems by numeric core, and detects dangling, self-referential, cyclic and cross-key references. Any problem, or an unreadable card, falls the whole key back to serial with one deduplicated audit event instead of silently magnifying the work in progress.",
        ]),
        ("### Changed", [
            "- Changed the conductor from a static key cap to a dependency frontier (mw-dynamic-concurrency): per key it starts `min(max_workers_per_key, |task frontier|)` workers and across keys `min(max_parallel_keys, |key frontier|)`, both recomputed per tick from the parsed dependency graph. A card without a declared write face is scheduled serial-only rather than assumed non-overlapping (mw-write-face-guard D-003), and the write-face judgement, the task.md write and the queue row now share one `workers.lock` critical section.",
            "- Changed the `advance` timeline event to carry the wall clock of the synchronous `advance_phase.py` call in its structured `data` payload (`data={\"ms\": n}`) (mw-dynamic-concurrency). No new event name is introduced and the frozen `detail` sentence is untouched, so the existing listeners keep working; the measurement shows `advance` occupying 0.986-0.993 of the tick wall clock, i.e. the synchronous subprocess remains the dominant per-tick cost.",
        ]),
        ("### Fixed", [
            "- Fixed a duplicate dispatch of a live `task_key` upgrading an in-flight worker (mw-dynamic-concurrency): inside the already-held lock the dispatch path now looks the identity up in the live queue and refuses a non-terminal one with zero side effects (no task dir, no task.md, no row, no second `dispatch` event) and a `duplicate-dispatch:` reason. The conductor classifies that refusal as a wait-for-the-next-tick condition, so it no longer turns into a permanent stall, while a terminal row still re-dispatches through the upsert (the retry path stays open).",
        ]),
    ],
}


def insert(data: str, eol: str, heading: str, bullets: list[str]) -> tuple[str, bool]:
    start = data.find("## [Unreleased]")
    if start < 0:
        return data, False
    end = data.find(eol + "## [", start + 1)
    if end < 0:
        end = len(data)
    block = data[start:end]
    anchor = heading + eol
    pos = block.find(anchor)
    if pos < 0:
        # subsection absent: create it right after the [Unreleased] heading line
        head_end = block.find(eol)
        addition = heading + eol + eol + eol.join(bullets) + eol
        block2 = block[: head_end + len(eol)] + addition + block[head_end + len(eol):]
        new = data[:start] + block2 + data[end:]
        return new, True
    at = start + pos + len(anchor)
    payload = eol + (eol + eol).join(bullets) + eol
    return data[:at] + payload + data[at:], True


for rel, specs in ENTRIES.items():
    path = REPO / rel
    raw = path.read_bytes().decode("utf-8")
    crlf = raw.count("\r\n")
    eol = "\r\n" if crlf > (raw.count("\n") - crlf) else "\n"
    marker = "mw-dynamic-concurrency"
    if marker in raw.split("## [Unreleased]", 1)[1].split(eol + "## [", 1)[0]:
        print(f"{rel}: already has {marker} in [Unreleased] - skipped")
        continue
    for heading, bullets in specs:
        raw, ok = insert(raw, eol, heading, bullets)
        print(f"{rel}: {heading} -> {'appended' if ok else 'FAILED (no [Unreleased])'}")
    path.write_bytes(raw.encode("utf-8"))
    print(f"{rel}: eol={'CRLF' if eol == chr(13) + chr(10) else 'LF'} bytes={len(raw.encode('utf-8'))}")
