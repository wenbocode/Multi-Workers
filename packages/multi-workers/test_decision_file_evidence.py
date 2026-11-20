"""Freshness checks read only previously authorized, bounded source snapshots."""

from __future__ import annotations

import hashlib
import pathlib

import pytest

import decision_file_evidence as evidence


def dependency(path: pathlib.Path) -> dict:
    return {"path": str(path.absolute()), "canonical_path": str(path.resolve()),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def test_unchanged_file_remains_fresh_and_changed_bytes_invalidate(tmp_path):
    path = tmp_path / "proof.md"
    path.write_text("verified source\n", encoding="utf-8")
    expected = [dependency(path)]
    original_digest = expected[0]["sha256"]
    before = evidence.check_file_evidence(expected)
    assert not before.changed
    path.write_text("FAILED source\n", encoding="utf-8")
    after = evidence.check_file_evidence(expected)
    assert after.changed and before.revision != after.revision
    assert expected[0]["sha256"] == original_digest


def test_missing_source_appearing_invalidates_without_reading_new_target(tmp_path, monkeypatch):
    path = tmp_path / "missing.md"
    expected = [{"path": str(path), "canonical_path": None, "sha256": None, "status": "missing"}]
    assert not evidence.check_file_evidence(expected).changed
    path.write_text("now present", encoding="utf-8")
    monkeypatch.setattr(pathlib.Path, "open", lambda *_a, **_k: pytest.fail("new target not authorized for freshness reads"))
    assert evidence.check_file_evidence(expected).changed


def test_alias_target_change_is_detected_before_open(tmp_path, monkeypatch):
    original = tmp_path / "original.md"
    replacement = tmp_path / "replacement.md"
    original.write_text("original", encoding="utf-8")
    replacement.write_text("replacement", encoding="utf-8")
    alias = tmp_path / "alias.md"
    expected = [{"path": str(alias), "canonical_path": str(original),
                 "sha256": hashlib.sha256(b"original").hexdigest()}]
    resolve = pathlib.Path.resolve

    def changed_target(path, **kwargs):
        return replacement if path == alias else resolve(path, **kwargs)

    monkeypatch.setattr(pathlib.Path, "resolve", changed_target)
    monkeypatch.setattr(pathlib.Path, "open", lambda *_a, **_k: pytest.fail("retargeted alias must not be opened"))
    assert evidence.check_file_evidence(expected).changed


def test_disappeared_file_invalidates_hash(tmp_path):
    path = tmp_path / "proof.md"
    path.write_text("proof", encoding="utf-8")
    expected = [dependency(path)]
    path.unlink()
    assert evidence.check_file_evidence(expected).changed


def test_oversized_file_is_not_opened(tmp_path, monkeypatch):
    path = tmp_path / "large.log"
    with path.open("wb") as handle:
        handle.truncate(evidence.MAX_FILE_BYTES + 1)
    expected = [{"path": str(path), "canonical_path": str(path), "sha256": "a" * 64}]
    monkeypatch.setattr(pathlib.Path, "open", lambda *_a, **_k: pytest.fail("oversized file must not be opened"))
    assert evidence.check_file_evidence(expected).changed


@pytest.mark.parametrize("raw", [
    None, {}, {"path": "relative.md", "sha256": None},
    {"path": "/absolute", "sha256": "bad"},
    {"path": "/absolute", "sha256": None, "status": "made-up"},
    {"path": "/absolute", "sha256": None, "status": None},
    {"path": "/absolute", "sha256": "a" * 64, "canonical_path": None},
])
def test_malformed_dependency_refuses_before_read(raw, monkeypatch):
    monkeypatch.setattr(pathlib.Path, "resolve", lambda *_a, **_k: pytest.fail("malformed metadata must not resolve paths"))
    with pytest.raises(evidence.FileEvidenceError):
        evidence.check_file_evidence([raw])


def test_absent_field_differs_from_malformed_present_metadata():
    assert evidence.parse_file_evidence({}) is None
    assert evidence.parse_file_evidence({"file_evidence": []}) == []
    with pytest.raises(evidence.FileEvidenceError):
        evidence.parse_file_evidence({"file_evidence": None})
    with pytest.raises(evidence.FileEvidenceError):
        evidence.check_file_evidence([{}] * (evidence.MAX_DEPENDENCIES + 1))


def test_minimal_legacy_metadata_normalizes_like_ts(tmp_path):
    path = tmp_path / "proof.md"
    path.write_text("proof", encoding="utf-8")
    hashed = {"path": str(path), "sha256": hashlib.sha256(b"proof").hexdigest()}
    assert not evidence.check_file_evidence([hashed]).changed
    missing = {"path": str(tmp_path / "not-created"), "sha256": None}
    assert not evidence.check_file_evidence([missing]).changed


def test_read_change_during_hash_is_not_trusted(tmp_path, monkeypatch):
    path = tmp_path / "proof.md"
    path.write_text("proof", encoding="utf-8")
    expected = [dependency(path)]
    real_fstat = evidence.os.fstat
    calls = []

    def changed_stat(descriptor):
        calls.append(1)
        if len(calls) == 2:
            path.write_text("changed during read", encoding="utf-8")
        return real_fstat(descriptor)

    monkeypatch.setattr(evidence.os, "fstat", changed_stat)
    assert evidence.check_file_evidence(expected).changed
