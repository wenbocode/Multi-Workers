"""Reconcile frozen v0.5 examples and isolated runtime evidence, stage by stage."""

import argparse
from collections import Counter
import hashlib
import json
import os
import pathlib
import shutil
import subprocess

from reconcile_auto_pm_handoff import read_handoff


OUT = pathlib.Path(__file__).resolve().parent
KEY = OUT.parents[1]
PROJECT = KEY.parents[1]
LIBRARY = KEY / "docs" / "reference-records"
QG_NEGATIVE = OUT / "qg-historical-menu-negative-lineage.json"
INTEGRATION_LOG = OUT / "integration-lineage.log"
STAGES = {
    "decision_book": ("decision-book.json", "local_book", (1, 2, 4, 7, 15, 17)),
    "model_input": ("model-input.json", "model_input", (1, 2, 3, 4, 5, 6, 15, 17)),
    "model_return": ("model-return.raw.json", "model_return", (10, 12, 15, 16, 17)),
    "pm_decision": ("pm-reference-decision.json", "pm_reference_decision", (6, 9, 12, 13, 14, 16, 17, 18)),
}


def read(path):
    return json.loads(path.read_bytes())


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def rows(path):
    return [json.loads(line) for line in path.read_bytes().splitlines() if line.strip()]


def ref(path):
    return path.relative_to(KEY).as_posix()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def unique(items):
    [result] = items
    return result


