#!/usr/bin/env python3
# Recovery-contract historical-corpus pass-rate statistics (AC-010(a)).
# Read-only. tier A = current whole-text alias substring (checkRecovery).
# tier B = S1 heading-only (a heading line contains the alias).
# Run: python .agenticdoc/mw-worker-output-contract/evidence/scripts/recovery-contract-corpus-stats.py
import argparse, pathlib, re, sys
from collections import Counter

BASE = ['\u7ed3\u8bba', '\u8bc1\u636e', '\u6b8b\u7559\u4e0e\u672a\u9a8c\u8bc1', '\u4e0a\u4e0b\u6587\u6765\u6e90']
TYPE_EXTRA = {'coding': ['\u6539\u52a8\u6e05\u5355'], 'review': ['\u672a\u8986\u76d6\u9762\u58f0\u660e']}
ALIASES = {
    '\u7ed3\u8bba': ['\u7ed3\u8bba', 'tldr', 'tl;dr', 'summary', '\u6458\u8981', 'verdict', '\u603b\u7ed3'],
    '\u8bc1\u636e': ['\u8bc1\u636e', 'evidence', '\u539f\u59cb\u547d\u4ee4', '\u547d\u4ee4\u4e0e\u8f93\u51fa', '\u590d\u73b0', 'verification', '\u9a8c\u8bc1\u6b65\u9aa4', '\u6d4b\u8bd5\u7ed3\u679c'],
    '\u6b8b\u7559\u4e0e\u672a\u9a8c\u8bc1': ['\u6b8b\u7559', '\u672a\u9a8c\u8bc1', '\u672a\u786e\u8ba4', '\u9057\u7559', 'remaining', 'residual', 'unverified', 'limitation', '\u9650\u5236'],
    '\u4e0a\u4e0b\u6587\u6765\u6e90': ['\u4e0a\u4e0b\u6587\u6765\u6e90', '\u6765\u6e90\u6e05\u5355', 'sources', 'references', '\u53c2\u8003', '\u8bfb\u53d6', '\u9605\u8bfb\u6e05\u5355', 'context sources'],
    '\u6539\u52a8\u6e05\u5355': ['\u6539\u52a8\u6e05\u5355', '\u53d8\u66f4\u6e05\u5355', 'changed files', 'files changed', '\u6539\u52a8', '\u53d8\u66f4', '\u4fee\u6539\u6587\u4ef6'],
    '\u672a\u8986\u76d6\u9762\u58f0\u660e': ['\u672a\u8986\u76d6\u9762', '\u672a\u8986\u76d6', 'coverage', '\u672a\u5ba1', '\u672a\u8003\u5bdf', '\u7f3a\u53e3'],
}
H2 = re.compile(r'^##\s+(?P<t>.*?)\s*#*\s*$')
H23 = re.compile(r'^\s*#{2,3}\s+(?P<t>.*?)\s*#*\s*$')


def sections_for(t):
    req = list(BASE)
    if t is not None:
        req.extend(TYPE_EXTRA.get(t, []))
    return req


def header_type(task_md):
    for line in task_md.read_text(encoding='utf-8', errors='replace').splitlines():
        m = re.match(r'^type:\s*(\S*)\s*$', line)
        if m:
            v = m.group(1).strip()
            return v if v else None
        if line.strip().startswith('## '):
            break
    return None


def product(d):
    for name in ('report.md', 'output.md'):
        p = d / name
        if p.is_file():
            text = p.read_text(encoding='utf-8', errors='replace')
            if text.strip():
                return name, text
    return None, None


def corpus(root):
    hits = []
    for w in sorted(root.rglob('workers')):
        if not w.is_dir():
            continue
        for d in sorted(w.iterdir()):
            if not d.is_dir():
                continue
            tm = d / 'task.md'
            if not tm.is_file():
                continue
            t = header_type(tm)
            if t is None:
                continue
            pname, text = product(d)
            if text is None:
                continue
            hits.append((d, t, pname, text))
    return hits


def alias_hit(text, aliases, boundary):
    hay = text.lower()
    for a in aliases:
        al = a.lower()
        if al not in hay:
            continue
        if not (boundary and re.fullmatch(r'[a-z;. ]+', al)):
            return True
        if re.search(r'(?<![a-z0-9])' + re.escape(al) + r'(?![a-z0-9])', hay):
            return True
    return False


def alias_ok(text, t, boundary):
    return all(alias_hit(text, ALIASES[s], boundary) for s in sections_for(t))


def headings(text, cap):
    return [m.group('t').strip().lower() for m in (cap.match(l) for l in text.splitlines()) if m]


def heading_ok(text, t, cap):
    hs = headings(text, cap)
    for s in sections_for(t):
        if not any(a.lower() in hd for a in ALIASES[s] for hd in hs):
            return False
    return True


def missing_sections(text, t, cap):
    hs = headings(text, cap)
    return [s for s in sections_for(t) if not any(a.lower() in hd for a in ALIASES[s] for hd in hs)]


def pct(k, n):
    return '{}/{} = {:.1f}%'.format(k, n, k / n * 100) if n else 'n/a'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=str(pathlib.Path(__file__).resolve().parents[3]))
    ap.add_argument('--flips', action='store_true', help='list alias-pass heading-fail files')
    args = ap.parse_args()
    root = pathlib.Path(args.root)
    hits = corpus(root)
    n = len(hits)
    print('corpus root: ' + str(root))
    print('judged targets (workers/*/task.md header type: + non-empty report.md|output.md): n={}'.format(n))
    print('type distribution: ' + str(dict(Counter(t for _, t, _, _ in hits))))
    a_sub = sum(1 for _, t, _, x in hits if alias_ok(x, t, False))
    a_bnd = sum(1 for _, t, _, x in hits if alias_ok(x, t, True))
    h2 = sum(1 for _, t, _, x in hits if heading_ok(x, t, H2))
    h23 = sum(1 for _, t, _, x in hits if heading_ok(x, t, H23))
    print('tier A alias substring (current checkRecovery, includes): ' + pct(a_sub, n))
    print('tier A2 alias word-boundary variant:                     ' + pct(a_bnd, n))
    print('tier B heading H2 contains:                              ' + pct(h2, n))
    print('tier B2 heading H2/H3 contains:                          ' + pct(h23, n))
    flip = sum(1 for _, t, _, x in hits if alias_ok(x, t, False) and not heading_ok(x, t, H23))
    print('flip alias-pass to H2/H3-heading-fail:                   ' + pct(flip, n))
    freq = Counter()
    for _, t, _, x in hits:
        for s in missing_sections(x, t, H23):
            freq[s] += 1
    print('heading-tier missing frequency: ' + ', '.join('{}={}/{}'.format(s, freq[s], n) for s, _ in freq.most_common()))
    if args.flips:
        for d, t, pname, x in hits:
            if alias_ok(x, t, False) and not heading_ok(x, t, H23):
                print('FLIP ' + str(d.relative_to(root)).replace(chr(92), '/') + ' [{}] via {}'.format(t, pname))
    return 0


if __name__ == '__main__':
    sys.exit(main())
