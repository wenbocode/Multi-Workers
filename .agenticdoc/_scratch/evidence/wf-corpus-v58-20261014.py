"""PM-authored corpus patch: freeze V58 (mw-write-face-guard, 2026-10-14).

Adds the deferred corpus row for the intersection-time state-machine fallback:
`a = [huge, "src/x.ts"]`, `b = [huge, "src/x.ts"]` where huge = "x/"*300 + "x".
Measured before the patch (see evidence/wf-v58-probe-20261014.py and
wf-v58-ts-out.json):

    PY: Unsupported glob-product-state-limit   (detail "(301+1)*(301+1) > 65536")
    TS: Conflict sample=src/x.ts reason=write-face-overlap

Per design.md D-111 and evidence/PM-parity-differential-20261014.md section 7 the
TS shape is correct: a state-machine fallback must defer THAT PAIR, never abort
the whole `for ga / for gb` search, so the later provable conflict still wins.

Surgical line-based edit on purpose: a full `json.dumps(indent=2)` re-dump would
reformat every compact array in the file and make the contract diff unreadable.

Usage:
    python wf-corpus-v58-20261014.py --check     # verify the patch is applied
    python wf-corpus-v58-20261014.py             # apply it (idempotent)
"""

import hashlib
import pathlib
import sys

CORPUS = pathlib.Path(__file__).resolve().parents[3] / "packages" / "multi-workers" / "test" / "fixtures" / "write-face-corpus.json"
BEFORE_SHA = "1ca66a899fcc2041b477bf7be79791345026b652a23e6ca3e96849bb82a6b530"
HUGE = "x/" * 300 + "x"

EXTENDED_APPEND = (
    "; V58 (state-machine fallback pair + provable conflict), "
    "per evidence/PM-parity-differential-20261014.md section 7"
)

NOTE = (
    "    \"V58 (2026-10-14) pins the section 3.2 state-machine fallback at intersection time: a pair whose "
    "product exceeds the state limit must be deferred per pair, not abort the whole search, so a later "
    "provably-conflicting pair still yields an overlap (D-111; PM-parity-differential section 7). Its 601 "
    "character entry ('x/' repeated 300 times, then 'x') is written inline on purpose: the corpus expands only "
    "$REPO/$OUTSIDE, and one more macro would be one more expansion rule to get wrong. The deferred *reason "
    "string* is deliberately NOT pinned, so vectors that differ only in that string (unsupported-syntax vs "
    "glob-product-state-limit) are not corpus rows.\""
)

V58_ROW = (
    '    { "name": "V58 state-machine fallback pair does not abort the search", '
    f'"a": ["{HUGE}", "src/x.ts"], "b": ["{HUGE}", "src/x.ts"], '
    '"case_insensitive": false, "expect": { "kind": "overlap", "sample_globfree": true } }'
)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def apply_patch(lines: list[str]) -> list[str]:
    """Return patched lines; raises AssertionError when a precondition breaks."""
    assert lines[7].startswith('    "extended": "'), lines[7][:60]
    assert lines[7].rstrip().endswith('",'), lines[7][-40:]
    assert lines[12].strip() == '"overlap": 58,', lines[12]
    assert "overlap 33 / none 13" in lines[13], lines[13][:80]
    assert lines[40].rstrip().endswith('"'), lines[40][-40:]
    assert lines[41].strip() == "],", lines[41]
    assert lines[125].lstrip().startswith('{ "name": "V57'), lines[125][:60]
    assert lines[125].rstrip().endswith("}"), lines[125][-40:]
    assert lines[126].strip() == "]", lines[126]

    out = list(lines)
    out[7] = out[7].rstrip()[: -len('",')] + EXTENDED_APPEND + '",'
    out[12] = out[12].replace('"overlap": 58,', '"overlap": 59,')
    out[13] = out[13].replace("overlap 33 / none 13", "overlap 34 / none 13")
    out[40] = out[40].rstrip() + ","
    out.insert(41, NOTE)
    out[126] = out[126].rstrip() + ","
    out.insert(127, V58_ROW)
    return out


def main() -> int:
    raw = CORPUS.read_text(encoding="utf-8")
    check = "--check" in sys.argv
    already = "V58 state-machine fallback pair" in raw
    if check:
        print(f"file        : {CORPUS}")
        print(f"sha256      : {sha(raw)}")
        print(f"bytes       : {len(raw.encode('utf-8'))}")
        print(f"v58 present : {already}")
        print(f"counts.59   : {'\"overlap\": 59,' in raw}")
        return 0 if already and '"overlap": 59,' in raw else 1
    if already:
        print("already applied; nothing to do")
        print(f"sha256 : {sha(raw)}")
        print(f"bytes  : {len(raw.encode('utf-8'))}")
        return 0

    print(f"before sha256 : {sha(raw)}   (recorded: {BEFORE_SHA})")
    assert sha(raw) == BEFORE_SHA, "corpus changed since the v2 freeze; re-derive the patch first"
    patched = "\n".join(apply_patch(raw.splitlines())) + "\n"
    CORPUS.write_text(patched, encoding="utf-8")
    print(f"after  sha256 : {sha(patched)}")
    print(f"after  bytes  : {len(patched.encode('utf-8'))}")
    print(f"delta  bytes  : {len(patched.encode('utf-8')) - len(raw.encode('utf-8'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
