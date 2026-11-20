"""Exact-file decision grants never become directory, alias or write grants."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import decision
import decision_evidence_policy as policy
import decision_file_evidence as freshness
import decision_material_sources as sources
import mw_common


@pytest.fixture(autouse=True)
def no_worker(monkeypatch):
    monkeypatch.delenv("PI_WORKER_TASK", raising=False)


@pytest.fixture
def layout(tmp_path):
    root = tmp_path / "control"
    root.mkdir()
    (root / ".mw").mkdir()
    dark = tmp_path / "Dark"
    dark.mkdir()
    game = dark / "Game"
    engine = dark / "Engine"
    game.mkdir()
    engine.mkdir()
    (root / ".agenticdoc").mkdir()
    (root / ".agenticdoc" / "target.yml").write_text(
        f"mode: dual\ngame: '{game.as_posix()}'\nengine: '{engine.as_posix()}'\nengine_writable: false\n",
        encoding="utf-8",
    )
    rules = dark / "AGENTS.md"
    rules.write_text("must preserve project rules\n", encoding="utf-8", newline="")
    sibling = dark / "other.md"
    sibling.write_text("private sibling\n", encoding="utf-8")
    return root, rules, sibling


def grant(root, files):
    path = root / ".mw" / "decision-evidence.yml"
    path.write_text(json.dumps({"read_files": [str(file) for file in files]}), encoding="utf-8")
    return path


def state(file):
    return {"material": {"task_requirements": f"`{file}:1`"}, "preparation": {}}


def no_open(monkeypatch, *files):
    original = Path.open
    def checked(path, *args, **kwargs):
        if path in files:
            pytest.fail("refused source bytes must not be opened")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", checked)


def test_exact_file_only_and_workspace_write_config_unchanged(layout, monkeypatch):
    root, rules, sibling = layout
    before = mw_common.load_target_config(root)
    target_bytes = (root / ".agenticdoc" / "target.yml").read_bytes()
    with pytest.raises(sources.SourceMaterialError, match="outside"):
        sources.prepare_source_state(state(rules), root)
    grant(root, [rules])
    result = sources.prepare_source_state(state(rules), root)
    assert result["evidence_sources"][0]["text"] == rules.read_bytes().decode("utf-8")
    assert result["evidence_sources"][0]["references"] == ["material.task_requirements"]
    assert mw_common.load_target_config(root) == before
    assert before["engine_writable"] is False
    assert (root / ".agenticdoc" / "target.yml").read_bytes() == target_bytes
    no_open(monkeypatch, sibling)
    with pytest.raises(sources.SourceMaterialError, match="outside"):
        sources.prepare_source_state(state(sibling), root)
    with pytest.raises(sources.SourceMaterialError, match="outside"):
        sources.prepare_source_state(state(rules.parent / "Game" / ".." / sibling.name), root)


@pytest.mark.parametrize("relative", ["../Dark/AGENTS.md", r"..\Dark\AGENTS.md"])
def test_relative_grants_anchor_to_control_root(layout, relative):
    root, rules, _ = layout
    grant(root, [relative])
    result = sources.prepare_source_state(state(rules), root)
    assert result["evidence_sources"][0]["path"] == str(rules.resolve())


@pytest.mark.parametrize("pattern", ["**/AGENTS.md", "AGENTS.md"])
def test_target_deny_globs_win_over_exact_grant(layout, monkeypatch, pattern):
    root, rules, _ = layout
    grant(root, [rules])
    config = root / ".agenticdoc" / "target.yml"
    config.write_text(config.read_text(encoding="utf-8") + f"ignore:\n  deny_globs: ['{pattern}']\n", encoding="utf-8")
    no_open(monkeypatch, rules)
    with pytest.raises(sources.SourceMaterialError, match="deny globs"):
        sources.prepare_source_state(state(rules), root)


@pytest.mark.parametrize("header,message", [
    ("read_scope:\n  - .", "outside the Worker"),
    ("deny_globs:\n  - '**/AGENTS.md'", "Worker card deny"),
    ("deny_globs:\n  - '**/other.md'", "lifetime read budget"),
])
def test_worker_limits_are_not_widened(layout, monkeypatch, header, message):
    root, rules, _ = layout
    grant(root, [rules])
    card = root / "task.md"
    card.write_text(f"type: coding\n{header}\n\n## Task\n", encoding="utf-8")
    monkeypatch.setenv("PI_WORKER_TASK", str(card))
    no_open(monkeypatch, rules)
    with pytest.raises(sources.SourceMaterialError, match=message):
        sources.prepare_source_state(state(rules), root)


@pytest.mark.parametrize("which", ["grant-alias", "citation-alias"])
def test_aliases_do_not_extend_grants_even_without_symlink_privileges(layout, monkeypatch, which):
    root, rules, sibling = layout
    alias = rules.parent / "alias.md"
    alias.write_text("alias placeholder", encoding="utf-8")
    grant(root, [alias if which == "grant-alias" else rules])
    original = Path.resolve
    def redirected(path, *args, **kwargs):
        return (sibling if which == "grant-alias" else rules) if path == alias else original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "resolve", redirected)
    no_open(monkeypatch, alias, rules, sibling)
    with pytest.raises(sources.SourceMaterialError, match="outside"):
        sources.prepare_source_state(state(alias), root)
    if which == "grant-alias":
        with pytest.raises(sources.SourceMaterialError, match="outside"):
            sources.prepare_source_state(state(sibling), root)


def test_real_symlink_cannot_redirect_granted_filename(layout, monkeypatch):
    root, rules, sibling = layout
    alias = rules.parent / "alias.md"
    try:
        alias.symlink_to(sibling)
    except OSError:
        pytest.skip("host does not grant symlink creation; simulated alias regressions always run")
    grant(root, [alias])
    no_open(monkeypatch, sibling)
    with pytest.raises(sources.SourceMaterialError, match="outside"):
        sources.prepare_source_state(state(alias), root)


@pytest.mark.parametrize("data", [
    "", "null", "[]", "read_files: null", "read_files: AGENTS.md", "read_files: [true]",
    "read_files: ['']", "read_files: ['../Dark/*.md']", "read_files: ['../Dark']",
    "read_files: []\nread_files: ['../Dark/AGENTS.md']", "read_files: []\nwrite_files: []",
    "read_files: [", "read_files: ['../Dark/{AGENTS,other}.md']",
])
def test_malformed_or_broad_policy_fails_before_source_bytes(layout, monkeypatch, data):
    root, rules, _ = layout
    (root / ".mw" / "decision-evidence.yml").write_text(data, encoding="utf-8")
    no_open(monkeypatch, rules)
    with pytest.raises(sources.SourceMaterialError, match="decision evidence"):
        sources.prepare_source_state(state(rules), root)


def test_open_time_replacement_refuses_before_reading_new_target(layout, monkeypatch):
    root, rules, sibling = layout
    grant(root, [rules])
    original = Path.open
    class WrongTarget:
        def __enter__(self):
            self.handle = original(sibling, "rb")
            return self
        def __exit__(self, *args):
            self.handle.close()
        def fileno(self):
            return self.handle.fileno()
        def read(self, *_args):
            pytest.fail("replacement descriptor must be rejected before reading bytes")
    def replaced(path, *args, **kwargs):
        return WrongTarget() if path == rules else original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", replaced)
    with pytest.raises(sources.SourceMaterialError, match="changed while reading"):
        sources.prepare_source_state(state(rules), root)


def test_policy_caps_are_bounded(layout, monkeypatch):
    root, rules, _ = layout
    path = grant(root, [rules] * (policy.MAX_READ_FILES + 1))
    with pytest.raises(sources.SourceMaterialError, match="bounded list"):
        sources.prepare_source_state(state(rules), root)
    path.write_bytes(b"x" * (policy.MAX_POLICY_BYTES + 1))
    no_open(monkeypatch, path, rules)
    with pytest.raises(sources.SourceMaterialError, match="read limit"):
        sources.prepare_source_state(state(rules), root)


def test_material_cannot_grant_reads(layout, monkeypatch):
    root, rules, _ = layout
    payload = state(rules)
    payload["read_files"] = [str(rules)]
    payload["material"]["read_files"] = [str(rules)]
    no_open(monkeypatch, rules)
    with pytest.raises(sources.SourceMaterialError, match="outside"):
        sources.prepare_source_state(payload, root)


def test_policy_creation_revocation_and_deletion_invalidate_cached_evidence(layout):
    root, rules, _ = layout
    with pytest.raises(sources.SourceMaterialError) as blocked:
        sources.prepare_source_state(state(rules), root)
    assert not freshness.check_file_evidence(blocked.value.file_evidence).changed
    path = grant(root, [rules])
    assert freshness.check_file_evidence(blocked.value.file_evidence).changed
    ready = sources.prepare_source_state(state(rules), root)
    assert not freshness.check_file_evidence(ready.file_evidence).changed
    grant(root, [])
    assert freshness.check_file_evidence(ready.file_evidence).changed
    with pytest.raises(sources.SourceMaterialError, match="outside"):
        sources.prepare_source_state(state(rules), root)
    path.unlink()
    assert freshness.check_file_evidence(ready.file_evidence).changed


def test_missing_granted_file_dependency_refreshes_after_creation(layout):
    root, rules, _ = layout
    grant(root, [rules])
    rules.unlink()
    with pytest.raises(sources.SourceMaterialError) as blocked:
        sources.prepare_source_state(state(rules), root)
    assert blocked.value.file_evidence[-1]["path"] == str(rules)
    assert blocked.value.file_evidence[-1]["status"] == "missing"
    rules.write_text("restored rules\n", encoding="utf-8")
    assert freshness.check_file_evidence(blocked.value.file_evidence).changed
    assert sources.prepare_source_state(state(rules), root)["evidence_sources"]


def test_real_prepared_client_reads_rules_before_backend_but_refuses_sibling(layout):
    root, rules, sibling = layout
    grant(root, [rules])
    fixture = Path(__file__).parent / "decide_cases" / "dp-w-type.json"
    book = copy.deepcopy(json.loads(fixture.read_text(encoding="utf-8"))["book"])
    config = decision.DecisionConfig(enabled=True, extras={"api_key": "allowlist-fixture-key"})
    credentials = decision.credential_snapshot(config, env={}, auth_path=root / "no-auth.json")
    calls = []
    def answer(prepared, questions, _config):
        calls.append(prepared)
        choice = questions["decision_selection"]["choices"][0]
        return decision.BackendOutcome(True, None, False, {
            "decision_selection": {"value": choice, "confidence": 0.95},
        }, 1)
    backend = decision.FakeBackend(default=answer)
    client = decision.DecisionClient(config, backend=backend, credential_snapshot=credentials, project_root=root)
    book["material"]["task_requirements"] = f"Read `{rules}:1`."
    allowed = client.request_prepared("dp-w-type", book["material"], book["preparation"], actor_role="pm")
    assert allowed["available"], allowed
    assert calls[0]["evidence_sources"][0]["text"] == "must preserve project rules\n"
    book["material"]["task_requirements"] = f"Read `{sibling}:1`."
    refused = client.request_prepared("dp-w-type", book["material"], book["preparation"], actor_role="pm")
    assert not refused["available"] and refused["reason"] == "input-incomplete"
    assert "outside the configured read roots" in str(refused)
    assert len(calls) == 1


def test_maximum_citations_and_worker_policy_dependencies_fit_parser(layout, monkeypatch):
    root, rules, _ = layout
    grant(root, [rules])
    card = root / "task.md"
    card.write_text("type: coding\ntimeout: 20\n\n## Task\n", encoding="utf-8")
    monkeypatch.setenv("PI_WORKER_TASK", str(card))
    files = []
    for index in range(63):
        file = root / f"source-{index}.md"
        file.write_text("evidence\n", encoding="utf-8")
        files.append(str(file))
    files.append(str(rules))
    result = sources.prepare_source_state({"material": {"review_evidence": files}}, root)
    assert len(result.file_evidence) == 67
    assert freshness.parse_file_evidence({"file_evidence": result.file_evidence}) is not None
    assert not freshness.check_file_evidence(result.file_evidence).changed
