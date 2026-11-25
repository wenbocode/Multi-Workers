"""Check module catalogs and design, optionally against the pre-change baseline."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, help="Require post-change design and engineering-record validation")
    args = parser.parse_args()
    result = subprocess.run([sys.executable, "-B", "agent/catalog.py", "--check"], cwd=ROOT)
    if result.returncode:
        return result.returncode
    config = json.loads((ROOT / "agent/module.json").read_text(encoding="utf-8-sig"))
    reference_check = ["agent/ask.py", "--check"]
    if args.baseline is not None:
        reference_check = ["agent/gates/design_gate.py", "--baseline", str(args.baseline.resolve())]
    elif config.get("design_status") == "ready":
        reference_check = ["agent/gates/design_gate.py"]
    for command in (reference_check, ["-m", "unittest", "discover", "-s", "agent/tests", "-v"]):
        result = subprocess.run([sys.executable, "-B", *command], cwd=ROOT)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
