"""Codex-only lifecycle against real CLI processes and the unchanged worker launcher."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

import codex_pm
import change_set
import mw_common
from test_integration import _wait_for, fakebin, proj, start_launcher

CLI = Path(__file__).with_name("codex_pm.py")


def invoke(project, action, *args, key="counter", expected=0):
    result = subprocess.run([sys.executable, str(CLI), action, "--project", str(project), "--key", key, *args],
                            cwd=project, capture_output=True, text=True, encoding="utf-8", timeout=60,
                            env={**os.environ, "PYTHONUTF8": "1", "PI_CODING_AGENT_DIR": str(project / ".pi-agent")})
    assert result.returncode == expected, (result.stdout, result.stderr)
    return json.loads(result.stdout or result.stderr)


def fill(project, key="counter", criteria="- AC-001: Increment returns the next integer."):
    file = project / ".agenticdoc" / key / "codex_doc.md"
    header = file.read_text(encoding="utf-8").split("## 目标")[0]
    file.write_text(header + "## 目标\nImplement the counter.\n## 范围\ncounter.py\n"
                    f"## 验收标准\n{criteria}\n## 接续须知\nResume from this document.\n", encoding="utf-8")


def achieved(project, residual="None.", key="counter"):
    (project / ".agenticdoc" / key / "achieved.md").write_text(
        f"## 系统行为变化\nCounter implemented and independently checked.\n"
        f"## 修改面\n- `counter.py`\n- `check.py`\n"
        f"## 遗留\n{residual}\n", encoding="utf-8")


@pytest.fixture()
def lite(proj):
    invoke(proj, "init")
    fill(proj)
    (proj / "counter.py").write_text("def increment(value): return value + 1\n")
    (proj / "check.py").write_text("from counter import increment\nassert increment(4) == 5\n")
    invoke(proj, "advance", "--phase", "EXECUTE")
    return proj


def test_direct_lifecycle_keeps_real_index_and_complete_projection(lite):
    invoke(lite, "init", key="unrelated")
    before = next(line for line in (lite / ".agenticdoc/_index.parallel").read_text(encoding="utf-8").splitlines()
                  if line.startswith("| unrelated |"))
    check = invoke(lite, "check", "--ac", "AC-001", "--", sys.executable, "check.py")
    assert check["verdict"] == "passed" and Path(check["log"]).is_file()
    invoke(lite, "advance", "--phase", "VERIFY")
    achieved(lite)
    result = invoke(lite, "done", "--summary", "Counter behavior verified")
    assert (result["phase"], result["status"], result["claim_id"]) == ("DONE", "idle", "—")
    state = invoke(lite, "status")
    assert state["phase"] == "DONE" and state["claim"] == "—"
    assert 'active_keys: ["unrelated"]' in (lite / ".agenticdoc/_index.md").read_text(encoding="utf-8")
    assert before in (lite / ".agenticdoc/_index.parallel").read_text(encoding="utf-8")
    directory = lite / ".agenticdoc/counter"
    assert all(not (directory / f"{name}.md").exists() for name in ("spec", "design", "plan"))
    assert "- Phase: init" in (directory / "pm-state.md").read_text(encoding="utf-8")
    invoke(lite, "done", "--summary", "Counter behavior verified")
    assert (lite / ".agenticdoc/_project_log.md").read_text(encoding="utf-8").count("| counter |") == 1
    invoke(lite, "claim", expected=2)


@pytest.mark.parametrize("observe_check_file", [False, True])
def test_completion_requires_write_list_and_records_change_set(lite, observe_check_file):
    invoke(lite, "check", "--ac", "AC-001", "--", sys.executable, "check.py")
    invoke(lite, "advance", "--phase", "VERIFY")
    key_dir = lite / ".agenticdoc/counter"
    (key_dir / "achieved.md").write_text(
        "## 系统行为变化\nCounter implemented.\n## 遗留\nNone.\n", encoding="utf-8")
    refused = invoke(lite, "done", "--summary", "Missing write list", expected=2)
    assert "修改面" in refused["error"]
    assert invoke(lite, "status")["phase"] == "VERIFY"
    achieved(lite)
    change_set.record(lite, "counter", "edit", "counter.py")
    if observe_check_file:
        change_set.record(lite, "counter", "write", "check.py")
    result = invoke(lite, "done", "--summary", "Counter behavior verified")
    assert result["phase"] == "DONE"
    closure = json.loads((key_dir / "evidence/codex-pm/completion.json").read_text(encoding="utf-8"))
    assert Path(closure["change_set"]["change_set"]).is_file()
    data = json.loads((key_dir / "change-set.json").read_text(encoding="utf-8"))
    assert [item["path"] for item in data["files"]] == ["check.py", "counter.py"]
    assert all(item["sha256"] for item in data["files"])
    assert data["coverage"]["machine_sources"] == ["pm-tool-result"]
    assert data["coverage"]["complete"] is observe_check_file
    assert data["coverage"]["declared_paths_missing_from_machine"] == ([] if observe_check_file else ["check.py"])
    assert (key_dir / "change-set.md").is_file()
    assert "修改面" in (key_dir / "achieved.md").read_text(encoding="utf-8")


def test_change_set_flags_machine_writes_missing_from_write_list(lite):
    # Any new file outside .agenticdoc must exist before `check`, whose
    # source_sha256 pins the whole source tree.
    (lite / "extra.py").write_text("x = 1\n", encoding="utf-8")
    invoke(lite, "check", "--ac", "AC-001", "--", sys.executable, "check.py")
    invoke(lite, "advance", "--phase", "VERIFY")
    key_dir = lite / ".agenticdoc/counter"
    change_set.record(lite, "counter", "write", "extra.py")
    achieved(lite)
    invoke(lite, "done", "--summary", "Counter behavior verified")
    data = json.loads((key_dir / "change-set.json").read_text(encoding="utf-8"))
    assert data["coverage"]["machine_paths_missing_from_declared"] == ["extra.py"]
    assert "extra.py" in [item["path"] for item in data["files"]]
    assert data["coverage"]["complete"] is False


def test_completion_excludes_agenticdoc_from_change_set(lite):
    invoke(lite, "check", "--ac", "AC-001", "--", sys.executable, "check.py")
    invoke(lite, "advance", "--phase", "VERIFY")
    key_dir = lite / ".agenticdoc/counter"
    change_set.record(lite, "counter", "write", ".agenticdoc/counter/evidence/x.md")
    (key_dir / "achieved.md").write_text(
        "## 系统行为变化\nCounter implemented.\n## 修改面\n无改动。\n## 遗留\nNone.\n",
        encoding="utf-8")
    invoke(lite, "done", "--summary", "Counter behavior verified")
    data = json.loads((key_dir / "change-set.json").read_text(encoding="utf-8"))
    assert all(not item["path"].startswith(".agenticdoc/") for item in data["files"])
    assert data["files"] == []
    assert data["coverage"]["declared_no_write_acknowledged"] is True


def test_scaffold_requires_real_contract_before_execution(proj):
    assert invoke(proj, "init")["phase"] == "SPEC"
    assert invoke(proj, "status")["checks"] == []
    assert "nonempty" in invoke(proj, "advance", "--phase", "EXECUTE", expected=2)["error"]
    fill(proj)
    file = proj / ".agenticdoc/counter/codex_doc.md"
    file.write_text(file.read_text(encoding="utf-8") + "\n## 目标\nDuplicate.\n", encoding="utf-8")
    assert "Duplicate section" in invoke(proj, "advance", "--phase", "EXECUTE", expected=2)["error"]


def test_release_resume_and_case_identity(lite):
    result = invoke(lite, "release", key="COUNTER")
    assert result["key"] == "counter" and result["phase"] == "EXECUTE" and result["status"] == "idle"
    assert 'active_keys: []' in (lite / ".agenticdoc/_index.md").read_text(encoding="utf-8")
    invoke(lite, "check", "--ac", "AC-001", "--", sys.executable, "check.py", expected=2)
    assert invoke(lite, "claim")["claim_id"] == "codex"
    invoke(lite, "advance", "--phase", "VERIFY")
    invoke(lite, "advance", "--phase", "EXECUTE", expected=2)


def test_parallel_codex_keys_do_not_demote_each_other(proj):
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda key: invoke(proj, "init", key=key), ("one", "two", "three")))
    assert all(result["claim_id"] == "codex" for result in results)
    projection = (proj / ".agenticdoc/_index.md").read_text(encoding="utf-8").split("active_keys: ")[1]
    assert set(json.loads(projection)) == {"one", "two", "three"}


@pytest.mark.parametrize("change", ["source", "contract", "failed-check"])
def test_completion_rejects_stale_or_superseded_acceptance(lite, change):
    invoke(lite, "check", "--ac", "AC-001", "--", sys.executable, "check.py")
    invoke(lite, "advance", "--phase", "VERIFY")
    achieved(lite)
    if change == "source":
        (lite / "counter.py").write_text("def increment(value): return value\n")
    elif change == "contract":
        doc = lite / ".agenticdoc/counter/codex_doc.md"
        doc.write_text(doc.read_text(encoding="utf-8").replace("next integer", "next positive integer"), encoding="utf-8")
    else:
        invoke(lite, "check", "--ac", "AC-001", "--", sys.executable, "-c", "raise SystemExit(1)", expected=1)
    assert "current passing" in invoke(lite, "done", "--summary", "Should fail", expected=2)["error"]
    assert invoke(lite, "status")["phase"] == "VERIFY"


def test_each_criterion_needs_evidence_and_failed_command_is_visible(lite):
    fill(lite, criteria="- AC-001: Counter increments.\n- AC-002: Counter accepts zero.")
    invoke(lite, "check", "--ac", "AC-999", "--", sys.executable, "check.py", expected=2)
    invoke(lite, "check", "--ac", "AC-001", "--", sys.executable, "check.py")
    invoke(lite, "advance", "--phase", "VERIFY")
    achieved(lite)
    invoke(lite, "done", "--summary", "Incomplete coverage", expected=2)
    invoke(lite, "check", "--ac", "AC-002", "--", sys.executable, "check.py")
    assert invoke(lite, "done", "--summary", "Both criteria verified")["phase"] == "DONE"


def test_completion_uses_bound_reviewed_signoff_and_separate_dispositions(lite, monkeypatch):
    invoke(lite, "check", "--ac", "AC-001", "--", sys.executable, "check.py")
    invoke(lite, "advance", "--phase", "VERIFY")
    key_dir = lite / ".agenticdoc/counter"
    signed_achieved = b"## Achieved\n\nCounter implemented and independently checked.\n"
    (key_dir / "achieved.md").write_bytes(signed_achieved)
    monkeypatch.setattr(codex_pm.contract_guard, "read_freeze", lambda _path: {"decision_signoff": "required"})
    with pytest.raises(ValueError, match="current sign-off"):
        codex_pm.complete(lite, key_dir, "Must bind the independent sign-off")
    validation = codex_pm.decision_signoff_result.SignoffValidation(
        valid=True, reason="", record_version=4, native_basis_verified=True,
    )
    monkeypatch.setattr(codex_pm.decision_signoff_result, "validate_signoff", lambda *_: validation)
    with pytest.raises(ValueError, match="结案遗留"):
        codex_pm.complete(lite, key_dir, "Must record dispositions")
    with (key_dir / "codex_doc.md").open("a", encoding="utf-8") as document:
        document.write("\n## 结案遗留\nNo remaining work.\n")
    result = codex_pm.complete(lite, key_dir, "Close on signed review")
    assert (result["phase"], result["status"], result["claim_id"]) == ("DONE", "idle", "—")
    assert (key_dir / "achieved.md").read_bytes() == signed_achieved


@pytest.mark.parametrize("bad_row", [
    "| counter | active | EXECUTE | foreign:1 | — | foreign | now |\n",
    "| COUNTER | active | EXECUTE | codex | — | duplicate | now |\n",
    "| hostile | active | wrong-columns |\n",
])
def test_foreign_or_corrupt_authority_is_never_overwritten(lite, bad_row):
    index = lite / ".agenticdoc/_index.parallel"
    if "foreign:1" in bad_row:
        index.write_text("\n".join(line for line in index.read_text(encoding="utf-8").splitlines()
                                   if not line.startswith("| counter |")) + "\n" + bad_row, encoding="utf-8")
    else:
        index.write_text(index.read_text(encoding="utf-8") + bad_row, encoding="utf-8")
    before = index.read_bytes()
    projection = (lite / ".agenticdoc/_index.md").read_bytes()
    invoke(lite, "claim", expected=2)
    assert index.read_bytes() == before
    assert (lite / ".agenticdoc/_index.md").read_bytes() == projection


def test_projection_partial_failure_is_reported_and_claim_repairs(lite, monkeypatch):
    def fail(*_args):
        raise codex_pm.active_projection.ActiveProjectionError("PARTIAL WRITE: injected projection refusal")

    with monkeypatch.context() as patch:
        patch.setattr(codex_pm.active_projection, "write_projection", fail)
        with pytest.raises(RuntimeError, match="PARTIAL WRITE"):
            codex_pm.lite_transition(lite, "counter", "advance", "VERIFY")
    assert invoke(lite, "claim")["phase"] == "VERIFY"
    assert 'active_keys: ["counter"]' in (lite / ".agenticdoc/_index.md").read_text(encoding="utf-8")


def test_init_recovers_when_authority_committed_before_document_failure(proj, monkeypatch):
    original = codex_pm.atomic_text

    def fail_document(path, text):
        if path.name == "codex_doc.md":
            raise OSError("Injected document write failure")
        original(path, text)

    with monkeypatch.context() as patch:
        patch.setattr(codex_pm, "atomic_text", fail_document)
        with pytest.raises(RuntimeError, match="PARTIAL WRITE"):
            codex_pm.lite_transition(proj, "counter", "init")
    assert not (proj / ".agenticdoc/counter/codex_doc.md").exists()
    recovered = invoke(proj, "init")
    assert recovered["phase"] == "SPEC" and recovered["claim_id"] == "codex"
    assert invoke(proj, "status")["phase"] == "SPEC"
    assert not (proj / ".mw/codex-pm/counter.pending.json").exists()


def test_claim_repairs_partial_done_without_reactivating_task(lite, monkeypatch):
    invoke(lite, "advance", "--phase", "VERIFY")
    original = codex_pm.atomic_text

    def fail_document(path, text):
        if path.name == "codex_doc.md":
            raise OSError("Injected DONE mirror failure")
        original(path, text)

    with monkeypatch.context() as patch:
        patch.setattr(codex_pm, "atomic_text", fail_document)
        with pytest.raises(RuntimeError, match="PARTIAL WRITE"):
            codex_pm.lite_transition(lite, "counter", "done")
    result = invoke(lite, "claim")
    assert (result["phase"], result["status"], result["claim_id"]) == ("DONE", "idle", "—")
    assert invoke(lite, "status")["phase"] == "DONE"
    assert 'active_keys: []' in (lite / ".agenticdoc/_index.md").read_text(encoding="utf-8")


def test_completion_cannot_release_a_key_with_pending_worker(lite):
    invoke(lite, "check", "--ac", "AC-001", "--", sys.executable, "check.py")
    invoke(lite, "advance", "--phase", "VERIFY")
    achieved(lite)
    task = lite / ".agenticdoc/counter/workers/busy/task.md"
    task.parent.mkdir(parents=True)
    task.write_text("type: coding\n", encoding="utf-8")
    stamp = mw_common.iso_now()
    mw_common.workers_path(lite).write_text(mw_common.serialize_entry({
        "task_key": "busy", "status": "pending", "cli": "pi", "provider": "timi", "model": "",
        "task_path": str(task), "dispatched_at": stamp, "updated_at": stamp,
    }) + "\n", encoding="utf-8")
    assert "in-flight" in invoke(lite, "done", "--summary", "Cannot close yet", expected=2)["error"]
    assert invoke(lite, "status")["claim"] == "codex"


def test_completed_log_can_recover_after_later_source_changes(lite, monkeypatch):
    invoke(lite, "check", "--ac", "AC-001", "--", sys.executable, "check.py")
    invoke(lite, "advance", "--phase", "VERIFY")
    achieved(lite)
    original = codex_pm.atomic_text

    def fail_log(path, text):
        if path.name == "_project_log.md":
            raise OSError("Injected project-log refusal")
        original(path, text)

    with monkeypatch.context() as patch:
        patch.setattr(codex_pm, "atomic_text", fail_log)
        with pytest.raises(RuntimeError, match="PARTIAL WRITE"):
            codex_pm.complete(lite, lite / ".agenticdoc/counter", "Original closure")
    (lite / "counter.py").write_text("def increment(value): return value + 2\n", encoding="utf-8")
    assert invoke(lite, "done", "--summary", "Retry closure")["phase"] == "DONE"
    log = (lite / ".agenticdoc/_project_log.md").read_text(encoding="utf-8")
    assert "Original closure" in log and "Retry closure" not in log


def test_completion_preserves_other_project_log_bytes(lite):
    log = lite / ".agenticdoc/_project_log.md"
    original = b"# Existing log\r\n\r\n| Completed | Commit | Key | Summary |\r\n| old | abc | other | User text |\r\n"
    log.write_bytes(original)
    invoke(lite, "check", "--ac", "AC-001", "--", sys.executable, "check.py")
    invoke(lite, "advance", "--phase", "VERIFY")
    achieved(lite)
    invoke(lite, "done", "--summary", "Append only this task")
    assert log.read_bytes().startswith(original)
    assert log.read_bytes().endswith(b"\r\n")


def test_original_sdd_task_cannot_be_implicitly_adopted(proj):
    directory = proj / ".agenticdoc/counter"
    directory.mkdir()
    (directory / "spec.md").write_text("Existing full-SDD task")
    invoke(proj, "init", expected=2)
    assert not (proj / ".agenticdoc/_index.parallel").exists()


def test_project_template_customizations_are_used_without_overwriting(proj):
    template = proj / ".agenticdoc/templates/codex_doc.md"
    template.parent.mkdir()
    contents = (CLI.parent / "templates/codex_doc.md").read_text(encoding="utf-8") + "\nProject-specific guidance.\n"
    template.write_text(contents, encoding="utf-8")
    invoke(proj, "init")
    assert "Project-specific guidance" in (proj / ".agenticdoc/counter/codex_doc.md").read_text(encoding="utf-8")
    assert template.read_text(encoding="utf-8") == contents


def test_incompatible_custom_template_fails_before_registering_key(proj):
    template = proj / ".agenticdoc/templates/codex_doc.md"
    template.parent.mkdir()
    template.write_text("# Custom legacy template\n", encoding="utf-8")
    assert "update the project template" in invoke(proj, "init", expected=2)["error"]
    assert not (proj / ".agenticdoc/_index.parallel").exists()
    assert not (proj / ".agenticdoc/counter").exists()


@pytest.mark.parametrize("phase", ["EXECUTE", "VERIFY"])
def test_lite_dispatch_preserves_independent_review_role(lite, phase):
    if phase == "VERIFY":
        invoke(lite, "advance", "--phase", phase)
    (lite / ".agenticdoc/target.yml").write_text("active: single\n")
    card = lite / ".agenticdoc/counter/tasks/T-review.md"
    card.parent.mkdir()
    card.write_text(
        "type: review\n\n## 上下文\n.agenticdoc/goal.md and counter.py:1 define AC-001.\n"
        "## 审计目标\nVerify increment independently.\n## 要求\nReview the check and its output.\n"
        "## 未覆盖面声明\nOther modules are outside this review.\n## 交付格式\nUse report.md.\n"
        f"## 验收命令\n```json\n{json.dumps([sys.executable, 'check.py'])}\n```\n",
        encoding="utf-8",
    )
    result = invoke(lite, "dispatch", "--card", card.stem)
    task = Path(result["artifacts"]["task.md"]).read_text(encoding="utf-8")
    assert mw_common.read_task_type(task).type == "review"
    assert mw_common.read_task_header_scalar(task, "phase") == phase
    assert "Independently review" in task
    assert result["queue"] == "pending" and invoke(lite, "dispatch", "--card", card.stem)["reused"]
    if phase == "VERIFY":
        coding = card.with_name("T-coding.md")
        coding.write_text(card.read_text(encoding="utf-8").replace("type: review", "type: coding", 1), encoding="utf-8")
        refused = invoke(lite, "dispatch", "--card", coding.stem, expected=2)
        assert "Dispatch requires EXECUTE" in refused["error"]


@pytest.mark.parametrize("key", ["counter", "k" * 64])
def test_lite_dispatch_uses_existing_launcher_without_sdd_docs(lite, fakebin, start_launcher, key):
    # The real launcher uses a local fake executable; no model/API request.
    (lite / ".agenticdoc/target.yml").write_text("active: single\n")
    if key != "counter":
        invoke(lite, "init", key=key)
        fill(lite, key=key)
        invoke(lite, "advance", "--phase", "EXECUTE", key=key)
    tasks = lite / ".agenticdoc" / key / "tasks"
    tasks.mkdir()
    command = [sys.executable, "check.py"]
    (tasks / "T-01.md").write_text(
        "type: coding\n\n## 上下文\n.agenticdoc/goal.md and counter.py:1 define AC-001.\n"
        "## 要求\nImplement increment.\n## 交付格式\nUpdate counter.py and output.md.\n"
        "## 写入允许面\n- counter.py\n## 写入禁止面\n- production/\n"
        f"## 验收命令\n```json\n{json.dumps(command)}\n```\n## 改动历史\nFirst card.\n", encoding="utf-8")
    (fakebin / "fake_cli.py").write_text(
        "import os\nfrom pathlib import Path\n"
        "task=Path(os.environ['PI_WORKER_TASK'])\n"
        "assert 'phase: EXECUTE' in task.read_text(encoding='utf-8')\n"
        "task.with_name('output.md').write_text('Worker delivered the counter.')\n", encoding="utf-8")
    submitted = invoke(lite, "dispatch", "--card", "T-01", key=key)
    assert invoke(lite, "status", key=key)["tasks"][0]["task"] == submitted["task"]
    launcher = start_launcher({"TEST_TIMI_API_KEY": "fixture", "MW_USAGE_DIR": str(lite / ".usage")})
    assert _wait_for(lite, submitted["task"], {"done", "failed"}, proc=launcher, timeout=20) == "done"
    verified = invoke(lite, "verify", "--card", "T-01", "--", *command, key=key)
    assert verified["verdict"] == "passed" and verified["criteria"] == ["AC-001"]
    invoke(lite, "advance", "--phase", "VERIFY", key=key)
    achieved(lite, key=key)
    assert invoke(lite, "done", "--summary", "Worker accepted by Codex", key=key)["phase"] == "DONE"
