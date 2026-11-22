"""Independent subprocess checks for the isolated QG repair example."""

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile


ASSERTION = "assert ordered_rows(rows) == rows"
IMPLEMENTATION = "ordered_rows.py"
CHECKS = "checks.py"
ANCHORS = "anchors.json"
INPUTS = (IMPLEMENTATION, CHECKS, ANCHORS)


def check_ordering(project: Path, files: dict[str, bytes], lines: list[str]) -> str | None:
    assertion_lines = [index for index, line in enumerate(lines, 1) if line.strip() == ASSERTION]
    if len(assertion_lines) != 1:
        return "checks.py must contain one explicit assertion for input row order."
    implementation = files[IMPLEMENTATION]
    original_return = b"return tuple(rows)"
    if implementation.count(original_return) != 1:
        return "Could not isolate the original row-return statement for the ordering probe."
    if project.parent == project:
        return "Could not allocate a scratch directory outside the reviewed project."
    with tempfile.TemporaryDirectory(prefix="qg-order-review-", dir=project.parent) as directory:
        snapshot = Path(directory)
        for name in (CHECKS, IMPLEMENTATION):
            (snapshot / name).write_bytes(files[name])
        argv = [sys.executable, "-B", "-E", "-S", str(snapshot / CHECKS)]
        confirmed = subprocess.run(argv, cwd=snapshot, capture_output=True, text=True, timeout=15, check=False)
        if confirmed.returncode != 0:
            return f"checks.py exited {confirmed.returncode} on the observed implementation: {confirmed.stderr.strip()}"
        (snapshot / IMPLEMENTATION).write_bytes(implementation.replace(original_return, b"return tuple(sorted(rows))"))
        mutated = subprocess.run(argv, cwd=snapshot, capture_output=True, text=True, timeout=15, check=False)
    traceback_line = rf'^  File "[^"\r\n]*[\\/]checks\.py", line {assertion_lines[0]}, in '
    if mutated.returncode == 0:
        return "checks.py accepted an implementation that sorted away the original row order."
    if not re.search(traceback_line, mutated.stderr, re.MULTILINE) or not mutated.stderr.rstrip().endswith("AssertionError"):
        return f"The altered implementation exited {mutated.returncode} without failing the ordering assertion: {mutated.stderr.strip()}"
    return None


def check_anchor(raw: bytes, lines: list[str]) -> str | None:
    try:
        anchor = json.loads(raw)["ordering_assertion"]
        path, line = anchor["path"], anchor["line"]
    except (TypeError, ValueError, KeyError):
        return "anchors.json lacks a valid ordering_assertion path and line."
    if path != CHECKS or type(line) is not int or not 1 <= line <= len(lines):
        return "The ordering_assertion anchor must name checks.py and an existing one-based line."
    if lines[line - 1].strip() != ASSERTION:
        return f"The ordering_assertion anchor points to checks.py:{line}, which does not contain the ordering assertion."
    return None


def main(project: Path) -> int:
    try:
        files = {name: (project / name).read_bytes() for name in INPUTS}
        lines = files[CHECKS].decode("utf-8-sig").splitlines()
        anchor_failure = check_anchor(files[ANCHORS], lines)
        try:
            ordering_failure = check_ordering(project, files, lines)
        except (OSError, subprocess.TimeoutExpired) as error:
            ordering_failure = f"Could not complete the ordering probe: {error}"
        unchanged = all((project / name).read_bytes() == files[name] for name in INPUTS)
    except (OSError, UnicodeError) as error:
        print(f"Unable to read the isolated review inputs: {error}", file=sys.stderr)
        return 2

    if ordering_failure:
        print(f"AC-001 / VC-001 FAIL: {ordering_failure}", file=sys.stderr)
    if anchor_failure:
        print(f"AC-002 / VC-002 FAIL: {anchor_failure}", file=sys.stderr)
    if not unchanged:
        print("Reviewed files changed during the audit. Retry against a frozen snapshot.", file=sys.stderr)
    if ordering_failure or anchor_failure or not unchanged:
        return 1

    print("## Quality Gate Report\n")
    print("| ID | Status | Evidence |\n| --- | --- | --- |")
    for identifier, name in (
        ("AC-001", CHECKS),
        ("AC-002", ANCHORS),
        ("VC-001", CHECKS),
        ("VC-002", ANCHORS),
        ("FLOW-001", IMPLEMENTATION),
    ):
        print(f"| {identifier} | PASS | {name}@{hashlib.sha256(files[name]).hexdigest()} |")
    print(
        "\n## Achieved\n\n"
        "The isolated repair now checks input row order with unsorted input. The original "
        "implementation passed that check, and the deliberately sorted implementation failed "
        "at the exact ordering assertion. The evidence index resolves to that assertion in the "
        "same observed revision. Both review probes ran without modifying the reviewed project."
    )
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {Path(sys.argv[0]).name} PROJECT_ROOT", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(Path(sys.argv[1]).resolve()))