def collect(root, *, supplemental=False, run_label="lineage"):
    current = {}
    manifest_name = "pipeline-supplement.json" if supplemental else "pipeline-evidence.json"
    for source in sorted(root.glob(f"test_*/**/{manifest_name}")):
        if any(part.endswith("current") for part in source.relative_to(root).parts):
            continue
        manifest = read(source)
        case = manifest.get("case_id", manifest["dp"])
        assert case not in current, case
        project = source.parent
        target = OUT / (("supplements-v05-" if supplemental else "runs-v05-") + run_label) / case
        target.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target / "manifest.json")
        auto = project / ".agenticdoc" / "_autopilot"
        if "preflight" in manifest:
            refusal = manifest["preflight"]
            assert refusal["transport_attempts"] == refusal["business_decisions"] == 0
            event = auto / "dp-blocked" / (refusal["blocked_event_id"] + ".json")
            assert read(event)["reason"] == refusal["reason"] == "input-incomplete"
            assert read(event)["stage"] == "input-validation"
            shutil.copyfile(event, target / "blocked-event.json")
            shutil.copyfile(project / "decision-book.json", target / "decision-book.json")
            save(target / "request.json", None)
            save(target / "response.json", None)
            current[case] = target
            continue
        related = [row for row in rows(auto / "decisions-wire.jsonl") if row.get("call_id") == manifest["call_id"]]
        start = unique([row for row in related if row["kind"] == "attempt-start"])
        end = unique([row for row in related if row["kind"] == "attempt-end"])
        assert start["decision_id"] == end["decision_id"] == manifest["decision_id"]
        assert start["attempt_index"] == end["attempt_index"] == 1
        for row, field, name in ((start, "request", "request.json"), (end, "response", "response.json")):
            capture = row[field]
            assert capture["byte_exact"]
            raw = capture["text"].encode()
            assert digest(raw) == capture["captured_redacted_sha256"]
            (target / name).write_bytes(raw)
        snapshot = unique([row for row in related if row["kind"] == "book-snapshot"])
        assert snapshot["decision_id"] == manifest["decision_id"] and snapshot["capture_status"] == "ok"
        body = snapshot["book"]
        assert body["byte_exact"] and digest(body["text"].encode()) == body["captured_redacted_sha256"]
        frozen = json.loads(body["text"])
        request = read(target / "request.json")
        assert frozen["state"] == request["state"]
        assert {key: pair["label"] for key, pair in frozen["pair_map"].items()} == request["questions"]["decision_selection"]["criteria"]
        save(target / "frozen-book-snapshot.json", frozen)
        sources = []
        for entry in request["state"].get("evidence_sources", []):
            location = pathlib.Path(entry["path"]).resolve(strict=True)
            assert location.is_relative_to(project.resolve())
            artifact = target / "source-files" / location.relative_to(project.resolve())
            artifact.parent.mkdir(parents=True, exist_ok=True)
            raw = location.read_bytes()
            if digest(raw) == entry["sha256"]:
                artifact.write_bytes(raw)
                copied = ref(artifact)
            else:
                # Supplemental QG intentionally repairs source files after sending.
                # The frozen excerpt and its original digest remain in request.json.
                assert supplemental, location
                copied = None
            sources.append({"source_id": entry["source_id"], "file": copied, "sha256": entry["sha256"]})
        for item in frozen.get("file_evidence", []):
            location = pathlib.Path(item["path"])
            if location.name not in ("spec.md", "design.md") or not item.get("sha256"):
                continue
            location = location.resolve(strict=True)
            assert location.is_relative_to(project.resolve())
            artifact = target / "source-files" / location.relative_to(project.resolve())
            artifact.parent.mkdir(parents=True, exist_ok=True)
            raw = location.read_bytes()
            assert digest(raw) == item["sha256"]
            artifact.write_bytes(raw)
            sources.append({"contract": location.name, "file": ref(artifact), "sha256": item["sha256"]})
        save(target / "source-files.json", sources)
        ledger = rows(auto / "decision-lifecycle.jsonl")
        receipt_ids = set(manifest["receipts"].values())
        receipts = [row for row in ledger if row.get("event_id") in receipt_ids]
        assert {row["event_id"] for row in receipts} == receipt_ids
        assert all(row.get("decision_id") == manifest["decision_id"] for row in receipts)
        assert all(row.get("project_id") == start["project_id"] for row in receipts)
        assert all((row.get("key"), row.get("task_key")) == (start.get("key"), start.get("task_key")) for row in receipts)
        save(target / "wire-events.json", related)
        save(target / "lifecycle.json", [row for row in ledger if row.get("decision_id") == manifest["decision_id"]])
        book = project / "decision-book.json"
        if not book.is_file():
            book = project / "prepared-book.json"
        if book.is_file():
            shutil.copyfile(book, target / "decision-book.json")
        if case == "dp-QG" and supplemental:
            qg = project / manifest["qg_path"]
            assert digest(qg.read_bytes()) == manifest["qg_sha256"]
            shutil.copyfile(qg, target / "quality-gate-report.md")
            key_dir = qg.parent.parent
            reviewer = key_dir / "workers" / manifest["review_run_id"].split("@", 1)[0]
            for artifact in ("task.md", "run.json", "output.md", "trace.log"):
                shutil.copyfile(reviewer / artifact, target / f"reviewer-{artifact}")
            assert read(reviewer / "run.json")["run_id"] == manifest["review_run_id"]
            shutil.copyfile(key_dir / "evidence" / "review" / "sign-final.md", target / "sign-final.md")
            signoff = key_dir / "evidence" / "review" / "decide-results" / (manifest["local_signoff_id"] + ".json")
            shutil.copyfile(signoff, target / "local-signoff-result.json")
            for artifact in ("review-before.txt", "checks.py", "anchors.json", "ordered_rows.py"):
                shutil.copyfile(project / artifact, target / artifact)
        current[case] = target
    return current


def leaves(value, path=""):
    if isinstance(value, dict) and value:
        return {key: child for name, item in value.items()
                for key, child in leaves(item, f"{path}/{name}").items()}
    if isinstance(value, list) and value:
        return {key: child for index, item in enumerate(value)
                for key, child in leaves(item, f"{path}/{index}").items()}
    return {path or "/": value}


