#!/usr/bin/env python3
# T-07 AC-010(c): per-case disposition of the 111 alias-pass / heading-fail
# flips under the CURRENT (H2-only) predicate + the I2 mechanical backfill.
# Read-only over the corpus. The classification mirrors the TS implementation:
#   - H2 headings only (like worker/output-sections.ts h2Headings: `## ` lines,
#     not ###, outside fences/blockquotes);
#   - mechanical whitelist = {上下文来源} (R2, MECHANICAL_SECTIONS);
#   - a case missing ONLY 上下文来源 => the I2 backfill rescues it (exit=2 -> 0)
#     WHEN the role is judged (writeless research/review, or a write role that
#     produced a report.md product; AC-006/C5 exemption otherwise).
#   - a case missing any substantive section => still fails (backfill cannot
#     invent 结论/证据/残留与未验证/改动清单/未覆盖面声明).
#   - a coding case with no report.md and no report-<slug>.md is NOT judged
#     (write-role exemption) => vacuous green, not a real flip.
# Output: one row per flip + class counts + rescued/still-fails summary.
import pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
AGENTICDOC = ROOT / ".agenticdoc"
SRC = AGENTICDOC / "mw-worker-output-contract" / "evidence" / "recovery-contract-flip-disposition-20261014.txt"

BASE = ["结论", "证据", "残留与未验证", "上下文来源"]
EXTRA = {"coding": ["改动清单"], "review": ["未覆盖面声明"]}
MECHANICAL = {"上下文来源"}

ALIASES = {
    "结论": ["结论", "tldr", "tl;dr", "summary", "摘要", "verdict", "总结"],
    "证据": ["证据", "evidence", "原始命令", "命令与输出", "复现", "verification", "验证步骤", "测试结果"],
    "残留与未验证": ["残留", "未验证", "未确认", "遗留", "remaining", "residual", "unverified", "limitation", "限制"],
    "上下文来源": ["上下文来源", "来源清单", "sources", "references", "参考", "读取", "阅读清单", "context sources"],
    "改动清单": ["改动清单", "变更清单", "changed files", "files changed", "改动", "变更", "修改文件"],
    "未覆盖面声明": ["未覆盖面", "未覆盖", "coverage", "未审", "未考察", "缺口"],
}
H2 = re.compile(r'^ {0,3}##(?!#)[ \t]+(?P<t>.*)$')
FENCE = re.compile(r'^( {0,3})(`{3,}|~{3,})(.*)$')
BQ = re.compile(r'^ {0,3}>')


def sections_for(t):
    req = list(BASE)
    if t is not None:
        req.extend(EXTRA.get(t, []))
    return req


def h2_headings(text):
    out = []
    fence = None
    for line in text.splitlines():
        m = FENCE.match(line)
        if m:
            char, ln = m.group(2)[0], len(m.group(2))
            if fence is None:
                fence = (char, ln)
            elif char == fence[0] and ln >= fence[1] and m.group(3).strip() == "":
                fence = None
            continue
        if fence is not None or BQ.match(line):
            continue
        m = H2.match(line)
        if m:
            t = re.sub(r'#+\s*$', '', m.group('t')).strip()
            out.append(re.sub(r'\s+', ' ', t).lower())
    return out


def normalize(a):
    return re.sub(r'\s+', ' ', a).strip().lower()


def missing_sections(text, t):
    hs = h2_headings(text)
    return [s for s in sections_for(t)
            if not any(normalize(a) in h for a in ALIASES[s] for h in hs)]


def header_type(task_md):
    for line in task_md.read_text(encoding='utf-8', errors='replace').splitlines():
        m = re.match(r'^type:\s*(\S*)\s*$', line)
        if m:
            v = m.group(1).strip()
            return v if v else None
        if line.strip().startswith('## '):
            break
    return None


def product_text(d):
    for name in ('report.md', 'output.md'):
        p = d / name
        if p.is_file():
            text = p.read_text(encoding='utf-8', errors='replace')
            if text.strip():
                return name, text
    return None, None


def has_report_product(d):
    for name in ('report.md',):
        p = d / name
        if p.is_file() and p.read_text(encoding='utf-8', errors='replace').strip():
            return True
    for p in d.glob('report-*.md'):
        if p.is_file() and p.read_text(encoding='utf-8', errors='replace').strip():
            return True
    return False


def classify(d, t, pname, text):
    """Return (verdict, reason) for one flip under the current predicate."""
    missing = missing_sections(text, t)
    judged = t in ('research', 'review') or (t == 'coding' and has_report_product(d))
    if not judged:
        return 'write-role-exempt', 'not judged (AC-006/C5 exemption; no report product)'
    if not missing:
        return 'h2-ok', 'no longer a flip under H2-only predicate'
    remaining = [m for m in missing if m not in MECHANICAL]
    if not remaining:
        return 'backfill-rescued', 'only mechanical 上下文来源 missing -> I2 backfill (exit=2 -> 0)'
    return 'still-fails', 'missing substantive: ' + ','.join(remaining)


def main():
    rows = []
    for line in SRC.read_text(encoding='utf-8').splitlines():
        if not line.startswith('FLIP '):
            continue
        rel = line[len('FLIP '):].split(' [')[0]
        d = ROOT / rel
        tm = d / 'task.md'
        if not tm.is_file():
            rows.append((rel, 'absent', '-', '-', 'task dir not present in this snapshot'))
            continue
        t = header_type(tm)
        if t is None:
            rows.append((rel, 'no-type', '-', '-', 'no header type: (legacy book)'))
            continue
        pname, text = product_text(d)
        if text is None:
            rows.append((rel, t, '-', '-', 'no non-empty product'))
            continue
        verdict, reason = classify(d, t, pname, text)
        rows.append((rel, t, pname, verdict, reason))

    from collections import Counter
    counts = Counter(r[3] for r in rows)
    n = len(rows)
    print('flip cases: n={}'.format(n))
    print('class counts (current predicate): {}'.format(dict(counts)))
    rescued = [r for r in rows if r[3] == 'backfill-rescued']
    still = [r for r in rows if r[3] == 'still-fails']
    exempt = [r for r in rows if r[3] == 'write-role-exempt']
    print('backfill-rescued: {} (exit=2 -> 0 through I2)'.format(len(rescued)))
    print('still-fails: {} (substantive gap, whitelist refuses to invent it)'.format(len(still)))
    print('write-role-exempt: {} (coding, no report product, not judged)'.format(len(exempt)))
    print()
    print('--- per-case disposition ---')
    for rel, t, pname, verdict, reason in rows:
        print('{:<58} [{}] via {:<10} {}: {}'.format(rel, t, pname or '-', verdict, reason))
    return 0


if __name__ == '__main__':
    sys.exit(main())
