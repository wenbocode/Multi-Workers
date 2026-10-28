import pathlib
import re

path = pathlib.Path(
    r"H:\git\Multi-Workers\.agenticdoc\mw-dp-consolidation\implementation-worktree\packages\coding-agent\src\extensions\agent-team-loop\shared\decide-registry.generated.ts"
)
text = path.read_text(encoding="utf-8")
for number, line in enumerate(text.splitlines(), 1):
    if re.search(r"contextSlots|emptyIsValue|roleScope|^\t\"", line):
        print(number, line)
print("---- ids:", re.findall(r'^\t"([^"]+)": \{', text, re.M))
print("---- lines/bytes:", len(text.splitlines()), len(text.encode("utf-8")))
