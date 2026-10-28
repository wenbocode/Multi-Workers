import json
import os
import sys

sys.path.insert(0, os.path.abspath("packages/multi-workers"))
from autopilot.write_face import Refused, Undeclared, Unsupported, parse_write_face, overlap  # noqa: E402

BASE = os.path.abspath(".")
CASES = [
    ["[a-", ".."],
    ["..", "[a-"],
    ["[a-", "!a"],
    ["!a", "[a-"],
    ["[a-", "/abs/x"],
    ["/abs/x", "[a-"],
    ["[a-", "a"],
    ["a", "[a-"],
    ["..", "a"],
    ["a", ".."],
]
REF = parse_write_face("write_face: a", base=BASE, case_insensitive=False)
out = {}
for entries in CASES:
    r = parse_write_face("write_face: " + ", ".join(entries), base=BASE, case_insensitive=False)
    if isinstance(r, Undeclared):
        v = "undeclared"
    elif isinstance(r, Refused):
        v = "reject:" + r.code
    else:
        o = overlap(r, REF)
        v = "none" if o is None else ("unsupported" if isinstance(o, Unsupported) else "overlap")
    out[", ".join(entries)] = v
path = os.path.join(os.environ["TEMP"], "wf-pos-py.json")
with open(path, "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False, indent=1))
