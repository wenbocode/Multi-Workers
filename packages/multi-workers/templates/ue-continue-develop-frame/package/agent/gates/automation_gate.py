"""Run one implemented UE AutomationTest and inspect its native JSON report."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent"))
import ask


def validate_report(report, name):
    matches = [test for test in report.get("tests", []) if test.get("fullTestPath") == name]
    if len(matches) != 1:
        raise ValueError("Expected exactly one report entry for " + name)
    test = matches[0]
    if test.get("state") != "Success" or test.get("errors", 0):
        raise ValueError("AutomationTest failed: " + name)
    return {"fullTestPath": name, "state": test["state"], "warnings": test.get("warnings", 0)}


def command(case, editor, project, map_name, report):
    config = ask.module_config.load(ROOT).get('ue', {})
    plugin = []
    if config.get('descriptor'):
        plugin = ['-PLUGIN=' + str(ask.local_path(ROOT, config['descriptor'])), '-EnablePlugins=' + config['plugin_name']]
    return [str(editor), str(project), map_name, *plugin,
            "-unattended", "-nosplash", "-nosound", "-nop4", "-NoLiveCoding",
            "-ExecCmds=Automation RunTests " + case["name"], "-TestExit=Automation Test Queue Empty",
            "-ReportExportPath=" + str(report), "-abslog=" + str(report / "editor.log")]



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    parser.add_argument("--editor", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--map", default="/Engine/Maps/Entry")
    parser.add_argument("--report-root", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=1200)
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()
    result = {}
    report = None
    try:
        data = ask.load_package(ROOT)
        case = next((row for row in data["testcases"] if row["case_id"] == args.case), None)
        if not case:
            raise ValueError("Unknown testcase")
        target = args.report_root.resolve() / (args.case + "-" + uuid.uuid4().hex)
        argv = command(case, args.editor.resolve(), args.project.resolve(), args.map, target)
        if args.plan:
            result = {"status": "planned", "argv": argv, "preconditions": case["preconditions"],
                      "case_status": case["status"], "expected": case["expected"]}
        else:
            if case["status"] != "accepted":
                raise ValueError("Testcase requires individual human confirmation: " + args.case)
            if data["stale_sources"]:
                raise ValueError("Source index is stale")
            if not args.editor.is_file() or not args.project.is_file() or args.timeout <= 0:
                raise ValueError("Editor, project and positive timeout are required")
            runtime = ask.module_config.load(ROOT).get('ue', {}).get('cases', {}).get(case['case_id'], {})
            if runtime.get('map') and args.map != runtime['map']:
                raise ValueError('This testcase requires ' + runtime['map'])
            target.mkdir(parents=True, exist_ok=False)
            report = target
            result = {"status": "running", "argv": argv, "source_revision": data["source_revision"],
                      "case_sha256": ask.item_digest([row for row in data["testcases"] if row["case_id"] == args.case], ROOT)}
            with (target / "console.log").open("wb") as stream:
                process = subprocess.run(argv, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=args.timeout)
            if process.returncode:
                raise ValueError("Editor exit code " + str(process.returncode))
            native = json.loads((target / "index.json").read_text(encoding="utf-8-sig"))
            result["test"] = validate_report(native, case["name"])
            current = ask.fingerprint(ROOT, ask.module_config.source_files(ROOT))
            if current != result["source_revision"]:
                raise ValueError("Source changed during test run")
            result["status"] = "passed"
            result["report"] = str(target / "index.json")
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        result.update(status="failed", error=str(error))
    if report:
        (report / "gate-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["status"] == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
