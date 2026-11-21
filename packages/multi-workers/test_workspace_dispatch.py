"""Explicit workspace selection through the real conductor dispatch transaction."""

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import mw_common
from autopilot import dispatch
from autopilot import timeline as timeline_mod
from workspace_dispatch import load_dispatch_target_config

WORKSPACE_ENV = (
    "MW_TARGET_GAME", "MW_TARGET_ENGINE", "MW_PARTITION_PARENT", "MW_PARTITION_ROOT",
)


@pytest.fixture(autouse=True)
def clean_workspace_env(monkeypatch):
    for name in WORKSPACE_ENV:
        monkeypatch.delenv(name, raising=False)


def configure(project, mode):
    target = project.parent / "target"
    parent = project.parent / "parent"
    target.mkdir(exist_ok=True)
    parent.mkdir(exist_ok=True)
    config = {"active": mode}
    if mode == "dual":
        config["dual"] = {"game": str(target)}
    elif mode == "partition":
        config["partition"] = {"parent": str(parent), "partition": str(target)}
    path = mw_common.target_yml_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config), encoding="utf-8", newline="\n")
    return path


def send(project, stem="new", timeline=None):
    return dispatch.dispatch(
        project, "work", stem, "repair", "Do the work.",
        loop="workspace-gate", attempt=1, timeline=timeline,
    )


def snapshot(root):
    return {str(path.relative_to(root)): path.read_bytes()
            for path in root.rglob("*") if path.is_file()}


@pytest.mark.parametrize("expected_mode", ["dual", "partition"])
@pytest.mark.parametrize("existing_task", [False, True])
def test_first_time_missing_config_refuses_without_task_or_queue_writes(
    tmp_path, expected_mode, existing_task,
):
    project = tmp_path / "control"
    project.mkdir()
    # A prose convention cannot establish runtime configuration.
    (project / "AGENTS.md").write_text(f"Workspace mode: {expected_mode}\n", encoding="utf-8")
    queue = mw_common.workers_path(project)
    queue.parent.mkdir()
    queue.write_bytes(b"# Existing queue bytes\r\n")
    task_dir = project / ".agenticdoc/work/workers/ap-work-new"
    if existing_task:
        task_dir.mkdir(parents=True)
        (task_dir / "task.md").write_bytes(b"type: coding\r\nKeep this task.\r\n")
        (task_dir / "output.md").write_bytes(b"Keep existing output.\n")
    before = snapshot(project)
    result = send(project)
    assert not result.ok and result.reason == "target-config-unusable"
    assert "target-config-required" in result.detail
    assert result.task_md is None and not result.row_verified
    assert snapshot(project) == before
    assert task_dir.exists() == existing_task
    print("[VERIFY] VC-001: missing-config=blocked side-effects=0")


@pytest.mark.parametrize("body", [None, "", " \n  ", "{}\n", "contract: {}\n"])
def test_default_config_refusal_is_actionable_and_precedes_write_face(tmp_path, body):
    project = tmp_path / "control"
    project.mkdir()
    path = mw_common.target_yml_path(project)
    path.parent.mkdir()
    if body is not None:
        path.write_text(body, encoding="utf-8")
    card = project / ".agenticdoc/work/tasks/new.md"
    card.parent.mkdir(parents=True)
    card.write_text("## 写入允许面\n- ../outside.cpp\n", encoding="utf-8")
    before = snapshot(project)
    timeline = timeline_mod.Timeline(project / ".agenticdoc/_autopilot/timeline.jsonl")
    result = send(project, timeline=timeline)
    assert not result.ok and result.reason == "target-config-unusable"
    events = timeline_mod.query_events(timeline.path).events
    assert [event["ev"] for event in events] == ["target-config-rejected"]
    detail = events[0]["detail"]
    for expected in (
        "target-config-required", str(project.resolve()), str(path.resolve()),
        "mode=single", "source=default", "active: single", "active: dual",
        "active: partition", "MW_TARGET_GAME", "MW_PARTITION_PARENT/MW_PARTITION_ROOT",
    ):
        assert expected in detail
        assert expected in result.detail
    after = snapshot(project)
    after.pop(str(timeline.path.relative_to(project)))
    assert after == before
    assert not (project / ".agenticdoc/work/workers").exists()
    assert not mw_common.workers_path(project).exists()
    print("[VERIFY] VC-002: implicit-default=blocked")


@pytest.mark.parametrize("mode", ["dual", "partition"])
def test_deleted_config_refuses_and_retains_existing_dispatch(tmp_path, mode):
    project = tmp_path / "control"
    project.mkdir()
    path = configure(project, mode)
    first = send(project, "old")
    assert first.ok and first.row_verified
    path.unlink()
    before = snapshot(project)
    result = send(project)
    assert not result.ok and result.reason == "target-config-unusable"
    assert result.task_md is None and snapshot(project) == before
    assert not (project / ".agenticdoc/work/workers/ap-work-new").exists()
    print("[VERIFY] VC-001: deleted-config=blocked side-effects=0")


