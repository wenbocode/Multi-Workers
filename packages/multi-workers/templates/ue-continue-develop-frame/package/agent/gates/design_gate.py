"""Plan a DESIGN refresh and validate the result against a pre-change baseline."""
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


def source_hashes(root):
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in ask.module_config.source_files(root)}


def check_baseline(baseline, module):
    if (not isinstance(baseline, dict) or not isinstance(baseline.get("records"), dict)
            or not all(isinstance(baseline.get(key), str) and baseline[key]
                       for key in ("module", "source_sha256", "design_sha256", "implementation_sha256"))):
        raise ValueError("Use a pre-change v2 snapshot from design_gate.py --snapshot")
    if baseline["module"] != module:
        raise ValueError("Baseline belongs to another module")


def refresh_plan(root, baseline):
    current = change_record.inputs(root)
    check_baseline(baseline, current["module"])
    old = baseline.get("source_files")
    changes = None
    if old is not None:
        if not isinstance(old, dict) or not all(isinstance(value, str) for value in old.values()):
            raise ValueError("Invalid source file digests in baseline")
        new = source_hashes(root)
        changes = {
            "added": sorted(new.keys() - old.keys()),
            "modified": sorted(path for path in new.keys() & old.keys() if new[path] != old[path]),
            "removed": sorted(old.keys() - new.keys()),
        }
    return {
        "status": "planned",
        "module": current["module"],
        "source_changed": current["source_sha256"] != baseline["source_sha256"],
        "design_changed": current["design_sha256"] != baseline["design_sha256"],
        "implementation_changed": current["implementation_sha256"] != baseline["implementation_sha256"],
        "source_changes": changes,
    }


def validate(root, baseline=None):
    ask.check(root)
    config = ask.module_config.load(root)
    design = (root / "DESIGN.md").read_text(encoding="utf-8-sig")
    if config.get("design_status") != "ready" or not design.strip() or "（草稿）" in design.splitlines()[0]:
        raise ValueError("DESIGN is a draft; complete module design before validation")
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
    current = change_record.snapshot(root)
    engineering_records = []
    if baseline is not None:
        check_baseline(baseline, current["module"])
        if baseline["source_sha256"] != current["source_sha256"] and baseline["design_sha256"] == current["design_sha256"]:
            raise ValueError("Source changed; DESIGN requires review and an update explaining its impact")
        engineering_records = change_record.validate(root, baseline)
    return {"status": "passed", "baseline_checked": baseline is not None, "snapshot": current,
            "engineering_records": engineering_records,
            "scope": "Structure, source references and change tracking. Design semantics require review."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--snapshot", type=Path, help="Write pre-change hashes to a new file")
    mode.add_argument("--refresh-plan", action="store_true", help="Report changed source paths from --baseline as JSON")
    parser.add_argument("--baseline", type=Path, help="Compare against the pre-change snapshot")
    args = parser.parse_args()
    if args.refresh_plan and args.baseline is None:
        parser.error("--refresh-plan requires --baseline")
    if args.snapshot and args.baseline is not None:
        parser.error("--snapshot cannot be combined with --baseline")
    try:
        if args.snapshot:
            snapshot = dict(change_record.snapshot(ROOT), source_files=source_hashes(ROOT))
            with args.snapshot.open("x", encoding="utf-8") as stream:
                json.dump(snapshot, stream, indent=2)
            result = {"status": "snapshot_saved", "path": str(args.snapshot)}
        elif args.baseline is not None:
            baseline = json.loads(args.baseline.read_text(encoding="utf-8-sig"))
            if not isinstance(baseline, dict):
                raise ValueError("Expected a pre-change baseline JSON object")
            result = refresh_plan(ROOT, baseline) if args.refresh_plan else validate(ROOT, baseline)
        else:
            result = validate(ROOT)
    except (ValueError, OSError, KeyError) as error:
        result = {"status": "failed", "error": str(error)}
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["status"] == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
