import json
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "packages", "multi-workers"))
from autopilot.write_face import Conflict, Refused, Unsupported, Undeclared, parse_write_face  # noqa: E402

ALPHA = [
    "a", "b", "c", "x.ts", "*.ts", "a/*", "a/**", "**", "**/b", "a/**/b", "a/b*",
    "A/B", "a/b", "a/b/c", "x*y", "a?b", "src/**", "src/*.ts", "*", "a/*/c",
    "..", "a/../b", "!a", "+(a)", "!(a)", "@(a)", "[a-", "/abs/x", "a//b", "./a", "a/",
]
BASE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
SETTLE = {}


def py_verdict(a, b):
    def shape(entries):
        text = "write_face: " + ", ".join(entries)
        r = parse_write_face(text, base=BASE, case_insensitive=False)
        if isinstance(r, Undeclared):
            return "undeclared", None
        if isinstance(r, Refused):
            return "reject:" + r.code, None
        return "", r

    sa, fa = shape(a)
    if sa:
        return sa
    sb, fb = shape(b)
    if sb:
        return sb
    from autopilot.write_face import overlap

    res = overlap(fa, fb)
    if res is None:
        return "none"
    if isinstance(res, Conflict):
        return "overlap"
    assert isinstance(res, Unsupported), res
    return "unsupported"


def main():
    random.seed(20261014)
    tmp = os.environ["TEMP"]
    vin = os.path.join(tmp, "wf-diff-vectors.json")
    vout = os.path.join(tmp, "wf-diff-ts.json")
    rows = []
    for _ in range(600):
        a = [random.choice(ALPHA) for _ in range(random.randint(1, 2))]
        b = [random.choice(ALPHA) for _ in range(random.randint(1, 2))]
        rows.append({"a": a, "b": b})
    with open(vin, "w", encoding="utf-8") as fh:
        json.dump(rows, fh)
    if not os.path.exists(vout):
        print("TS verdicts missing; run the temp vitest first:", vout)
        return 2
    with open(vout, encoding="utf-8") as fh:
        ts = json.load(fh)
    assert len(ts) == len(rows), (len(ts), len(rows))
    bad = []
    kinds = {}
    for row, t in zip(rows, ts):
        p = py_verdict(row["a"], row["b"])
        kinds[t] = kinds.get(t, 0) + 1
        if p != t:
            bad.append((row["a"], row["b"], p, t))
    print("vectors=%d  mismatches=%d" % (len(rows), len(bad)))
    print("ts kind histogram:", dict(sorted(kinds.items(), key=lambda kv: -kv[1])))
    for item in bad[:15]:
        print("  MISMATCH", item)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
