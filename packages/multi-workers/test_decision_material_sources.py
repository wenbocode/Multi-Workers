"""Offline evidence hydration and protected excerpt budget regressions."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import decision
import decision_material_sources as sources
import mw_common


def state(value: object, field: str = "review_evidence") -> dict:
    return {"material": {field: value}, "preparation": {"basis_catalog": []}, "context": {"note": "retained"}}


def test_full_source_snapshot_and_deep_copy(tmp_path: Path) -> None:
    raw = b"alpha\nbeta\n"
    (tmp_path / "report.md").write_bytes(raw)
    original = state(["report.md"])
    result = sources.prepare_source_state(original, tmp_path)
    actual = result["evidence_sources"][0]
    assert actual["text"] == raw.decode()
    assert actual["sha256"] == hashlib.sha256(raw).hexdigest()
    assert actual["source_bytes"] == len(raw)
    assert actual["line_range"] == [1, 2]
    assert actual["included_lines"] == [[1, 2]]
    assert actual["omitted_lines"] == []
    assert actual["representation"] == "full"
    assert actual["references"] == ["material.review_evidence[0]"]
    assert "evidence_sources" not in original
    result["context"]["note"] = "changed"
    assert original["context"]["note"] == "retained"


def test_ranges_deduplicate_and_keep_field_provenance(tmp_path: Path) -> None:
    (tmp_path / "source.py").write_text("one\ntwo\nthree\nfour\n", encoding="utf-8", newline="")
    result = sources.prepare_source_state(state(["source.py:2-3", "See `source.py:2-3`.", "[evidence](source.py:2-3)"]), tmp_path)
    assert len(result["evidence_sources"]) == 1
    actual = result["evidence_sources"][0]
    assert actual["text"] == "two\nthree\n"
    assert actual["line_range"] == [2, 3]
    assert actual["representation"] == "excerpt"
    assert len(actual["references"]) == 3


def test_nested_material_and_unquoted_line_citation(tmp_path: Path) -> None:
    (tmp_path / "proof.txt").write_text("observed result\n", encoding="utf-8", newline="")
    result = sources.prepare_source_state(state({"current_state": "actual proof.txt:1 supports it"}, "background"), tmp_path)
    assert result["evidence_sources"][0]["text"] == "observed result\n"


@pytest.mark.parametrize("pattern", ["{private,secret}/**", "@(private|secret)/**", "!public/**"])
def test_unsupported_target_firewall_pattern_refuses_before_source_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pattern: str,
) -> None:
    original = mw_common.load_target_config
    config = original(tmp_path)
    config["ignore"] = {"deny_globs": [pattern]}
    monkeypatch.setattr(mw_common, "load_target_config", lambda _root: config)
    (tmp_path / "proof.md").write_bytes(b"must not be read\n")
    source_open = Path.open
    def observed(path: Path, *args: object, **kwargs: object):
        if path.name == "proof.md":
            pytest.fail("unsupported firewall must refuse before reading source bytes")
        return source_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", observed)
    with pytest.raises(sources.SourceMaterialError, match="unsupported pattern"):
        sources.prepare_source_state(state("proof.md"), tmp_path)


@pytest.mark.parametrize("value", ["missing.md", "missing.md:1", "[proof](missing.md:2)"])
def test_missing_source_refuses_without_echoing_values(tmp_path: Path, value: str) -> None:
    with pytest.raises(sources.SourceMaterialError) as error:
        sources.prepare_source_state(state(value), tmp_path)
    assert error.value.issues[0][0] == "material.review_evidence"
    assert "missing or cannot be resolved" in str(error.value)
    assert "missing.md" not in str(error.value)


@pytest.mark.parametrize("reference", ["source.md:0", "source.md:-1", "source.md:1--2", "source.md:2-1", "source.md:1-9"])
def test_invalid_ranges(tmp_path: Path, reference: str) -> None:
    (tmp_path / "source.md").write_text("one\ntwo", encoding="utf-8")
    with pytest.raises(sources.SourceMaterialError, match="line range"):
        sources.prepare_source_state(state(reference), tmp_path)


def test_source_content_is_not_recursively_followed(tmp_path: Path) -> None:
    (tmp_path / "report.md").write_text("`secret.json:1`\n", encoding="utf-8")
    actual = sources.prepare_source_state(state("report.md"), tmp_path)
    assert len(actual["evidence_sources"]) == 1
    assert "secret.json" in actual["evidence_sources"][0]["text"]


def test_paths_with_spaces_and_backslashes(tmp_path: Path) -> None:
    directory = tmp_path / "with space"
    directory.mkdir()
    source = directory / "report.md"
    source.write_text("proof\n", encoding="utf-8", newline="")
    for ref in (f"`with space/report.md:1`", f"{source}:1", r"with space\report.md:1"):
        if ref.startswith("with space"):
            ref = f"`{ref}`"
        result = sources.prepare_source_state(state(ref), tmp_path)
        assert result["evidence_sources"][0]["text"] == "proof\n"


def test_urls_commands_and_future_outputs_do_not_trigger_reads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse_scope(*_args: object, **_kwargs: object) -> dict:
        pytest.fail("no reference should resolve workspace config")
    monkeypatch.setattr(mw_common, "load_target_config", refuse_scope)
    original = {"material": {
        "review_evidence": ["https://host/report.md:1", "python -B check.py", "cat report.md", "version 1.2"],
        "task_deliverables": "new-report.md",
        "handling_options": [{"description": "new-source.py", "consequence": "new-report.md"}],
    }, "preparation": {}}
    assert sources.prepare_source_state(original, tmp_path) == original


def test_explicit_citations_in_future_fields_still_require_evidence(tmp_path: Path) -> None:
    with pytest.raises(sources.SourceMaterialError):
        sources.prepare_source_state(state("not-created.md:1", "task_deliverables"), tmp_path)


def test_no_project_root_refuses_only_file_references() -> None:
    assert sources.prepare_source_state(state("a review finding"), None) == state("a review finding")
    with pytest.raises(sources.SourceMaterialError, match="project root"):
        sources.prepare_source_state(state("report.md"), None)


def test_caller_sources_are_rebuilt_not_trusted(tmp_path: Path) -> None:
    (tmp_path / "report.md").write_text("real\n", encoding="utf-8", newline="")
    original = state("report.md")
    original["evidence_sources"] = [{"text": "fabricated"}]
    result = sources.prepare_source_state(original, tmp_path)
    assert result["evidence_sources"][0]["text"] == "real\n"


def test_outside_root_and_symlink_escape(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    other = tmp_path / "other.md"
    other.write_text("outside\n", encoding="utf-8")
    with pytest.raises(sources.SourceMaterialError, match="outside"):
        sources.prepare_source_state(state("../other.md"), project)


def test_symlink_escape(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    other = tmp_path / "other.md"
    other.write_bytes(b"outside\n")
    link = project / "link.md"
    try:
        link.symlink_to(other)
    except OSError:
        pytest.skip("symlinks require privileges on this host")
    with pytest.raises(sources.SourceMaterialError, match="outside"):
        sources.prepare_source_state(state("link.md"), project)


def test_named_target_roots_and_deny_globs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "project"
    target = tmp_path / "target"
    project.mkdir()
    target.mkdir()
    (target / "allowed.md").write_text("allowed\n", encoding="utf-8")
    (target / "secret.md").write_text("secret\n", encoding="utf-8")
    monkeypatch.setattr(mw_common, "load_target_config", lambda _root: {
        "roots": {"target": str(target)}, "ignore": {"deny_globs": ["**/secret.md"]},
    })
    assert sources.prepare_source_state(state(str(target / "allowed.md")), project)["evidence_sources"]
    with pytest.raises(sources.SourceMaterialError, match="deny globs"):
        sources.prepare_source_state(state(str(target / "secret.md")), project)


@pytest.mark.parametrize("raw", [b"", b" \n", b"x\x00y", b"\xff\xfe", b"abc\x01"])
def test_empty_non_utf8_and_binary_refused(tmp_path: Path, raw: bytes) -> None:
    (tmp_path / "bad.md").write_bytes(raw)
    with pytest.raises(sources.SourceMaterialError):
        sources.prepare_source_state(state("bad.md"), tmp_path)


def test_utf8_bom_is_accepted_and_hashes_raw_bytes(tmp_path: Path) -> None:
    raw = b"\xef\xbb\xbfproof\n"
    (tmp_path / "bom.md").write_bytes(raw)
    actual = sources.prepare_source_state(state("bom.md"), tmp_path)["evidence_sources"][0]
    assert actual["text"] == "proof\n"
    assert actual["sha256"] == hashlib.sha256(raw).hexdigest()


def test_finite_read_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "large.md").write_text("long text", encoding="utf-8")
    monkeypatch.setattr(sources, "MAX_SOURCE_BYTES", 4)
    with pytest.raises(sources.SourceMaterialError, match="read limit"):
        sources.prepare_source_state(state("large.md"), tmp_path)


def test_compression_retains_middle_failure_and_explicit_omissions(tmp_path: Path) -> None:
    lines = [f"observation {index}: ordinary detail {'x' * 80}\n" for index in range(300)]
    lines[151] = "P1: failed validation; runtime remains UNVERIFIED.\n"
    lines[202] = "约束：不得把未验证项声明为通过。\n"
    (tmp_path / "large.md").write_text("".join(lines), encoding="utf-8")
    questions = {"selection": {"type": "choice", "instructions": "pick", "choices": ["fixA"]}}
    result = sources.prepare_source_state(state("large.md"), tmp_path, questions=questions,
                                          max_state_plus_question_tokens=1400, max_total_tokens=1400)
    actual = result["evidence_sources"][0]
    assert actual["representation"] == "excerpt"
    assert "151: observation 150" in actual["text"]
    assert "152: P1: failed validation" in actual["text"]
    assert "runtime remains UNVERIFIED" in actual["text"]
    assert "约束：不得把未验证项" in actual["text"]
    assert actual["omitted_lines"]
    assert "No semantic completeness" in actual["compression"]
    state_tokens = decision._estimate_tokens(decision._encode_state(result).decode())
    assert state_tokens + decision._estimate_tokens(json.dumps(questions["selection"], ensure_ascii=False)) <= 1400


def test_every_source_has_content_after_compression(tmp_path: Path) -> None:
    for name in ("one.md", "two.md"):
        (tmp_path / name).write_text("".join(f"row {index} {'x' * 90}\n" for index in range(150)), encoding="utf-8")
    result = sources.prepare_source_state(state(["one.md", "two.md"]), tmp_path,
                                          max_state_plus_question_tokens=1200, max_total_tokens=1200)
    assert len(result["evidence_sources"]) == 2
    assert all(source["text"] and source["included_lines"] for source in result["evidence_sources"])


def test_protected_minimum_or_core_too_large_refuses(tmp_path: Path) -> None:
    (tmp_path / "constraints.md").write_text("".join(f"must preserve constraint {index} {'x' * 60}\n" for index in range(100)), encoding="utf-8")
    with pytest.raises(sources.SourceMaterialError, match="compression-required"):
        sources.prepare_source_state(state("constraints.md"), tmp_path,
                                     max_state_plus_question_tokens=500, max_total_tokens=500)


def test_byte_ceiling_counts_metadata_and_questions_count_for_tokens(tmp_path: Path) -> None:
    (tmp_path / "report.md").write_text("proof\n", encoding="utf-8")
    with pytest.raises(sources.SourceMaterialError, match="compression-required"):
        sources.prepare_source_state(state("report.md"), tmp_path, max_state_bytes=20)
    with pytest.raises(sources.SourceMaterialError, match="compression-required"):
        sources.prepare_source_state(state("report.md"), tmp_path,
                                     max_total_tokens=100, max_state_plus_question_tokens=100,
                                     questions={"q": {"instructions": "x" * 1000}})


def test_book_evidence_is_hydrated_without_sending_local_notes(tmp_path: Path) -> None:
    (tmp_path / "report.md").write_bytes(b"actual proof\n")
    result = sources.prepare_source_state(state("review facts"), tmp_path,
                                          source_references={"review_findings": "report.md:1", "runtime": "cmd:pytest"})
    assert result["evidence_sources"][0]["text"] == "actual proof\n"
    assert result["evidence_sources"][0]["references"] == ["notes.evidence.review_findings"]
    assert "notes" not in result


def test_target_config_failure_is_a_field_addressable_refusal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def bad_config(_root: object) -> dict:
        raise mw_common.TargetConfigError("invalid-config", "do not expose submitted config")
    monkeypatch.setattr(mw_common, "load_target_config", bad_config)
    with pytest.raises(sources.SourceMaterialError, match="read scope") as error:
        sources.prepare_source_state(state("report.md"), tmp_path)
    assert "do not expose" not in str(error.value)


def test_multiple_ranges_use_one_file_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "report.md"
    source.write_bytes(b"first\nsecond\n")
    original_read = sources._read_source
    reads = 0
    def changing_read(*args: object, **kwargs: object) -> tuple[dict[str, object], list[str]]:
        nonlocal reads
        reads += 1
        if reads == 2:
            source.write_bytes(b"changed\nsecond\n")
        return original_read(*args, **kwargs)
    monkeypatch.setattr(sources, "_read_source", changing_read)
    result = sources.prepare_source_state(state(["report.md:1", "report.md:2"]), tmp_path)
    assert [item["text"] for item in result["evidence_sources"]] == ["first\n", "second\n"]
    assert len({item["sha256"] for item in result["evidence_sources"]}) == 1


def test_duplicate_citations_open_file_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "report.md").write_bytes(b"one\ntwo\n")
    original_open = Path.open
    opens = 0
    def counting_open(path: Path, *args: object, **kwargs: object):
        nonlocal opens
        if path.name == "report.md":
            opens += 1
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", counting_open)
    result = sources.prepare_source_state(state(["report.md:1", "report.md:1", "report.md:2"]), tmp_path)
    assert opens == 1
    assert len(result["evidence_sources"]) == 2


def test_concurrent_change_during_read_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "report.md"
    path.write_bytes(b"original\n")
    original_open = Path.open
    class ChangingRead:
        def __init__(self, handle) -> None:
            self.handle = handle
        def __enter__(self):
            self.handle.__enter__()
            return self
        def __exit__(self, *args):
            return self.handle.__exit__(*args)
        def read(self, size: int) -> bytes:
            raw = self.handle.read(size)
            with original_open(path, "wb") as writer:
                writer.write(b"different contents\n")
            return raw
        def fileno(self) -> int:
            return self.handle.fileno()
    def changing_open(candidate: Path, *args: object, **kwargs: object):
        handle = original_open(candidate, *args, **kwargs)
        return ChangingRead(handle) if candidate == path else handle
    monkeypatch.setattr(Path, "open", changing_open)
    with pytest.raises(sources.SourceMaterialError, match="changed while reading"):
        sources.prepare_source_state(state("report.md"), tmp_path)


def test_unreadable_source_refuses_without_contents(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "report.md").write_bytes(b"secret contents\n")
    original_open = Path.open
    def deny_open(path: Path, *args: object, **kwargs: object):
        if path.name == "report.md":
            raise PermissionError("do not expose secret contents")
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", deny_open)
    with pytest.raises(sources.SourceMaterialError, match="unreadable") as error:
        sources.prepare_source_state(state("report.md"), tmp_path)
    assert "secret contents" not in str(error.value)


def test_replay_dependencies_are_local_only_and_include_scope_config(tmp_path: Path) -> None:
    (tmp_path / "report.md").write_bytes(b"actual\n")
    prepared = sources.prepare_source_state(state("report.md"), tmp_path)
    assert len(prepared.file_evidence) == 3
    config, policy, source = prepared.file_evidence
    assert policy == {"path": str(tmp_path / ".mw" / "decision-evidence.yml"), "canonical_path": None,
                      "sha256": None, "status": "missing"}
    assert config == {"path": str(tmp_path / ".agenticdoc" / "target.yml"), "canonical_path": None,
                      "sha256": None, "status": "missing"}
    assert source["path"] == source["canonical_path"] == str(tmp_path / "report.md")
    assert source["sha256"] == hashlib.sha256(b"actual\n").hexdigest()
    assert "file_evidence" not in json.loads(json.dumps(prepared))


def test_missing_source_dependency_is_authorized_but_outside_path_is_not(tmp_path: Path) -> None:
    with pytest.raises(sources.SourceMaterialError) as missing:
        sources.prepare_source_state(state("missing.md"), tmp_path)
    assert missing.value.file_evidence[-1] == {
        "path": str(tmp_path / "missing.md"), "canonical_path": None, "sha256": None, "status": "missing",
    }
    with pytest.raises(sources.SourceMaterialError) as outside:
        sources.prepare_source_state(state("../missing.md"), tmp_path)
    assert len(outside.value.file_evidence) == 2


def test_invalid_utf8_source_still_has_hash_for_replay_invalidation(tmp_path: Path) -> None:
    raw = b"\xff\xfe"
    (tmp_path / "binary.md").write_bytes(raw)
    with pytest.raises(sources.SourceMaterialError) as failure:
        sources.prepare_source_state(state("binary.md"), tmp_path)
    assert failure.value.file_evidence[-1]["sha256"] == hashlib.sha256(raw).hexdigest()


def test_chinese_execution_and_authority_negatives_survive_compression(tmp_path: Path) -> None:
    negatives = ["未执行", "未运行", "未批准", "未测试", "无证据", "没有证据", "结论不成立"]
    lines = [f"ordinary row {index} {'x' * 90}\n" for index in range(500)]
    for index, negative in enumerate(negatives):
        lines[150 + index * 20] = negative + "。\n"
    (tmp_path / "report.md").write_text("".join(lines), encoding="utf-8")
    prepared = sources.prepare_source_state(state("report.md"), tmp_path,
                                             max_total_tokens=2500, max_state_plus_question_tokens=2500)
    text = prepared["evidence_sources"][0]["text"]
    assert all(negative in text for negative in negatives)
