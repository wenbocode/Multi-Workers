"""Restricted prepare launcher admission at the existing fixed-allocation boundary."""

import datetime
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import decision_prepare
import mw_common


def _fixture(root, *, deadline, model="deepseek/test-model"):
    key = root / ".agenticdoc" / "export"
    card_dir = key / "tasks"
    task_dir = key / "workers" / "prepare"
    grants = root / ".agenticdoc/_runtime/fixed-child-budgets/export"
    for folder in (card_dir, task_dir, grants):
        folder.mkdir(parents=True)
    card = card_dir / "prepare.md"
    card.write_text(
        f"type: decide_prepare\nprepare_profile: bounded-v1\nmodel: {model}\n"
        "\n- `parent_matter_ref`: `export/original`\n",
        encoding="utf-8",
    )
    pin = mw_common.sha256_eol_normalized(card)
    task = task_dir / "task.md"
    envelope = (
        "type: decide_prepare\nprepare_profile: bounded-v1\n"
        f"prepare_model: {model}\ncard_path: tasks/prepare.md\ncard_sha256: {pin}\n"
        f"fixed_child_steps: 12\nfixed_child_deadline: {deadline}\n"
    )
    task.write_text(envelope, encoding="utf-8")
    grant = grants / "prepare.json"
    grant.write_text(json.dumps({
        "card": "tasks/prepare.md", "pin": pin, "task": "prepare", "steps": 12, "deadline": deadline,
        "prepare": {"parent_matter_ref": "export/original", "model": model},
    }), encoding="utf-8")
    return task, envelope, card, grant


def _future():
    return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=1)).isoformat()


def test_prepare_spawn_uses_pinned_model_and_inherited_grant(tmp_path):
    task, envelope, _card, _grant = _fixture(tmp_path, deadline=_future())
    assert decision_prepare.spawn_model(tmp_path, task, envelope) == "deepseek/test-model"


@pytest.mark.parametrize("change", ["model", "budget", "already-started", "card"])
def test_prepare_spawn_rejects_mutations_before_launch(tmp_path, change):
    task, envelope, card, grant = _fixture(tmp_path, deadline=_future())
    if change == "model":
        envelope = envelope.replace("deepseek/test-model", "timi/test-model")
    elif change == "budget":
        envelope = envelope.replace("fixed_child_steps: 12", "fixed_child_steps: 40")
    elif change == "already-started":
        grant.with_suffix(".json.started").write_text("10", encoding="utf-8")
    else:
        card.write_text(card.read_text(encoding="utf-8") + "Card drift\n", encoding="utf-8")
    with pytest.raises(decision_prepare.Refusal):
        decision_prepare.spawn_model(tmp_path, task, envelope)


def test_prepare_spawn_rejects_expired_original_deadline(tmp_path):
    task, envelope, _card, _grant = _fixture(tmp_path, deadline="2000-01-01T00:00:00Z")
    with pytest.raises(decision_prepare.Refusal, match="expired"):
        decision_prepare.spawn_model(tmp_path, task, envelope)


@pytest.mark.parametrize("used_calls,used_bytes,charge", [(0, 0, 11), (1, 1, 1)])
def test_delegated_read_cannot_increase_original_worker_allowance(tmp_path, used_calls, used_bytes, charge):
    doc = tmp_path / ".agenticdoc"
    parent = doc / "export/workers/original/task.md"
    parent.parent.mkdir(parents=True)
    text = b"type: coding\nread_scope:\n  - evidence.txt\nl2_read_file_cap: 1\nl2_read_byte_cap: 10\n"
    parent.write_bytes(text)
    run_id = "original@2026-11-22T00:00:00Z"
    scope = hashlib.sha256(text).hexdigest()
    allowance = doc / "_runtime/read-allowance/export/original.json"
    allowance.parent.mkdir(parents=True)
    receipt = {"run_id": run_id, "scope_sha256": scope, "calls": used_calls, "bytes": used_bytes}
    allowance.write_text(json.dumps(receipt), encoding="utf-8")
    binding = {"key": "export", "dp": "dp-w-check-task", "parent_run": run_id, "parent_card_sha256": scope}
    with pytest.raises(decision_prepare.Refusal, match="cumulative read allowance"):
        decision_prepare._charge_original_read(tmp_path, binding, charge)
    assert json.loads(allowance.read_text(encoding="utf-8")) == receipt