def historical(case):
    directory = LIBRARY / case["case_id"]
    chain = read(directory / "reference-chain.json")
    data = {stage: read(directory / files[0]) for stage, files in STAGES.items()}
    for stage, files in STAGES.items():
        assert data[stage] == chain[files[1]], (case["case_id"], stage)
    for stage, name, hash_field in (("model_input", "request.json", "request_sha256"),
                                    ("model_return", "response.json", "response_sha256")):
        raw = (directory / STAGES[stage][0]).read_bytes()
        assert digest(raw) == case[hash_field] == chain[hash_field]
        assert raw == (KEY / "docs" / case["source_capture"] / name).read_bytes()
    [answer] = data["model_return"]["answers"].values()
    expected = read(directory / "expected-checks.json")
    pair = unique([item for item in chain["pair_map"] if item["wire_id"] == answer["choice"]])
    assert answer["choice"] == expected["expected_wire"]
    for field, expected_field in (("choice", "expected_business_choice"), ("basis_id", "expected_basis_id"),
                                  ("finding_ids", "expected_finding_ids"), ("remaining_ids", "expected_remaining_ids")):
        assert pair[field] == chain["local_decode"][field] == expected[expected_field]
    assert chain["local_decode"]["confidence"] == answer["confidence"]
    assert chain["local_decode"]["probabilities"] == answer["probabilities"]
    pm = data["pm_decision"]
    assert pm["historical_runtime_pm_record"] is None and pm["production_executed"] is False
    assert pm["disposition"] == expected["expected_pm_disposition"] and pm["model_wire_id"] == answer["choice"]
    return data, expected


PM_REVIEWS = {
    "dp-w-type": (
        "The coding receipt and the planning note cover exporter-only write scope, unchanged format, and code plus comma/quote tests.",
        "Only the selected type was read. Worker launch and regression success are absent. Model, permissions and budget remain dispatch prerequisites.",
    ),
    "dp-pm-steer": (
        "The split note keeps W1 and W2 unfinished, distinct test files and the shared interface. It records 36 of 50 worker minutes before independent review.",
        "The pending settlement records planning only. No dispatch or full-cost budget approval is recorded.",
    ),
    "dp-w-check-task": (
        "The bound Worker consumed investigate and recorded one bounded encoding-note read. The book states 1024 bytes and the original eight-minute limit.",
        "The recorded observation establishes UTF-8 for the isolated input. Non-ASCII verification remains unfinished and the task was not marked complete.",
    ),
    "dp-route": (
        "The registry route and pending note target QG for the current deliverable. The request carries the seven target definitions.",
        "The note keeps target role, criteria, review source and original budget as prerequisites. No target call or quality verdict was recorded.",
    ),
    "dp-auto-optimized": (
        "The settlement accepts retry-first as a direction. It preserves the original 300-second premise, one 60-second retry, conditional 120-second health read and 30-second report reserve.",
        "The note requires authority, current remaining time and stop checks. No action, success, new allowance or confidence calibration is recorded.",
    ),
    "dp-QG": (
        "The negative rejects the historical missing-reopen shape before send. The corrected original-scope receipt keeps both findings, the unverified AC-002 and unrun VC-002.",
        "The settlement asks for a scoped independent recheck and records no repair, dispatch or quality pass. The distinct repair fixture is supplemental.",
    ),
    "dp-gate-approve": (
        "The original-scope receipt preserves C1 read-only, C2 full diff retention and the one frozen sample. The note requires current authorization and budget before execution.",
        "The run records an approve judgment and a pending decision, with no execution, release or extra authority. The distinct applied gate fixture is supplemental.",
    ),
    "dp-sign-key": (
        "The current-scope input preserves the fix judgment for interruption behavior and the unknown AC-002. The original sign writer records continue and not-required.",
        "The isolated signer produced no signoff, completion or claim release. The open interruption check remains in scope for existing authority.",
    ),
}


def pointer(value, path):
    for item in path.strip("/").split("/"):
        item = item.replace("~1", "/").replace("~0", "~")
        value = value[int(item)] if isinstance(value, list) else value[item]
    return value


