"""Reproduce the pre-fix bounded-window tail scrub in a throwaway copy.

`decision_wire.py` is untracked, so git cannot hand back the audited version.
This script rewrites ONLY the tail scrub (and min_prefix) of a *temp copy* back
to the reported defect (fixed 64 char window, min_prefix=4) so the long-secret
tests can be run RED against it. The worktree module is never touched.

Usage: python revert-scrub-repro.py <path to temp decision_wire.py>
"""
import pathlib
import sys

OLD = '''    def scrub_tail_prefix(self, text: str, window: int = 64) -> tuple[str, bool]:
        """Drop a trailing *partial* secret left by a read/segment cut."""
        if not text or not self.secrets:
            return text, False
        tail = text[-window:] if window > 0 else text[-64:]
        best = 0
        for secret in self.secrets:
            limit = min(len(secret) - 1, len(tail))
            for size in range(limit, self.min_prefix - 1, -1):
                if size > best and tail.endswith(secret[:size]):
                    best = size
                    break
        if best <= 0:
            return text, False
        return text[: len(text) - best], True


'''

path = pathlib.Path(sys.argv[1])
source = path.read_text(encoding="utf-8")
marker = '        """Drop every trailing *partial* secret left by a read/segment cut.'
start = source.index(marker)
body_start = source.rindex("    def scrub_tail_prefix(", 0, start)
next_def = source.index("\ndef _sha256_hex", start)
source = source[:body_start] + OLD + source[next_def + 1 :]
source = source.replace("MIN_SCRUB_PREFIX = 1", "MIN_SCRUB_PREFIX = 4")
assert "MIN_SCRUB_PREFIX = 4" in source
assert "class SubstringRedactor" in source
path.write_text(source, encoding="utf-8", newline="\n")
print(f"reverted tail scrub in {path} to the pre-fix 64 char window / min_prefix=4")
