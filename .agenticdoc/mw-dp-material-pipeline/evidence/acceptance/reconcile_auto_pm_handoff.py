"""Verify the bound PM refusal and refresh the single affected v0.5 comparison row."""

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import sys


HERE = Path(__file__).resolve().parent
KEY = HERE.parents[1]
CASE = "dp-auto-original"
RUN = KEY / "evidence/review/normal-entry/dp-auto-original-pm-handoff"
COMPARISON = HERE / "v05-four-stage-comparison.json"
INDEX = HERE / "evidence-index.json"
MARKDOWN = HERE / "v05-four-stage-comparison.md"
PM_RECORD = RUN / "pm-handoff.json"
STATUS = ("matched", "justified-change", "expected-rejection", "fail", "unverified")


def load(path):
    return json.loads(path.read_bytes())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def relative(path):
    return path.relative_to(KEY).as_posix()


def read_handoff(reference, *, run_dir=RUN, source_book_path=HERE / "runs-v05-t09-fixes" / CASE / "decision-book.json"):
    transcript = run_dir / "normal-entry.json"
    run = load(transcript)
    source_book = load(source_book_path)
    assert not run.get("error") and run["case_id"] == CASE and run["role"] == "pm" and run["worker_task"] is None
    inputs = run["author_inputs"]
    assert inputs["dp"] == "dp-auto" and inputs["key"] == run["key"] == source_book["meta"]["key"]
    for field in ("material", "preparation"):
        assert inputs[field] == source_book[field], field
    assert {item["id"] for item in inputs["material"]["handling_options"]} == {"retry", "diagnose"}
    assert "auto_comparison" not in inputs["preparation"]["model_context"]
    assert load(run_dir / "loopback-transcript.json") == []
    assert not (run_dir / "decisions-wire.jsonl").exists() and not (run_dir / "decision-lifecycle.jsonl").exists()
    observation, = run["observations"]
    ask, = observation["tool_results"]
    assert observation["http_delta"] == 0 and ask["tool"] == "ask_decision" and not ask["error"]
    verdict_line, feedback_line, *_ = ask["text"].splitlines()
    verdict = json.loads(verdict_line)
    feedback = json.loads(feedback_line)["decision_feedback"]
    raw = feedback["raw_payload"]
    binding = feedback["binding"]
    assert verdict["available"] is False and verdict["unavailable"] == "input-incomplete"
    assert feedback["origin"] == "mw-decide-run" and feedback["category"] == "input-gap"
    assert feedback["raw_reason"] == "input-incomplete" and feedback["effect_state"] == "none"
    assert binding["role"] == "pm" and binding["owner"] == binding["claim_id"] == feedback["owner"]
    assert binding["key"] == run["key"] and binding["owner"].split(":")[-1] == str(run["window_pid"])
    assert raw["decision_id"] is None and raw["answers"] is None and raw["acted"] is False
    assert raw["transport_attempts"] == raw["business_decisions"] == 0
    issue, = raw["issues"]
    assert issue["field"] == "preparation.model_context.auto_comparison"
    blocked = run_dir / "dp-blocked" / (raw["blocked_event_id"] + ".json")
    host = load(blocked)
    assert host["stage"] == "input-validation" and host["reason"] == verdict["unavailable"]
    assert host["event_id"] == raw["blocked_event_id"] and host["logical_id"] == raw["logical_id"]
    assert host["key"] == run["key"] and host["dp"] == "dp-auto" and host["decision_id"] is None
    assert host["issues"] == raw["issues"]
    reply = run["pm_session_reply"]
    assert reply["role"] == "assistant"
    summary, handoff_line = reply["text"].splitlines()
    assert summary == "blocked on decision dp-auto"
    handoff = json.loads(handoff_line)
    assert handoff["record_kind"] == "current_pm_preflight_handoff"
    assert handoff["disposition"] == reference["disposition"] == "return-material-for-goal-and-path-clarity"
    assert {key: value for key, value in handoff["accepted_by"].items() if key != "actor"} == binding
    assert handoff["accepted_by"]["actor"] and handoff["reason"] and len(handoff["next_steps"]) == 3
    assert all(isinstance(step, str) and step.strip() for step in handoff["next_steps"])
    assert handoff["refusal"] == {
        "code": verdict["unavailable"], "issues": raw["issues"], "blocked_event_id": host["event_id"],
        "feedback_ref": feedback["feedback_ref"], "matter_ref": feedback["matter_ref"], "logical_id": host["logical_id"],
        "transport_attempts": 0, "decision_id": None,
    }
    assert handoff["follow_up_state"] == "pending-source-confirmation" and handoff["business_action_executed"] is False
    assert handoff["historical_runtime_pm_record"] is reference["historical_runtime_pm_record"] is None
    assert reference["actual_business_receipt"] is None and reference["production_executed"] is False
    return {
        **handoff,
        "case_id": CASE,
        "observation_source": "isolated PM session using production ask_decision and mw.py with a scripted PM response",
        "submitted_constraints": inputs["material"]["background"]["constraints"],
        "submitted_book": relative(source_book_path),
        "submitted_book_sha256": digest(source_book_path),
        "session_transcript": relative(transcript),
        "session_transcript_sha256": digest(transcript),
        "blocked_event": relative(blocked),
        "blocked_event_sha256": digest(blocked),
    }