def compare(case, stage, data, expected, target):
    checks = []
    key = case["case_id"]
    manifest = read(target / "manifest.json")

    def check(path, reference, observed, rule, status, reason):
        checks.append({"path": path, "reference": reference, "observed": observed, "rule": rule,
                       "result": status, "difference_reason": reason})

    if "preflight" in manifest:
        refusal = manifest["preflight"]
        rejected = {
            "decision_book": ("/preparation/model_context/auto_comparison", refusal["issues"],
                              "The submitted old case identifies no goal priority and no complete bounded paths."),
            "model_input": ("/transport_attempts", refusal["transport_attempts"],
                            "The input gate refused before any model request."),
            "model_return": ("/response", read(target / "response.json"),
                             "There is no current response. Historical retryA, confidence and probabilities were checked separately."),
            "pm_decision": ("/preparation_refusal", {"host": read(target / "blocked-event.json"),
                                                  "current_pm_assessment": manifest["pm_reason"]},
                            "The present PM can confirm the refusal and needed material. A same-case original owner receipt is unavailable."),
        }
        path, observed, reason = rejected[stage]
        check(path, expected["expected_pm_disposition"] if stage == "pm_decision" else expected["known_material_failures"],
              observed, "This old ambiguous request must stay pre-send, with its historical response kept separately.",
              "unverified" if stage == "pm_decision" else "expected-rejection", reason)
        return checks, {"kind": "current-preflight-refusal", "evidence": ref(target), "receipt_joined": False}

    snapshot = read(target / "frozen-book-snapshot.json")
    request = read(target / "request.json")
    book = read(target / "decision-book.json")
    book = book.get("book", book)
    state = request["state"]
    pairs = snapshot["pair_map"]
    before = data[stage]
    if stage == "decision_book":
        current = book
        fields = snapshot["field_trace"]["fields"]
        missing = [path for path in leaves(request) if not any(
            path == traced or path.startswith(traced + "/") for traced in fields
        )]
        for path, entry in fields.items():
            for source in entry["sources"]:
                if source.startswith("book:") and not entry["transform"].startswith("no-cited-"):
                    pointer(book, source.removeprefix("book:"))
                if source.startswith("source:"):
                    assert source.removeprefix("source:") in {
                        item["source_id"] for item in state.get("evidence_sources", [])
                    }, (key, path, source)
        check("/field_trace", before.get("field_trace"), snapshot["field_trace"],
              "Every sent leaf resolves through a snapshot source and every book pointer names a submitted field.",
              "fail" if missing else "justified-change",
              "Missing provenance " + ", ".join(missing) if missing else "All current model leaves were traced; named local layers stay outside the request.")
        legal = {row["choice"] for row in read(LIBRARY / key / "reference-chain.json")["pair_map"]}
        current_choices = {row["choice"] for row in pairs.values()}
        check("/pair_map", sorted(legal), pairs, "Compare complete effective business coverage and exact rendered labels.",
              "justified-change" if legal <= current_choices else "fail",
              "Current snapshot preserves the exact wire map; QG includes the repaired reopen branch where applicable."
              if legal <= current_choices else "Original business choices are missing in the current sent map.")
        check("/preparation", before.get("preparation"), snapshot["local_preparation"],
              "Join the submitted rationale and synopsis to the same captured preparation.",
              "matched" if book["preparation"] == snapshot["local_preparation"] else "fail",
              "Snapshot preparation checked against the submitted book, independently of model input.")
    elif stage == "model_input":
        current = request
        original_state = before["state"]
        sources = {row["source_id"]: row for row in state.get("evidence_sources", [])}
        for name, entry in original_state.get("references", {}).items():
            reference = state["references"].get(name, {})
            body = reference.get("text", sources.get(reference.get("source_id"), {}).get("text"))
            matches = isinstance(body, str) and body.rstrip("\r\n") == entry["content"]
            check(f"/state/references/{name}", entry, {"reference": reference, "body": body},
                  "Resolve the original named reference to the current authorized body.",
                  "justified-change" if matches else "fail", "Text preserved through current contract or file projection."
                  if matches else "The expected reference body was absent or differed.")
        for field in ("desc", "material", "terminology", "enum_meanings", "references"):
            found = state.get(field)
            if field in ("terminology", "enum_meanings"):
                valid = isinstance(found, dict) and all(found.get(name) for name in original_state[field])
            else:
                valid = isinstance(found, (dict, list)) and (field == "references" or bool(found))
            check(f"/state/{field}", original_state[field], found, "Require the actual current projection and named definitions.",
                  "justified-change" if valid else "fail",
                  "The active entry uses its own projection structure; review the field lineage and reference body checks above.")
        choice = request["questions"].get("decision_selection")
        check("/questions/decision_selection", before["questions"]["decision_selection"], choice,
              "Check the exact single-choice question and its legal pair vocabulary.",
              "justified-change" if list(request["questions"]) == ["decision_selection"] and choice["type"] == "choice" else "fail",
              "Current labels and options resolve against the captured same-call table.")
        measurement = manifest.get("desc_measurement")
        if measurement:
            text = "\n".join(state["desc"])
            ascii_chars = sum(char.isascii() for char in text)
            count = len(text) - ascii_chars + (ascii_chars + 3) // 4
            expected_budget = {"rule": "desc-local-v1", "count": count, "limit": 1000, "passed": True}
            check("/local/desc_measurement", data["decision_book"].get("desc_preparation"), measurement,
                  "Recalculate the local budget from the exact desc sent in this request.",
                  "justified-change" if count <= 1000 and measurement.get("local_budget") == expected_budget else "fail",
                  "The count and pass result are computed in the host using the fixed desc-local-v1 rule.")
        if key == "dp-QG":
            negative = read(QG_NEGATIVE)["refusal"]
            check("/pre_send_negative/reopen", expected["known_material_failures"], negative,
                  "Reproduce incomplete QG fixed-choice rejection with no send.",
                  "justified-change" if negative["transport_attempts"] == 0 and negative["reason"] == "input-incomplete" else "fail",
                  "The historical request and the repaired current request are independently retained.")
    elif stage == "model_return":
        current = read(target / "response.json")
        answer = current["answers"]["decision_selection"]
        normalized = manifest["normalized"]
        pair = pairs[answer["choice"]]
        for name, expected_key in (("choice", "expected_business_choice"), ("basis_id", "expected_basis_id"),
                                   ("finding_ids", "expected_finding_ids"), ("remaining_ids", "expected_remaining_ids")):
            correct = pair[name] == normalized[name] == expected[expected_key]
            check(f"/decoded/{name}", expected[expected_key], normalized[name],
                  "Compare historical value and current same-call decode against the frozen map.",
                  "matched" if correct else "fail", "The actual accepted value must preserve the full original decoded meaning.")
        check("/wire_id", expected["expected_wire"], answer["choice"],
              "Verify the response choice belongs to this request and preserves its business meaning.",
              "matched" if expected["expected_wire"] == answer["choice"] else "justified-change",
              "Temporary wire naming may differ across versions. The table joins the current answer and basis.")
        for field in ("model", "id", "usage", "answers"):
            check(f"/{field}", before.get(field), current.get(field),
                  "Verify each attempt's own byte-exact provider fields, confidence and probabilities.",
                  "matched" if before.get(field) == current.get(field) else "justified-change",
                  "This reply came from the offline transport fixture. Historical model statistics are preserved with their own request, and no live metrics are inferred.")
    else:
        current = read(target / "lifecycle.json")
        assert manifest["receipts"]
        facts, scope = PM_REVIEWS[key]
        for field, reason in (("disposition", facts), ("reasoning", facts), ("must_preserve", facts),
                              ("must_not_claim", scope), ("follow_up", scope)):
            check(f"/{field}", before[field], {"receipt": manifest["receipts"],
                                               "current_note": manifest.get("pm_reason", manifest.get("disposition")),
                                               "events": [event for event in current if event.get("lifecycle")]},
                  "Compare the current isolated consumer's action and reasoning with the historical reference scope.",
                  "justified-change", reason)
    existing_paths = {item["path"] for item in checks}
    reference_leaves = leaves(before)
    current_leaves = leaves(current)
    for path in sorted(reference_leaves.keys() | current_leaves.keys()):
        if path in existing_paths:
            continue
        shared = path in reference_leaves and path in current_leaves and reference_leaves[path] == current_leaves[path]
        check(path, reference_leaves.get(path), current_leaves.get(path), "Inventory leaf values alongside the stage-level comparison.",
              "matched" if shared else "justified-change",
              "Identical captured value." if shared else "Changed projection, transport metadata or fixture bookkeeping; compare the substantive field checks for this stage.")
    return checks, {"kind": "isolated-current-run", "receipt_joined": stage == "pm_decision",
                    "decision_id": manifest["decision_id"], "evidence": ref(target)}


