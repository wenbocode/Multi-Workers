"""Read-only inspection of the PM pre-dispatch inventory (no product writes).

Answers: which root, which exclusions, how many entries - so the R2 capture can
reproduce the same 1891-file window instead of inventing a second one.
"""

from __future__ import annotations

import json
import pathlib
import sys

KEY_ROOT = pathlib.Path(__file__).resolve().parents[5]  # .agenticdoc/mw-dp-consolidation
PRE = KEY_ROOT / "evidence/implementation/t05-r2-pre-dispatch-20261027"


def main() -> int:
    data = json.loads((PRE / "mirror-inventory.json").read_text(encoding="utf-8"))
    print("type", type(data).__name__, "len", len(data))
    keys = list(data)
    top: dict[str, int] = {}
    for key in keys:
        head = key.split("/")[0]
        top[head] = top.get(head, 0) + 1
    print("top-level buckets:")
    for head, count in sorted(top.items(), key=lambda item: -item[1]):
        print(f"  {head}: {count}")
    print("sample 10:")
    for key in keys[:10]:
        print("  ", key, data[key])
    print("last 5:")
    for key in keys[-5:]:
        print("  ", key)
    print("has .agenticdoc key:", any(key.startswith(".agenticdoc") for key in keys))
    print("has node_modules:", any("node_modules" in key for key in keys))
    print("has packages:", any(key.startswith("packages") for key in keys))
    return 0


if __name__ == "__main__":
    sys.exit(main())