def field_check(row, field, expected, observed, rule):
    return {
        "path": field, "reference": expected, "observed": observed, "rule": rule,
        "result": "expected-rejection",
        "difference_reason": "The old input is refused before send and the current bound PM returns it to preparation.",
        "ac_ids": row["ac_ids"], "vc_ids": row["vc_ids"],
    }


def update():
    report, index = load(COMPARISON), load(INDEX)
    spec_hash = digest(KEY / "spec.md")
    assert spec_hash in (KEY / "design.md").read_text(encoding="utf-8")
    assert report["source_file_sha256"] == index["source_file_sha256"]
    for source, expected in report["source_file_sha256"].items():
        assert digest(KEY.parents[1] / source) == expected, source
    rows = report["rows"]
    expected_cases = load(KEY / "docs/reference-records/index.json")["cases"]
    expected_rows = {(case["case_id"], stage) for case in expected_cases
                     for stage in ("decision_book", "model_input", "model_return", "pm_decision")}
    assert len(rows) == len(expected_rows) == 36
    assert {(row["case_id"], row["stage_id"]) for row in rows} == expected_rows
    for existing in rows:
        assert digest(KEY / existing["reference_path"]) == existing["reference_sha256"]
    row, = [item for item in rows if item["case_id"] == CASE and item["stage_id"] == "pm_decision"]
    ref_path = KEY / row["reference_path"]
    reference = load(ref_path)
    handoff = read_handoff(reference)
    evidence = [relative(PM_RECORD), handoff["session_transcript"], handoff["blocked_event"], handoff["submitted_book"]]
    row["implementation_result"] = {
        "kind": "current-pm-preflight-handoff",
        "evidence": relative(PM_RECORD),
        "current_pm_handoff_joined": True,
        "historical_runtime_pm_record": None,
        "decision_lifecycle_receipt": None,
    }
    row["field_checks"] = [
        field_check(row, "/historical_runtime_pm_record", None, None, "Preserve the recorded absence of historical PM evidence."),
        field_check(row, "/disposition", reference["disposition"], handoff["disposition"],
                    "Return incomplete old material to preparation."),
        field_check(row, "/reason", reference["reasoning"], {"pm_reason": handoff["reason"], "host": handoff["refusal"]},
                    "Tie the reason and zero-send refusal to the current host event."),
        field_check(row, "/current_pm_owner", "bound PM of the replayed matter", handoff["accepted_by"],
                    "Match role, key and live claim from the refusal in the same session."),
        field_check(row, "/next_steps", reference["follow_up"], handoff["next_steps"],
                    "Keep scope, deadline and retry cap while gathering necessary facts."),
        field_check(row, "/business_action_executed", False, handoff["business_action_executed"],
                    "Require no accepted decision or business action for the preflight refusal."),
    ]
    row["status"] = "expected-rejection"
    row["evidence_refs"] = list(dict.fromkeys([*row["evidence_refs"], *evidence]))
    observation = "当前 PM 从正常入口接回 input-incomplete，按原只读范围、五分钟及最多一次重试退回补材料。模型调用 0 次，历史回执仍为空。"
    row["current_pm_handoff"] = {"observation": observation, "evidence_refs": evidence}
    counts = Counter(item["status"] for item in rows)
    assert counts == {"justified-change": 32, "expected-rejection": 4}
    report["summary"] = {name: counts[name] for name in STATUS}
    transitions = Counter((item["prior_status"], item["status"]) for item in rows)
    report["transitions"] = [{"prior_status": before, "status": after, "count": value}
                             for (before, after), value in sorted(transitions.items())]
    report["spec_sha256"] = index["spec_sha256"] = spec_hash
    report["current_pm_handoff_cases"] = {CASE: relative(PM_RECORD)}
    index["current_pm_handoff_cases"] = report["current_pm_handoff_cases"]
    ac017 = index["ac_observations"]["AC-017"]
    if ac017.get("status") == "signed-off":
        refreshed = (json.dumps(report, indent=2, ensure_ascii=False) + "\n").replace("\n", os.linesep).encode("utf-8")
        assert ac017["signed_spec_sha256"] == spec_hash
        assert ac017["signed_comparison_sha256"] == hashlib.sha256(refreshed).hexdigest(), "changed comparison requires review"
    else:
        ac017.update(status="current-evidence-complete-awaiting-independent-review",
                     evidence_refs=[relative(COMPARISON), *evidence])

    markdown = MARKDOWN.read_text(encoding="utf-8")
    markdown, changed = re.subn(r"^36 项中 .*$",
        "36 项中 32 项差异有据、4 项符合预期拒绝、0 项失败、0 项待证。旧 dp-auto 的历史回执仍为空，第四段采用本次 PM 接回记录。",
        markdown, count=1, flags=re.M)
    assert changed == 1
    markdown, changed = re.subn(r"^\| dp-auto-original \| 原主体裁定 \|.*$",
        f"| {CASE} | 原主体裁定 | unverified | expected-rejection | {observation} | "
        f"[PM 接回](../../{relative(PM_RECORD)}) · [正常入口](../../{handoff['session_transcript']}) · "
        f"[拒绝事件](../../{handoff['blocked_event']}) |",
        markdown, count=1, flags=re.M)
    assert changed == 1
    save(PM_RECORD, handoff)
    save(COMPARISON, report)
    save(INDEX, index)
    MARKDOWN.write_text(markdown, encoding="utf-8")


