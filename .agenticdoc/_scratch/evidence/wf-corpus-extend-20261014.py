# 语料扩展：把 §3.2 回退清单与「混合条目顺序」锁进冻结契约
# 依据：.agenticdoc/mw-write-face-guard/evidence/PM-parity-differential-20261014.md
#      design.md D-111
# 用法：python .agenticdoc/_scratch/evidence/wf-corpus-extend-20261014.py [--check]
#   --check  只报告将要发生的改动与新旧 sha256，不写盘
# 契约变更只能由 PM 执行；扩展后必须把新的 sha256/bytes/counts 写回 plan.md。

import hashlib
import json
import pathlib
import sys

CORPUS = pathlib.Path("packages/multi-workers/test/fixtures/write-face-corpus.json")

# 回退清单条目（§3.2 第一类「不受支持语法」+ 三条硬违规做对照）：
# 关键契约点 = 「非法 class / extglob / 未闭合 brace」**不是 parse 期拒绝**，
# 而是解析通过、在交集期退化为 Unsupported（D-111 parse 期规则）。
PARSE_ROWS = [
    {"name": "P17 illegal char class is not a parse error", "head": ["write_face: src/[a-"],
     "expect": {"kind": "entries", "entries": ["src/[a-"]}},
    {"name": "P18 extglob negation is not a parse error", "head": ["write_face: src/!(x)"],
     "expect": {"kind": "entries", "entries": ["src/!(x)"]}},
    {"name": "P19 extglob plus() is not a parse error", "head": ["write_face: src/+(x)"],
     "expect": {"kind": "entries", "entries": ["src/+(x)"]}},
    {"name": "P20 extglob at() is not a parse error", "head": ["write_face: src/@(x)"],
     "expect": {"kind": "entries", "entries": ["src/@(x)"]}},
    {"name": "P21 unclosed brace is not a parse error", "head": ["write_face: src/{a,b"],
     "expect": {"kind": "entries", "entries": ["src/{a,b"]}},
    {"name": "P22 unsupported entry keeps order next to a valid one", "head": ["write_face: src/[a-, src/ok.ts"],
     "expect": {"kind": "entries", "entries": ["src/[a-", "src/ok.ts"]}},
]

OVERLAP_ROWS = [
    # 1) 不受支持语法 + 证不出重叠 ⇒ Unsupported（调用方按重叠处置）
    {"name": "V49 illegal class with nothing provable", "a": ["src/[a-"], "b": ["src/x.ts"],
     "case_insensitive": False, "expect": {"kind": "unsupported"}},
    {"name": "V50 extglob negation on side b", "a": ["src/x.ts"], "b": ["src/!(x)"],
     "case_insensitive": False, "expect": {"kind": "unsupported"}},
    {"name": "V51 unclosed brace with nothing provable", "a": ["src/{a,b"], "b": ["src/x.ts"],
     "case_insensitive": False, "expect": {"kind": "unsupported"}},
    # 2) 硬违规**优先**且与顺序无关（D-111 parse 期）——两种书写顺序给同一个 code
    {"name": "V52 hard escape wins over an earlier unsupported entry", "a": ["src/[a-", "src/../y"], "b": ["src/y"],
     "case_insensitive": False, "expect": {"kind": "reject", "side": "a", "code": "write-face-escape"}},
    {"name": "V53 same face, hard escape first (order independence)", "a": ["src/../y", "src/[a-"], "b": ["src/y"],
     "case_insensitive": False, "expect": {"kind": "reject", "side": "a", "code": "write-face-escape"}},
    {"name": "V54 hard invalid-entry wins over an earlier unsupported entry", "a": ["src/[a-", "!src/x"], "b": ["src/x"],
     "case_insensitive": False, "expect": {"kind": "reject", "side": "a", "code": "write-face-invalid-entry"}},
    {"name": "V55 hard outside-base wins over an earlier unsupported entry", "a": ["src/[a-", "$OUTSIDE/x"], "b": ["src/x"],
     "case_insensitive": False, "expect": {"kind": "reject", "side": "a", "code": "write-face-outside-base"}},
    {"name": "V56 same face, hard outside-base first (order independence)", "a": ["$OUTSIDE/x", "src/[a-"], "b": ["src/x"],
     "case_insensitive": False, "expect": {"kind": "reject", "side": "a", "code": "write-face-outside-base"}},
    # 3) 证得出的冲突优先于「不受支持语法」（D-111 overlap 期）
    {"name": "V57 provable conflict wins over an unsupported entry", "a": ["src/[a-", "src/x.ts"], "b": ["src/x.ts"],
     "case_insensitive": False, "expect": {"kind": "overlap", "sample_globfree": True}},
]

EXPECT_KIND_DOC = (
    "at least one side carries unsupported syntax (§3.2) and no conflict is provable; "
    "callers MUST treat it as overlap (D-006)"
)
NOTES_APPEND = [
    "D-111 (2026-10-14, PM parity differential): parse-time hard rule violations (`write-face-escape` / "
    "`write-face-invalid-entry` / `write-face-outside-base`) take precedence over an unsupported-syntax entry "
    "AND the verdict must not depend on entry order (V52–V56). At intersection time a provable conflict wins "
    "over unsupported syntax (V57); `Unsupported` means 'cannot decide', not 'decided overlap without a witness'.",
]


def main() -> int:
    raw = CORPUS.read_bytes()
    old_sha = hashlib.sha256(raw).hexdigest()
    doc = json.loads(raw.decode("utf-8"))
    names = {r["name"] for r in doc["parse"]} | {r["name"] for r in doc["overlap"]}
    added = [r["name"] for r in PARSE_ROWS + OVERLAP_ROWS if r["name"] not in names]
    if len(added) != len(PARSE_ROWS) + len(OVERLAP_ROWS):
        print("already extended (or name collision):", len(added), "of", len(PARSE_ROWS) + len(OVERLAP_ROWS))
    if "--check" in sys.argv:
        print("would add:", added)
        return 0
    doc["parse"].extend(r for r in PARSE_ROWS if r["name"] not in names)
    doc["overlap"].extend(r for r in OVERLAP_ROWS if r["name"] not in names)
    counts = doc["counts"]
    counts["parse"] = len(doc["parse"])
    counts["overlap"] = len(doc["overlap"])
    kinds: dict[str, int] = {}
    for row in doc["overlap"]:
        kinds[row["expect"]["kind"]] = kinds.get(row["expect"]["kind"], 0) + 1
    counts["overlap_note"] = (
        counts["overlap_note"].split("；kind：")[0]
        + "；kind：" + " / ".join(f"{k} {v}" for k, v in sorted(kinds.items(), key=lambda kv: -kv[1]))
    )
    doc["protocol"]["expect_kinds"]["unsupported"] = EXPECT_KIND_DOC
    existing_notes = doc["notes"]
    for note in NOTES_APPEND:
        if note not in existing_notes:
            existing_notes.append(note)
    doc["frozen"] = "2026-10-14 (extended: §3.2 fallback list + mixed-entry order, D-111)"
    text = json.dumps(doc, ensure_ascii=False, indent=1) + "\n"
    CORPUS.write_text(text, encoding="utf-8", newline="\n")
    new_sha = hashlib.sha256(CORPUS.read_bytes()).hexdigest()
    print("old sha256", old_sha)
    print("new sha256", new_sha)
    print("bytes", len(CORPUS.read_bytes()))
    print("counts", json.dumps(counts, ensure_ascii=False)[:200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
