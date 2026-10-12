"""Repair the Process Log: split the 18:45 line, restore the 18:32 entry before it."""

import pathlib

p = pathlib.Path(".agenticdoc/mw-gate-verdict-hardening/pm-state.md")
lines = p.read_text(encoding="utf-8").splitlines()

i = next(idx for idx, l in enumerate(lines) if l.startswith("- 10-10 18:45：**T-11 done + acked**"))
head, sep, tail = lines[i].partition("（T-10：done 前守卫是")
assert sep, "boundary not found"

lines[i] = head
lines.insert(i, "- 10-10 18:32：**T-10 + T-13 done + acked**" + sep + tail)

p.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
for idx in range(i - 2, i + 2):
    print(idx, lines[idx][:78])
