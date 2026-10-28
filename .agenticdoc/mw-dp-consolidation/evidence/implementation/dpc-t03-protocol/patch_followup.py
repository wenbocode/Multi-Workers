"""T03 follow-up patch (red -> green iteration 1).

The first green run found one real gap: ``entry_choice_issues`` accepted a
selection out of a one-candidate ``handling_options`` set because it only
validated the selection's membership in the (non-empty) candidate ids. The
prepared candidate set is part of the answer contract, so the choice validator
must carry the same ``entry_candidates_issues`` rule. This script applies exactly
that one anchored edit (CRLF-preserving) and fails loudly if the anchor drifted.

Usage: python patch_followup.py <decision_points.py>
"""

from __future__ import annotations

import hashlib
import pathlib
import sys

TARGET = pathlib.Path(sys.argv[1])

OLD = """    issues: list[tuple[str, str]] = []
    legal = resolve_entry_choices(dp_id, material)
    if entry.kind == "dynamic-candidates" and not legal:"""

NEW = """    issues: list[tuple[str, str]] = []
    legal = resolve_entry_choices(dp_id, material)
    if entry.kind == "dynamic-candidates":
        prepared = (
            material.get(entry.candidate_source.split(":", 1)[1])
            if isinstance(material, Mapping)
            else None
        )
        # The PM-prepared set is part of the answer contract: a selection out of
        # a one-candidate / duplicate-id / incomplete set is not legal either.
        issues.extend(entry_candidates_issues(dp_id, prepared))
    if entry.kind == "dynamic-candidates" and not legal:"""


def main() -> int:
    raw = TARGET.read_bytes()
    before = hashlib.sha256(raw).hexdigest()
    text = raw.decode("utf-8")
    eol = "\r\n" if b"\r\n" in raw else "\n"
    text = text.replace("\r\n", "\n")
    if text.count(OLD) != 1:
        raise SystemExit(f"anchor found {text.count(OLD)} times")
    TARGET.write_bytes(text.replace(OLD, NEW, 1).replace("\n", eol).encode("utf-8"))
    print(f"patched {TARGET}")
    print(f"sha_before={before}")
    print(f"sha_after={hashlib.sha256(TARGET.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
