"""Print ASCII-safe anchor lines for the W-05 (B2 runtime guard) card."""

import pathlib
import re

target = pathlib.Path(
    r"H:\git\Multi-Workers\packages\coding-agent\src\extensions\agent-team-loop\worker\worker-mode.ts"
)
lines = target.read_text(encoding="utf-8").splitlines()

patterns = [
    r"extractBashWriteCandidates",
    r"checkBashWriteScopeTarget",
    r"isWritelessRole",
    r"isShellRole",
    r"matchesWriteScopeEntry",
    r"WRITE_SCOPE",
    r"write_scope",
    r"worker_file",
]
for pat in patterns:
    hits = [i for i, line in enumerate(lines, 1) if re.search(pat, line)]
    head = ", ".join(str(h) for h in hits[:12])
    print(f"{pat}: n={len(hits)} lines=[{head}]")

print("--- write/edit/bash dispatch sites (case labels / handler maps) ---")
for i, line in enumerate(lines, 1):
    if re.search(r'case "(write|edit|bash)"|"(write|edit|bash)":|toolName ===', line):
        print(f"{i}: {line.strip()[:150]}")

print("--- exports in worker-mode.ts ---")
for i, line in enumerate(lines, 1):
    if line.startswith("export "):
        print(f"{i}: {line.strip()[:130]}")
