"""Summarise the read-only check substeps and record the post-fix hashes."""

import hashlib
import pathlib
import subprocess
import time

evidence = pathlib.Path(".agenticdoc/mw-decision-dashboard/evidence/runs/T05d-book-array-secret")
steps = [
    ("check-pinned-deps", "node scripts/check-pinned-deps.mjs"),
    ("check-ts-imports", "node scripts/check-ts-relative-imports.mjs"),
    ("check-shrinkwrap", "node scripts/generate-coding-agent-shrinkwrap.mjs --check"),
    ("check-install-lock", "node scripts/generate-coding-agent-install-lock.mjs --check"),
    ("check-tsgo", "tsgo --noEmit"),
]
lines = [
    "# read-only check substeps (NOT `npm run check`; the write-mode biome pass and",
    "# browser-smoke were deliberately skipped -- see report).",
]
for name, command in steps:
    log = (evidence / f"{name}.txt").read_text(encoding="utf-8")
    exits = [line for line in log.splitlines() if line.startswith("EXIT_")]
    lines.append(f"== {name} ==")
    lines.append(command)
    lines.extend(exits or ["EXIT_<missing>=<no log>"])
lines.extend(
    [
        "== biome (read-only, whole repo) ==",
        "node node_modules/@biomejs/biome/bin/biome check --error-on-warnings .",
        "log: check-biome-readonly.txt",
        "EXIT_check-biome-readonly=1  (5 pre-existing findings in packages/coding-agent/test/suite/mwoc-*.test.ts,",
        "  files outside this card's write face; no Python file is linted by biome)",
        "== browser-smoke ==",
        "NOT RUN (card forbids browser); full `npm run check` is therefore NOT equivalent and NOT run",
    ]
)
(evidence / "check-substeps.txt").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
print("\n".join(lines))

recorded = []
for name in (
    "packages/multi-workers/decision_book.py",
    "packages/multi-workers/test_decision_input_contract_migration.py",
):
    data = pathlib.Path(name).read_bytes()
    blob = subprocess.run(["git", "hash-object", name], capture_output=True, text=True).stdout.strip()
    recorded.append(f"{name}\tsha256={hashlib.sha256(data).hexdigest()}\tblob={blob}\tsize={len(data)}")
header = [
    f"# captured {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
    "# pre-fix baseline hashes in baseline-hashes.txt",
]
(evidence / "final-hashes.txt").write_text(
    "\n".join(header + recorded) + "\n", encoding="utf-8", newline="\n"
)
print("\n".join(recorded))

source = pathlib.Path("packages/multi-workers/decision_book.py").read_text(encoding="utf-8")
start = source.index("_SECRET_DETAIL = ")
end = source.index("def _context_strings(")
excerpt = source[start:end].rstrip() + "\n"
(evidence / "changed-region-decision_book.txt").write_text(
    "# decision_book.py: secret-scan region after the P0 fix\n" + excerpt,
    encoding="utf-8",
    newline="\n",
)
print(f"excerpt_bytes={len(excerpt)}")
