"""Mutant checks for card T05 (``test_decision_observation.py``).

Each mutation is applied in-process to the imported ``decision_points`` module
and then the observation suite is run against it. A mutation that leaves the
suite green would mean the tests do not actually observe the behaviour they
claim (self-certifying tests); the expected result is a non-zero pytest exit
with the behavioural tests failing.

The working tree is never modified: the patches live in this process only.
Run from ``packages/multi-workers``:

    python ../../.agenticdoc/mw-decision-dashboard/evidence/runs/T05-observation-seam/mutant-check.py <mutant>
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[5] / "packages" / "multi-workers"))

import pytest  # noqa: E402

import decision_points as dpts  # noqa: E402


def _mutant_pairing() -> str:
    """Drop the paired observation contract (intent/archive/scope validation)."""

    def noop(*args, **kwargs):
        return None

    dpts._validate_observation = noop
    return "observation pairing validation disabled"


def _mutant_trace() -> str:
    """Stop recording the archive signal (every decision would read not-attempted)."""

    def noop(self, state):
        return None

    dpts._ArchiveTrace.mark = noop
    return "archive trace disabled"


def _mutant_capture() -> str:
    """Never create/bind a capture scope (production capture silently missing)."""

    def no_scope(*args, **kwargs):
        return None, "production-scope"

    dpts._capture_scope = no_scope
    return "capture scope creation disabled"


MUTANTS = {
    "pairing": (_mutant_pairing, "test_decision_observation.py", "not requires_"),
    "trace": (_mutant_trace, "test_decision_observation.py", "not requires_"),
    "capture": (_mutant_capture, "test_decision_observation.py", "not requires_"),
}


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in MUTANTS:
        print(f"usage: {argv[0]} {{{'|'.join(MUTANTS)}}}", file=sys.stderr)
        return 2
    apply, target, selection = MUTANTS[argv[1]]
    description = apply()
    print(f"mutant={argv[1]} description={description}")
    code = pytest.main(
        [
            target,
            "-q",
            "-k",
            selection,
            "-p",
            "no:cacheprovider",
        ]
    )
    print(f"mutant={argv[1]} pytest_exit={int(code)}")
    return 0 if int(code) != 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