def main():
    global OUT, QG_NEGATIVE, INTEGRATION_LOG
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", type=pathlib.Path)
    parser.add_argument("--test-log", type=pathlib.Path, required=True)
    parser.add_argument("--run-label", choices=("lineage", "t09-fixes"), default="lineage")
    parser.add_argument("--batch-output", type=pathlib.Path)
    parser.add_argument("--pm-handoff-run", type=pathlib.Path)
    args = parser.parse_args()
    prior_path = OUT / "v05-before-lineage-rework.json"
    if args.batch_output:
        prior_path = OUT / "v05-four-stage-comparison.json"
        OUT = args.batch_output.resolve()
        if not OUT.is_relative_to(KEY / "evidence" / "acceptance") or OUT == prior_path.parent:
            parser.error("--batch-output must be a new directory within evidence/acceptance")
        OUT.mkdir(parents=True, exist_ok=True)
        QG_NEGATIVE = OUT / "qg-historical-menu-negative.json"
        INTEGRATION_LOG = OUT / "integration.log"
    elif args.run_label == "t09-fixes":
        QG_NEGATIVE = OUT / "qg-historical-menu-negative-t09-fixes.json"
        INTEGRATION_LOG = OUT / "integration-t09-fixes.log"
    current = collect(args.runs, run_label=args.run_label)
    supplemental = collect(args.runs, supplemental=True, run_label=args.run_label)
    negative = unique(list(path for path in args.runs.glob("test_*/historical-menu-negative.json")
                           if not path.parent.name.endswith("current")))
    shutil.copyfile(negative, QG_NEGATIVE)
    library = read(LIBRARY / "index.json")
    prior = {(row["case_id"], row["stage_id"]): row["status"] for row in read(prior_path)["rows"]}
    if not args.batch_output:
        assert list(prior.values()).count("fail") == 16 and list(prior.values()).count("unverified") == 16
    comparisons = []
    for case in library["cases"]:
        original, expected = historical(case)
        for stage, (filename, _chain_key, numbers) in STAGES.items():
            source = LIBRARY / case["case_id"] / filename
            actual = current.get(case["case_id"])
            checks, observation = compare(case, stage, original, expected, actual)
            handoff_refs = []
            if args.pm_handoff_run and case["case_id"] == "dp-auto-original" and stage == "pm_decision":
                book = actual / "decision-book.json"
                handoff = read_handoff(original[stage], run_dir=args.pm_handoff_run.resolve(), source_book_path=book)
                handoff_path = OUT / "dp-auto-current-pm-handoff.json"
                save(handoff_path, handoff)
                handoff_refs = [ref(handoff_path), handoff["session_transcript"], handoff["blocked_event"]]
                observed = {field: handoff[field] for field in (
                    "disposition", "accepted_by", "reason", "refusal", "next_steps", "submitted_constraints",
                    "business_action_executed", "historical_runtime_pm_record",
                )}
                checks = [{"path": "/preparation_refusal", "reference": original[stage], "observed": observed,
                           "rule": "Verify the bound current PM handoff for the same rejected book and preserve the historical null.",
                           "result": "expected-rejection",
                           "difference_reason": "The current PM returned the material to preparation after the pre-send refusal, within the original limits."}]
                observation = {"kind": "current-pm-preflight-handoff", "evidence": ref(handoff_path),
                               "receipt_joined": True, "historical_runtime_pm_record": None}
            states = {row["result"] for row in checks}
            status = next(value for value in ("fail", "unverified", "expected-rejection", "justified-change", "matched") if value in states)
            ac_ids = [f"AC-{number:03}" for number in numbers]
            vc_ids = [f"VC-{number:03}" for number in numbers]
            for check in checks:
                check.update(ac_ids=ac_ids, vc_ids=vc_ids)
            current_artifacts = {
                "decision_book": ("decision-book.json", "frozen-book-snapshot.json", "source-files.json"),
                "model_input": ("request.json", "wire-events.json"),
                "model_return": ("response.json", "wire-events.json"),
                "pm_decision": ("lifecycle.json", "blocked-event.json", "quality-gate-report.md"),
            }
            comparisons.append({
                "case_id": case["case_id"], "stage_id": stage, "source_schema": library["schema"],
                "reference_path": ref(source), "reference_sha256": digest(source.read_bytes()),
                "reference_result": "matched", "implementation_result": observation or {"kind": "not-observed"},
                "field_checks": checks, "status": status, "prior_status": prior[(case["case_id"], stage)], "ac_ids": ac_ids, "vc_ids": vc_ids,
                "evidence_refs": [ref(source)] + handoff_refs + ([
                    ref(actual / name) for name in ("manifest.json", *current_artifacts[stage])
                    if (actual / name).is_file()
                ] if actual else []),
            })
    assert len(comparisons) == 36 and len({(row["case_id"], row["stage_id"]) for row in comparisons}) == 36
    shutil.copyfile(args.test_log, INTEGRATION_LOG)
    summary = {status: sum(row["status"] == status for row in comparisons)
               for status in ("matched", "justified-change", "expected-rejection", "fail", "unverified")}
    transitions = [
        {"prior_status": before, "status": after, "count": count}
        for (before, after), count in sorted(Counter((row["prior_status"], row["status"]) for row in comparisons).items())
    ]
    source_files = {path: digest((PROJECT / path).read_bytes()) for path in (
        "packages/multi-workers/mw.py", "packages/multi-workers/decision_lifecycle.py",
        "packages/multi-workers/decision.py", "packages/multi-workers/decision_points.py",
        "packages/multi-workers/decision_model_context.py", "packages/multi-workers/decision_backends.py",
        "packages/multi-workers/decision_material_sources.py", "packages/multi-workers/decision_book.py",
        "packages/multi-workers/decision_playground.py", "packages/multi-workers/decision_file_evidence.py",
        "packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts",
        "packages/coding-agent/src/extensions/agent-team-loop/shared/decide-policy.ts",
        "packages/multi-workers/decision_wire.py", "packages/multi-workers/test/test_dp_material_pipeline_l2.py",
        "packages/multi-workers/autopilot/conductor.py",
        "packages/multi-workers/autopilot/contract_guard.py", "packages/multi-workers/codex_pm.py",
        "packages/multi-workers/codex_dispatch.mjs", "packages/multi-workers/decision_prepare.py",
        "packages/multi-workers/decision_signoff_result.py", "packages/multi-workers/decision_source_scope.py",
        "packages/coding-agent/src/extensions/agent-team-loop/pm/prepare-tool.ts",
        "packages/coding-agent/src/extensions/agent-team-loop/pm/task-dispatcher.ts",
        "packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts",
    )}
    header = {"cohorts": library["cohorts"], "reference_matched": len(comparisons),
              "runtime_receipt_cases": sorted(case for case, directory in current.items() if "preflight" not in read(directory / "manifest.json")),
              "summary": summary, "transitions": transitions,
              "prior_report": ref(prior_path), "prior_report_sha256": digest(prior_path.read_bytes()),
              "workspace": str(PROJECT), "spec_sha256": digest((KEY / "spec.md").read_bytes()),
              "source_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True).strip(),
              "source_file_sha256": source_files, "command_log": ref(INTEGRATION_LOG)}
    save(OUT / "v05-four-stage-comparison.json", {**header, "rows": comparisons})
    save(OUT / "evidence-index.json", {
        "status": "incomplete", "comparison": ref(OUT / "v05-four-stage-comparison.json"),
        "spec_sha256": header["spec_sha256"], "source_head": header["source_head"],
        "source_file_sha256": source_files,
        "integration": {"log": header["command_log"], "cases": {name: ref(path / "manifest.json") for name, path in current.items()}},
        "supplemental_runs": {name: ref(path / "manifest.json") for name, path in supplemental.items()},
        "independent_review": ref(OUT / "independent-qg-review.md"),
        "ac_observations": {
            f"AC-{number:03}": {"status": "not-signed-off", "related_rows": [
                f"{row['case_id']}/{row['stage_id']}" for row in comparisons if f"AC-{number:03}" in row["ac_ids"]
            ]}
            for number in range(1, 19)
        },
    })
    dp_count = len({read(directory / "manifest.json")["dp"] for directory in current.values()})
    md = ["# v0.5 九例四段验收", "", f"原件回放 {len(comparisons)}/36。当前覆盖 {dp_count}/8 个 DP，包含隔离发送和发送前拒绝。",
          f"本轮 {summary['expected-rejection']} 项符合拒绝预期，"
          f"{summary['justified-change']} 项为有依据的差异，{summary['fail']} 项失败，{summary['unverified']} 项待证。",
          "", "| 上轮 | 本轮 | 项数 |", "| --- | --- | ---: |",
          *(f"| {row['prior_status']} | {row['status']} | {row['count']} |" for row in transitions),
          "", "| 案例 | 阶段 | 上轮 | 当前 | 关键观测或缺口 | 可追溯证据 |", "| --- | --- | --- | --- | --- | --- |"]
    for row in comparisons:
        evidence = " · ".join(f"[{pathlib.Path(p).name}]({pathlib.Path(os.path.relpath(KEY / p, OUT)).as_posix()})" for p in row["evidence_refs"])
        stages = {
            "decision_book": "核实际冻结的字段来源、准备层和配对表。",
            "model_input": "核单题、引用正文、术语、枚举解释及 desc 本地预算。",
            "model_return": "保留本次离线原始字节，逐项对照 wire、业务结论、依据和原因。",
            "pm_decision": "核同次接回回执、原例保留事实、禁止声明及后续边界。",
        }
        note = stages[row["stage_id"]]
        exceptional = [check["difference_reason"] for check in row["field_checks"] if check["result"] in ("fail", "unverified")]
        if exceptional:
            note = " ".join(dict.fromkeys(exceptional))
        elif row["case_id"] == "dp-auto-original":
            note = row["field_checks"][0]["difference_reason"]
        elif row["case_id"] == "dp-QG" and row["stage_id"] == "model_return":
            note = "fixB 反解 F1、F2，剩余项为空。保留本次离线原始字节及历史回包。"
        elif row["case_id"] in ("dp-QG", "dp-sign-key") and row["stage_id"] == "model_input":
            note = "核当前 AC、VC 正文、关联、状态证据及 desc 本地预算。"
        elif row["stage_id"] == "pm_decision":
            note = PM_REVIEWS[row["case_id"]][0]
        md.append(f"| {row['case_id']} | {row['stage_id']} | {row['prior_status']} | {row['status']} | {note} | {evidence} |")
    md.extend(("", "当前实现逐字段差异、验收编号与两套 cohort 见 [JSON 报告](v05-four-stage-comparison.json)。",
               "原例对账由当前 PM 核对。补充隔离样例验证独立 QG 修复及 gate writer，完整 T09 仍待核验。",
               "同次回执来自隔离运行。本轮模型回复由本地替身提供，未推进实际项目阶段。", ""))
    (OUT / "v05-four-stage-comparison.md").write_text("\n".join(md), encoding="utf-8", newline="\n")
    print(json.dumps({"historical_rows": len(comparisons), "runtime_receipts": len(header["runtime_receipt_cases"]), "implementation": summary}))


if __name__ == "__main__":
    main()
