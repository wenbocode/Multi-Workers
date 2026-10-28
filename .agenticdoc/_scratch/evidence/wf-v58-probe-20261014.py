"""PM-side probe: measure the Python operator on the deferred V58 vector and the
V59/V60 deferral-order vectors.  Mirrors the corpus block-list/single-line
carrier rules; prints one JSON line per case."""

import json
import pathlib
import sys

PKG = pathlib.Path(r"H:\git\Multi-Workers\packages\multi-workers")
sys.path.insert(0, str(PKG))

from autopilot import write_face as wf  # noqa: E402

CASES = pathlib.Path(r"H:\git\Multi-Workers\.agenticdoc\_scratch\evidence\wf-v58-cases-20261014.json")
HUGE = "x/" * 300 + "x"
BASE = pathlib.Path(r"H:\git\Multi-Workers")


def head(entries: list[str]) -> str:
    return "## write_face\nwrite_face: " + ", ".join(entries) + "\n"


def describe(result: object) -> dict:
    kind = type(result).__name__
    out: dict = {"kind": kind}
    for attr in ("reason", "detail", "sample", "rule", "other"):
        value = getattr(result, attr, None)
        if value is not None:
            out[attr] = value if not isinstance(value, str) else value[:120]
    return out


def main() -> None:
    payload = json.loads(CASES.read_text(encoding="utf-8"))
    for case in payload["cases"]:
        expand = lambda seq: [HUGE if item == "$HUGE" else item for item in seq]  # noqa: E731
        a_entries, b_entries = expand(case["a"]), expand(case["b"])
        fa = wf.parse_write_face(head(a_entries), base=str(BASE))
        fb = wf.parse_write_face(head(b_entries), base=str(BASE))
        print(json.dumps({"case": case["name"], "a_kind": type(fa).__name__, "b_kind": type(fb).__name__}))
        if isinstance(fa, wf.WriteFace) and isinstance(fb, wf.WriteFace):
            print(json.dumps({"case": case["name"], "overlap": describe(wf.overlap(fa, fb))}))
        else:
            print(json.dumps({"case": case["name"], "overlap": "PARSE_REFUSED"}))


if __name__ == "__main__":
    main()