@pytest.mark.parametrize("mode", ["single", "dual", "partition"])
def test_explicit_modes_dispatch_and_preserve_workspace_roots(tmp_path, mode):
    project = tmp_path / "control"
    project.mkdir()
    configure(project, mode)
    config = load_dispatch_target_config(project)
    assert config["mode"] == mode and config["source"] == "target-yml"
    result = send(project)
    assert result.ok and result.row_verified
    assert result.task_md is not None and result.task_md.is_file()
    rows = mw_common.parse_workers_file(mw_common.workers_path(project))
    assert [row["task_key"] for row in rows] == ["ap-work-new"]
    expected_cwd = project if mode == "single" else tmp_path / "target"
    assert mw_common.workspace_root(config) == str(expected_cwd.resolve())
    if mode == "partition":
        text = result.task_md.read_text(encoding="utf-8")
        assert "[mw] mode: partition" in text
        assert f"Partition root (worker cwd): {expected_cwd.resolve()}" in text
    print(f"[VERIFY] VC-003: explicit-mode={mode} pass")


@pytest.mark.parametrize("mode", ["dual", "partition"])
def test_complete_env_activation_dispatches_without_file(tmp_path, monkeypatch, mode):
    project = tmp_path / "control"
    project.mkdir()
    target = tmp_path / "target"
    target.mkdir()
    if mode == "dual":
        monkeypatch.setenv("MW_TARGET_GAME", str(target))
    else:
        parent = tmp_path / "parent"
        parent.mkdir()
        monkeypatch.setenv("MW_PARTITION_PARENT", str(parent))
        monkeypatch.setenv("MW_PARTITION_ROOT", str(target))
    config = load_dispatch_target_config(project)
    assert config["mode"] == mode and config["source"] == "env"
    assert not mw_common.target_yml_path(project).exists()
    result = send(project)
    assert result.ok and result.row_verified
    print(f"[VERIFY] VC-003: complete-env={mode} pass")


@pytest.mark.parametrize("body", [
    "# comment only\n", "null\n", "active: dual\n", "mode: dual\n",
    "active: partition\npartition: {}\n", "active: [broken\n",
])
def test_malformed_or_incomplete_config_remains_refused(tmp_path, body):
    project = tmp_path / "control"
    project.mkdir()
    path = mw_common.target_yml_path(project)
    path.parent.mkdir()
    path.write_text(body, encoding="utf-8")
    before = snapshot(project)
    result = send(project)
    assert not result.ok and result.reason == "target-config-unusable"
    assert snapshot(project) == before


@pytest.mark.parametrize("name", WORKSPACE_ENV)
def test_incomplete_or_blank_env_never_authorizes_default(tmp_path, monkeypatch, name):
    # MW_TARGET_GAME alone is the complete dual activation, so use whitespace
    # for that member; every other singleton is incomplete by construction.
    monkeypatch.setenv(name, " " if name == "MW_TARGET_GAME" else str(tmp_path / "target"))
    result = send(tmp_path)
    assert not result.ok and result.reason == "target-config-unusable"
    assert not mw_common.workers_path(tmp_path).exists()


@pytest.mark.parametrize("mode", ["dual", "partition"])
def test_config_removed_while_waiting_for_queue_lock_refuses(tmp_path, monkeypatch, mode):
    project = tmp_path / "control"
    project.mkdir()
    path = configure(project, mode)
    acquire = mw_common.acquire_lock

    def acquire_then_remove(lock):
        acquire(lock)
        path.unlink()

    monkeypatch.setattr(mw_common, "acquire_lock", acquire_then_remove)
    result = send(project)
    assert not result.ok and result.reason == "target-config-unusable"
    assert not mw_common.lock_path(project).exists()
    assert not mw_common.workers_path(project).exists()
    assert not (project / ".agenticdoc/work/workers").exists()


@pytest.mark.parametrize("mode", ["dual", "partition"])
def test_config_changed_while_waiting_for_queue_lock_refuses(tmp_path, monkeypatch, mode):
    project = tmp_path / "control"
    project.mkdir()
    path = configure(project, mode)
    acquire = mw_common.acquire_lock

    def acquire_then_change(lock):
        acquire(lock)
        path.write_text("active: single\n", encoding="utf-8")

    monkeypatch.setattr(mw_common, "acquire_lock", acquire_then_change)
    result = send(project)
    assert not result.ok and result.reason == "target-config-unusable"
    assert "target-config-changed" in result.detail
    assert str(project.resolve()) in result.detail and str(path.resolve()) in result.detail
    assert not mw_common.lock_path(project).exists()
    assert not mw_common.workers_path(project).exists()
    assert not (project / ".agenticdoc/work/workers").exists()


def test_unconfigured_query_keeps_default_without_writes(tmp_path):
    before = snapshot(tmp_path)
    config = mw_common.load_target_config(tmp_path, env={})
    assert config["mode"] == "single" and config["source"] == "default"
    assert config["game_root"] == config["control_root"] == str(tmp_path.resolve())
    assert snapshot(tmp_path) == before
    print("[VERIFY] VC-004: query-default=preserved")
