"""Sync the two obsolete `interceptorCount() === 1` expectations in
test/suite/autopilot-read-scope.test.ts (type: coding now registers the
write-face guard as a second `tool_call` handler, D-007/D-115). Line-based so the
third, still-correct occurrence (research-type task) is untouched."""

import pathlib

TARGET = pathlib.Path(
    r"H:\git\Multi-Workers\packages\coding-agent\test\suite\autopilot-read-scope.test.ts"
)
lines = TARGET.read_text(encoding="utf-8").splitlines()

OLD = "\t\t\texpect(worker.interceptorCount()).toBe(1);"
NEW = [
    "\t\t\t// Two `tool_call` handlers: the read-scope interceptor plus the",
    "\t\t\t// write-face guard a `type: coding` task now installs (D-007/D-115).",
    "\t\t\texpect(worker.interceptorCount()).toBe(2);",
]

hits = [i for i, line in enumerate(lines) if line == OLD]
print(f"exact matches: {[i + 1 for i in hits]}")

# Only the two `type: coding` sites (1-indexed 752 and 809) are obsolete; the
# research-type site (466) stays 1.
TARGETS = [809, 752]
for lineno in TARGETS:
    idx = lineno - 1
    assert lines[idx] == OLD, f"line {lineno} is not the expected assertion: {lines[idx]!r}"
    lines[idx : idx + 1] = NEW

TARGET.write_text("\n".join(lines) + "\n", encoding="utf-8")

after = TARGET.read_text(encoding="utf-8").splitlines()
print("=== resulting sites ===")
for i, line in enumerate(after, 1):
    if "interceptorCount()).toBe(" in line:
        print(f"{i}: {line.strip()}")
print(f"file lines={len(after)}")
