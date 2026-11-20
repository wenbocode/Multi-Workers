"""Worker-bound evidence reads cannot bypass task-card scope or lifetime caps."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

import decision
import decision_material_sources as sources
import decision_source_scope as scope


@pytest.fixture(autouse=True)
def isolated_worker_binding(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PI_WORKER_TASK", raising=False)


def bind_card(root: Path, monkeypatch: pytest.MonkeyPatch, header: str, body: str = "") -> Path:
    card = root / "task.md"
    card.write_text(f"type: coding\n{header}\n\n{body}", encoding="utf-8", newline="")
    monkeypatch.setenv("PI_WORKER_TASK", str(card))
    return card


def state(reference: object) -> dict:
    return {"material": {"review_evidence": reference}, "preparation": {"basis_catalog": []}}


def refuse_source_opens(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    original = Path.open
    opened: list[Path] = []
    def observed(path: Path, *args: object, **kwargs: object):
        if path.name.endswith(".md") and path.name != "task.md":
            opened.append(path)
            pytest.fail("refused source must not be opened")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", observed)
    return opened


def test_unscoped_worker_reads_allowed_evidence_and_records_card_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    card = bind_card(tmp_path, monkeypatch, "timeout: 20")
    (tmp_path / "report.md").write_bytes(b"actual proof\n")
    result = sources.prepare_source_state(state("report.md"), tmp_path)
    assert result["evidence_sources"][0]["text"] == "actual proof\n"
    dependency = next(item for item in result.file_evidence if item["path"] == str(card))
    assert dependency["sha256"] == hashlib.sha256(card.read_bytes()).hexdigest()
    assert "file_evidence" not in json.dumps(result)


@pytest.mark.parametrize(("header", "reference", "message"), [
    ("read_scope:\n  - allowed", "outside.md", "outside the Worker card read_scope"),
    ("read_scope:", "outside.md", "outside the Worker card read_scope"),
    ("read_scope:\n  - .\ndeny_globs:\n  - '**/outside.md'", "outside.md", "deny globs"),
    ("deny_globs:\n  - 'private/**'", "private/outside.md", "deny globs"),
    ("read_scope:\n  - .", "outside.md", "Worker lifetime read budget is unavailable"),
    ("deny_globs:\n  - '**/other.md'", "outside.md", "Worker lifetime read budget is unavailable"),
    ("read_scope:\n  - .\nl2_read_byte_cap: 2", "outside.md", "read byte cap"),
    ("read_scope:\n  - .\nl2_read_file_cap: 0.5", "outside.md", "read file cap"),
])
def test_guarded_source_refuses_before_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                           header: str, reference: str, message: str) -> None:
    card = bind_card(tmp_path, monkeypatch, header)
    source = tmp_path / reference
    source.parent.mkdir(exist_ok=True)
    source.write_text("private proof\n", encoding="utf-8")
    opened = refuse_source_opens(monkeypatch)
    with pytest.raises(sources.SourceMaterialError, match=message) as failure:
        sources.prepare_source_state(state(reference), tmp_path)
    assert opened == []
    assert any(item["path"] == str(card) and item["sha256"] for item in failure.value.file_evidence)
    assert "private proof" not in str(failure.value)


def test_partition_parent_union_preserves_empty_scope_and_nonpartition_boundary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "partition"
    root.mkdir()
    parent = tmp_path / "parent"
    parent.mkdir()
    source = parent / "report.md"
    source.write_text("proof", encoding="utf-8")
    profile = f"[mw] mode: partition\nParent root (extended): {parent}\n"
    bind_card(root, monkeypatch, "read_scope:\n  - local", profile)
    config = scope.load_worker_source_scope(root)
    assert config is not None
    config.check_path(source)
    assert config.scope == ((root / "local").resolve(), parent.resolve())
    bind_card(root, monkeypatch, "read_scope:", profile)
    with pytest.raises(scope.WorkerSourceScopeError, match="outside"):
        scope.load_worker_source_scope(root).check_path(source)
    bind_card(root, monkeypatch, "read_scope:\n  - local", f"Parent root: {parent}")
    with pytest.raises(scope.WorkerSourceScopeError, match="outside"):
        scope.load_worker_source_scope(root).check_path(source)


def test_header_scope_cannot_be_widened_by_body_or_model_material(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bind_card(tmp_path, monkeypatch, "read_scope:\n  - allowed", "read_scope:\n  - .\n")
    (tmp_path / "report.md").write_text("proof", encoding="utf-8")
    payload = state("report.md")
    payload["read_scope"] = [str(tmp_path)]
    payload["material"]["read_scope"] = [str(tmp_path)]
    refuse_source_opens(monkeypatch)
    with pytest.raises(sources.SourceMaterialError, match="outside the Worker"):
        sources.prepare_source_state(payload, tmp_path)


def test_zero_caps_use_ts_defaults_and_still_refuse_lifetime_budget(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bind_card(tmp_path, monkeypatch, "read_scope:\n  - .\nl2_read_file_cap: 0\nl2_read_byte_cap: 0")
    config = scope.load_worker_source_scope(tmp_path)
    assert config.file_cap == 8 and config.byte_cap == 65536
    with pytest.raises(scope.WorkerSourceScopeError, match="lifetime"):
        config.charge(tmp_path / "report.md", 1)


@pytest.mark.parametrize("header", ["read_scope: []", "read_scope:\n  - .\nread_scope:\n  - narrow",
                                     "deny_globs:\n  - '**/{private,secret}/**'"])
def test_ambiguous_or_unsupported_scope_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, header: str) -> None:
    bind_card(tmp_path, monkeypatch, header)
    (tmp_path / "report.md").write_text("proof", encoding="utf-8")
    refuse_source_opens(monkeypatch)
    with pytest.raises(sources.SourceMaterialError, match="source read refused"):
        sources.prepare_source_state(state("report.md"), tmp_path)


def test_basis_text_explicit_citations_hydrate_without_reading_ids(tmp_path: Path) -> None:
    (tmp_path / "report.md").write_text("actual proof\n", encoding="utf-8")
    payload = state("ordinary facts")
    payload["preparation"]["basis_catalog"] = [
        {"id": "do-not-open.md", "text": "Read `report.md:1` and [proof](report.md:1)."},
        {"id": "reasonB", "text": "report.md"},
        {"id": "reasonC", "text": "report.md:1"},
    ]
    result = sources.prepare_source_state(payload, tmp_path)
    assert len(result["evidence_sources"]) == 1
    assert result["evidence_sources"][0]["references"] == [
        "preparation.basis_catalog[0].text", "preparation.basis_catalog[2].text",
    ]


def test_guarded_prepared_request_refuses_before_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bind_card(tmp_path, monkeypatch, "read_scope:\n  - .")
    (tmp_path / "report.md").write_text("proof\n", encoding="utf-8")
    fixture = Path(__file__).parent / "decide_cases" / "dp-w-check-task.json"
    book = copy.deepcopy(json.loads(fixture.read_text(encoding="utf-8"))["book"])
    book["material"]["completed"] = "report.md:1"
    cfg = decision.DecisionConfig(enabled=True, extras={"api_key": "scope-fixture-key"})
    snapshot = decision.credential_snapshot(cfg, env={}, auth_path=tmp_path / "no-auth.json")
    backend = decision.FakeBackend([])
    client = decision.DecisionClient(cfg, backend=backend, credential_snapshot=snapshot, project_root=tmp_path)
    refuse_source_opens(monkeypatch)
    result = client.request_prepared("dp-w-check-task", book["material"], book["preparation"], actor_role="worker")
    assert result["reason"] == "input-incomplete"
    assert "lifetime read budget" in str(result), json.dumps(result, ensure_ascii=False)
    assert backend.calls == []


def test_symlink_cannot_escape_card_scope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    other = tmp_path / "outside.md"
    other.write_text("private", encoding="utf-8")
    alias = allowed / "alias.md"
    try:
        alias.symlink_to(other)
    except OSError:
        pytest.skip("symlinks require host privileges")
    bind_card(tmp_path, monkeypatch, "read_scope:\n  - allowed")
    refuse_source_opens(monkeypatch)
    with pytest.raises(sources.SourceMaterialError, match="outside the Worker"):
        sources.prepare_source_state(state("allowed/alias.md"), tmp_path)
