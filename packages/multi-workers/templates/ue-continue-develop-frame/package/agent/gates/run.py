"""Dispatch a confirmed gate to its module-local implementation."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent"))
import ask


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate", required=True)
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("runner_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        data = ask.load_package(ROOT)
        rows = [row for row in data["gates"] if row["gate_id"] == args.gate]
        if not rows:
            raise ValueError("Unknown gate")
        implementations = {(row["runner"], row["args"]) for row in rows}
        if len(implementations) != 1:
            raise ValueError("Gate has inconsistent implementation")
        runner, fixed = implementations.pop()
        extra = args.runner_args[1:] if args.runner_args[:1] == ["--"] else args.runner_args
        if any(value.split("=", 1)[0] in ("--case", "--plan", "--snapshot") for value in extra):
            raise ValueError("Runner arguments cannot override the approved gate action")
        if runner == "agent/gates/package_gate.py" and extra:
            raise ValueError("Package gate takes no runtime arguments")
        fixed_args = json.loads(fixed)
        argv = [sys.executable, "-B", str(ask.local_path(ROOT, runner)), *fixed_args, *extra]
        if args.plan:
            print(json.dumps({"gate": args.gate, "status": rows[0]["status"], "argv": argv,
                              "item_sha256": ask.item_digest(rows, ROOT)}, ensure_ascii=False, indent=2))
            return 0
        if rows[0]["status"] != "accepted":
            raise ValueError("Gate requires individual human confirmation: " + args.gate)
        if args.gate == "G-DESIGN" and (fixed_args or len(extra) != 2 or extra[0] != "--baseline"):
            raise ValueError("DESIGN update gate takes only --baseline <pre-change snapshot>")
        return subprocess.run(argv, cwd=ROOT).returncode
    except (ValueError, OSError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
