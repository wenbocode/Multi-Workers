"""Read-only inspection of the legacy TS peer before writing the R2 test change."""
from __future__ import annotations

import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

WORKTREE = pathlib.Path(__file__).resolve().parents[4] / "implementation-worktree"
print("worktree", WORKTREE)
TS = WORKTREE / "packages/coding-agent/src/extensions/agent-team-loop/shared/decide-registry.generated.ts"
TRIAGE = WORKTREE / "packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts"

text = TS.read_text(encoding="utf-8")
print("ts bytes", len(text.encode()), "lines", text.count("\n"))
print("HEAD", repr(text.splitlines()[0]))
ids = re.findall(r'^\t"([^"]+)": \{', text, re.M)
print("ids", len(ids), ids)
print("has interface", "export interface DecideRegistryEntry {" in text)
print("block sample", repr(text[text.index(ids[0]) - 40 : text.index(ids[0]) + 600]))

triage = TRIAGE.read_text(encoding="utf-8")
start = triage.index("const UNIVERSAL_REQUIRED_FIELDS = [")
end = triage.index("];", start) + 2
print("UNIVERSAL BLOCK", triage[start:end])
tstart = triage.index("export const REQUIRED_FIELDS_BY_DP")
tend = triage.index("\n};", tstart) + 3
print("BYDP BLOCK", triage[tstart:tend])
print("DP1", re.search(r'export const DP1_ID = "([^"]+)";', triage).group(1))
