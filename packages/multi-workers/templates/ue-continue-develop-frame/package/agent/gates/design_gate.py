"""Validate module DESIGN structure, source references and a change baseline."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent"))
import ask
import change_record



def snapshot(root):
    return change_record.snapshot(root)


def validate(root, baseline=None):
    ask.check(root)
    config = ask.module_config.load(root)
    if config.get("design_status") != "ready":
        raise ValueError("DESIGN is a draft; complete module design before validation")
    design = (root / "DESIGN.md").read_text(encoding="utf-8-sig")
    headings = re.findall(r"^## (.+)$", design, flags=re.MULTILINE)
    for section in config["design_sections"]:
        if not any(heading.endswith(section) for heading in headings):
            raise ValueError("Missing DESIGN section: " + section)
    for section in re.split(r"(?=^## )", design, flags=re.MULTILINE):
        title = section.splitlines()[0]
        if "Flow" in title or "生命周期" in title or "静态结构" in title:
            diagrams = re.findall(r"```mermaid\s*\n(.*?)```", section, flags=re.DOTALL)
            if not diagrams or not all(re.search(r"(?:flowchart|stateDiagram-v2)\b", diagram) for diagram in diagrams):
                raise ValueError("Missing flow/state diagram: " + title)
            if not ask.NODE_REF.search(section):
                raise ValueError("Diagram requires source node references: " + title)
    current = snapshot(root)
    engineering_records = []
    if baseline:
        if baseline.get("module") != current["module"]:
            raise ValueError("Baseline belongs to another module")
        if baseline["source_sha256"] != current["source_sha256"] and baseline["design_sha256"] == current["design_sha256"]:
            raise ValueError("Source changed; DESIGN requires review and an update explaining its impact")
        engineering_records = change_record.validate(root, baseline)
    return {"status": "passed", "baseline_checked": baseline is not None, "snapshot": current,
            "engineering_records": engineering_records,
            "scope": "Structure, source references and change tracking. Design semantics require review."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, help="Write pre-change hashes to a new file")
    parser.add_argument("--baseline", type=Path, help="Compare against the pre-change snapshot")
    args = parser.parse_args()
    try:
        if args.snapshot:
            with args.snapshot.open("x", encoding="utf-8") as stream:
                json.dump(snapshot(ROOT), stream, indent=2)
            result = {"status": "snapshot_saved", "path": str(args.snapshot)}
        else:
            baseline = json.loads(args.baseline.read_text(encoding="utf-8")) if args.baseline else None
            result = validate(ROOT, baseline)
    except (ValueError, OSError, KeyError) as error:
        result = {"status": "failed", "error": str(error)}
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["status"] == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