def verify(spec=KEY / "spec.md"):
    report, index = load(COMPARISON), load(INDEX)
    handoff = read_handoff(load(KEY / "docs/reference-records/dp-auto-original/pm-reference-decision.json"))
    assert load(PM_RECORD) == handoff
    row, = [item for item in report["rows"] if item["case_id"] == CASE and item["stage_id"] == "pm_decision"]
    assert row["status"] == "expected-rejection" and len(row["field_checks"]) == 6
    assert report["spec_sha256"] == index["spec_sha256"] == digest(spec)
    assert index["current_pm_handoff_cases"][CASE] == relative(PM_RECORD) in row["evidence_refs"]
    assert len(report["rows"]) == 36 and sum(report["summary"].values()) == 36
    assert report["summary"] == dict.fromkeys(STATUS, 0) | {"justified-change": 32, "expected-rejection": 4}
    print(json.dumps({"ac": "AC-017", "evidence": "verified", "summary": report["summary"],
                      "pm_owner": handoff["accepted_by"]["owner"],
                      "blocked_event": handoff["refusal"]["blocked_event_id"],
                      "network_attempts": handoff["refusal"]["transport_attempts"],
                      "historical_runtime_pm_record": handoff["historical_runtime_pm_record"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--spec", type=Path, help="Verify a specific spec snapshot for read-only replay")
    args = parser.parse_args()
    if args.write:
        if args.spec is not None:
            parser.error("--spec can only be used for read-only replay")
        update()
    verify(args.spec or KEY / "spec.md")
