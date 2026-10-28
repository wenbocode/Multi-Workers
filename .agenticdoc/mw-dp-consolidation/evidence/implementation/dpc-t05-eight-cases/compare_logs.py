"""Compare two pytest logs: failing node ids and their first assertion line."""

from __future__ import annotations

import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent


def _read_text(path: pathlib.Path) -> str:
    data = path.read_bytes()
    if data[:2] in (b"\xff\xfe", b"\xfe\xff") or data[:4] in (b"\x00\x00\xfe\xff",):
        return data.decode("utf-16", errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("utf-16", errors="replace")


def parse(path: pathlib.Path) -> dict:
    text = _read_text(path)
    failures: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        match = re.match(r"^_{1,} (test_[\w\[\]\.-]+) _{1,}$", line.strip())
        if match:
            current = match.group(1)
            failures.setdefault(current, [])
            continue
        stripped = line.strip()
        if current and stripped.startswith("E ") and len(failures[current]) < 3:
            failures[current].append(stripped[2:].strip())
    passed = re.search(r"(\d+) passed", text)
    failed = re.search(r"(\d+) failed", text)
    return {
        "log": path.name,
        "passed": int(passed.group(1)) if passed else 0,
        "failed": int(failed.group(1)) if failed else 0,
        "failures": failures,
    }


def main(argv: list[str]) -> int:
    before = parse(pathlib.Path(argv[1]))
    after = parse(pathlib.Path(argv[2]))
    fixed = sorted(set(before["failures"]) - set(after["failures"]))
    remaining = sorted(set(after["failures"]))
    unchanged = [
        name for name in remaining if name in before["failures"] and before["failures"][name] == after["failures"][name]
    ]
    changed = [name for name in remaining if name in before["failures"] and name not in unchanged]
    new = [name for name in remaining if name not in before["failures"]]
    payload = {
        "before": {k: before[k] for k in ("log", "passed", "failed")},
        "after": {k: after[k] for k in ("log", "passed", "failed")},
        "fixed_by_this_change": fixed,
        "remaining_same_failure_reason": unchanged,
        "remaining_changed_failure_reason": {name: {"before": before["failures"].get(name), "after": after["failures"][name]} for name in changed},
        "new_failures": {name: after["failures"][name] for name in new},
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
