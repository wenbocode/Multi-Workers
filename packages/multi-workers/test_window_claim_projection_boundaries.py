"""T-18: precise init projection shapes and strict authority header boundaries.

Offline, temporary-root only. Reuses the existing ``test_active_projection``
offline bundle/guide fixture through ``_run_init`` -> real ``mw.cmd_init`` and
the existing row/projection helpers; no global config, model, claim, decision,
QG, sign, build, install or cross-language integration is exercised here.
"""

from __future__ import annotations

import os
import pathlib
import sys

import pytest

_PKG = pathlib.Path(__file__).resolve().parent
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

from autopilot import active_projection as projection  # noqa: E402
from autopilot import index_parallel  # noqa: E402
import test_active_projection as baseline  # noqa: E402

LF = b"\n"
CRLF = b"\r\n"
BOM = b"\xef\xbb\xbf"
TS = baseline.TS


def _assert_preserving_init_incomplete(
    root: pathlib.Path,
    original: bytes,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A real cmd_init must preserve unproven content and report INCOMPLETE."""
    authority_before = baseline._authority(root)
    assert baseline._projection(root) == original
    assert projection._projection_shape(original) == "user"
    assert baseline._run_init(root, monkeypatch) == 1
    assert baseline._projection(root) == original
    assert baseline._authority(root) == authority_before
    captured = capsys.readouterr()
    assert "INCOMPLETE" in captured.err
    assert "not a safely migratable" in captured.err
    assert "left untouched" in captured.err
    assert "Project initialized" not in captured.out
    assert not (root / ".mw" / "index.lock").exists()
    assert baseline._tmp_leftovers(root) == []


_UNSAFE_INIT_SHAPES = [
    pytest.param("personal_array", b'# Personal Notes\nactive_keys: ["my-list"]\n', id="personal_array"),
    pytest.param("personal_scalar", b"# Personal Notes\nactive: my-list\n", id="personal_scalar"),
    pytest.param("arbitrary_title_array", b'# Arbitrary Name\nactive_keys: ["Key", "Status", "Phase"]\n', id="arbitrary_title_array"),
    pytest.param("arbitrary_title_scalar", b"# Arbitrary Name\nactive: Key\n", id="arbitrary_title_scalar"),
    pytest.param("canonical_lookalike_array", b'# AgenticTask Index Notes\nactive_keys: ["x"]\n', id="canonical_lookalike_array"),
    pytest.param("canonical_lookalike_scalar", b"# AgenticTask Index Notes\nactive: x\n", id="canonical_lookalike_scalar"),
    pytest.param("legacy_lookalike_array", b'# legacy\nactive_keys: ["x"]\n', id="legacy_lookalike_array"),
    pytest.param("legacy_other_scalar", b"# legacy\nactive: other\n", id="legacy_other_scalar"),
    pytest.param("canonical_header_plus_prose", b'# AgenticTask Index\n\nactive_keys: ["x"]\nuser notes\n', id="canonical_header_plus_prose"),
    pytest.param("canonical_scalar_plus_prose", b"# AgenticTask Index\n\nactive: old\nuser notes\n", id="canonical_scalar_plus_prose"),
    pytest.param("arbitrary_title_plus_prose", b'# Arbitrary Name\nactive_keys: ["x"]\nmore prose\n', id="arbitrary_title_plus_prose"),
    pytest.param("legacy_array_plus_prose", b'# legacy\nactive_keys: ["x"]\nmore prose\n', id="legacy_array_plus_prose"),
]


@pytest.mark.parametrize("tag,custom", _UNSAFE_INIT_SHAPES)
def test_real_cmd_init_preserves_unapproved_shapes(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tag: str,
    custom: bytes,
) -> None:
    """N3 RED: arbitrary # headings and extra prose are not program content."""
    lines = [baseline.HEAD.rstrip("\n"), baseline._row("k1", "active")]
    root = baseline._project(tmp_path / tag, lines, index_md=custom)
    _assert_preserving_init_incomplete(root, custom, monkeypatch, capsys)
    print(f"[T18] init_preserved={tag} rc=1 incomplete=true", flush=True)


_SAFE_LEGACY_SHAPES = [
    pytest.param("canonical_blank", b"# AgenticTask Index\n\nactive: \n", id="canonical_blank"),
    pytest.param("canonical_value", b"# AgenticTask Index\n\nactive: old-last-writer\n", id="canonical_value"),
    pytest.param("no_header_blank", b"active: \n", id="no_header_blank"),
    pytest.param("no_header_value", b"active: stale\n", id="no_header_value"),
    pytest.param("old_header", b"# legacy\nactive: stale\n", id="old_header"),
    pytest.param("bare_scalar", b"active_keys: stale\n", id="bare_scalar"),
    pytest.param("bare_array", b'active_keys: ["k1"]\n', id="bare_array"),
    pytest.param("header_scalar_array", b"# AgenticTask Index\n\nactive_keys: stale\n", id="header_scalar_array"),
    pytest.param("header_stale_array", b'# AgenticTask Index\n\nactive_keys: ["stale"]\n', id="header_stale_array"),
    pytest.param("blank_file", b"", id="blank_file"),
    pytest.param("whitespace_file", b"\n\n", id="whitespace_file"),
]


@pytest.mark.parametrize("tag,custom", _SAFE_LEGACY_SHAPES)
def test_frozen_safe_legacy_shapes_still_migrate(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tag: str,
    custom: bytes,
) -> None:
    """Exact frozen program/legacy shapes keep their approved migration."""
    lines = [
        baseline.HEAD.rstrip("\n"),
        baseline._row("k1", "active"),
        baseline._row("k2", "active"),
        baseline._row("k3", "idle"),
    ]
    root = baseline._project(tmp_path / tag, lines, index_md=custom)
    authority_before = baseline._authority(root)
    assert baseline._run_init(root, monkeypatch) == 0
    assert baseline._projection(root) == baseline._expected(["k1", "k2"])
    assert b"active:" not in baseline._projection(root)
    assert b"active_keys:" in baseline._projection(root)
    assert baseline._authority(root) == authority_before
    captured = capsys.readouterr()
    assert "INCOMPLETE" not in captured.err
    assert "Project initialized" in captured.out
    assert not (root / ".mw" / "index.lock").exists()
    assert baseline._tmp_leftovers(root) == []
    print(f"[T18] safe_legacy_migrated={tag} rc=0", flush=True)


def test_canonical_header_and_separator_are_decoration_not_data() -> None:
    raw = (
        baseline.HEAD
        + baseline._row("k1", "active")
        + "\n"
        + baseline._row("k2", "idle")
        + "\n"
    )
    lines = raw.splitlines(keepends=True)
    parsed = projection.strict_rows_with_lines(lines)
    assert [(row["key"], row["status"]) for _, row, _, _ in parsed] == [
        ("k1", "active"),
        ("k2", "idle"),
    ]
    header = "| Key | Status | Phase | ClaimId | Deps | Desc | Updated |"
    separator = "|-----|--------|-------|---------|------|------|---------|"
    assert projection._strict_row_from_line(header, 1) is None
    assert projection._strict_row_from_line(separator, 2) is None
    assert projection.projection_text_from_lines(lines) == baseline._expected(["k1"]).decode("utf-8")
    print("[T18] canonical_header=decoration separator=decoration", flush=True)


def test_valid_key_named_key_active_row_survives_conductor_mutation(tmp_path: pathlib.Path) -> None:
    """A legal key literally named Key is data, not the whole header."""
    key_row = (
        "| Key | active | EXECUTE | foreign:1 | - | desc | " + TS + " |"
    )
    lines = [
        baseline.HEAD.rstrip("\n"),
        key_row,
        baseline._row("k1", "idle"),
        baseline._row("foreign", "active"),
    ]
    root = baseline._project(tmp_path / "key_data", lines)
    assert projection.key_name_refusal("Key") is None
    before = baseline._authority(root)
    before_fragments = before.decode("utf-8").splitlines(keepends=True)
    parsed = projection.strict_rows_from_lines(before_fragments)
    assert [row["key"] for row in parsed if row["status"] == "active"] == ["Key", "foreign"]
    assert index_parallel.set_claim(
        root, "Key", claim_id="conductor:1", status="active", updated=TS
    )
    after = baseline._authority(root)
    after_fragments = after.decode("utf-8").splitlines(keepends=True)
    target_index = next(
        index for index, fragment in enumerate(before_fragments)
        if fragment.startswith("| Key | active")
    )
    assert len(after_fragments) == len(before_fragments)
    for index, (old, new) in enumerate(zip(before_fragments, after_fragments)):
        if index != target_index:
            assert new == old, (index, old, new)
    assert after_fragments[target_index].startswith("| Key | active | EXECUTE | conductor:1 |")
    assert baseline._projection(root) == baseline._expected(["Key", "foreign"])
    assert projection.active_keys(projection.strict_rows_from_lines(after_fragments)) == ["Key", "foreign"]
    assert not (root / ".mw" / "index.lock").exists()
    assert baseline._tmp_leftovers(root) == []
    print("[T18] key_data=active projection_complete=True conductor_target=True", flush=True)


def test_conductor_complete_projection_zero_one_many_with_key_data(tmp_path: pathlib.Path) -> None:
    lines = [
        baseline.HEAD.rstrip("\n"),
        baseline._row("Key", "idle", claim="—"),
        baseline._row("k1", "idle", claim="—"),
        baseline._row("k2", "idle", claim="—"),
    ]
    root = baseline._project(tmp_path / "key_counts", lines)
    own = "conductor:1"
    assert index_parallel.set_claim(root, "Key", claim_id=own, status="active", updated=TS)
    assert baseline._projection(root) == baseline._expected(["Key"])
    assert index_parallel.set_claim(root, "k1", claim_id=own, status="active", updated=TS)
    assert baseline._projection(root) == baseline._expected(["Key", "k1"])
    assert index_parallel.set_claim(root, "k2", claim_id=own, status="active", updated=TS)
    assert baseline._projection(root) == baseline._expected(["Key", "k1", "k2"])
    for key in ("Key", "k1", "k2"):
        assert index_parallel.clear_claim(root, key, status="idle", updated=TS)
    assert baseline._projection(root) == baseline._expected([])
    assert not (root / ".mw" / "index.lock").exists()
    assert baseline._tmp_leftovers(root) == []
    print("[T18] key_data_counts=0,1,N projection_exact=True", flush=True)


_BAD_KEY_LIKE_ACTIVE_LINES = [
    pytest.param("three_cells", "| Key | active |", id="three_cells"),
    pytest.param("four_cells", "| Key | active | EXECUTE |", id="four_cells"),
    pytest.param("six_cells", "| Key | active | EXECUTE | c | - | extra |", id="six_cells"),
    pytest.param("eight_cells", "| Key | active | EXECUTE | c | - | desc | 2026 | extra |", id="eight_cells"),
    pytest.param("bare_seven", "Key | active | EXECUTE | c | - | desc | 2026 |", id="bare_seven"),
    pytest.param("no_trailing_pipe", "| Key | active | EXECUTE | c | - | desc | 2026", id="no_trailing_pipe"),
    pytest.param("header_looking_eight", "| Key | active | Status | Phase | ClaimId | Deps | Desc | Updated |", id="header_looking_eight"),
    pytest.param("empty_key", "|  | active | EXECUTE | c | - | desc | 2026 |", id="empty_key"),
]


@pytest.mark.parametrize("tag,bad_line", _BAD_KEY_LIKE_ACTIVE_LINES)
def test_bad_key_or_header_looking_active_shapes_fail_closed(
    tmp_path: pathlib.Path, tag: str, bad_line: str
) -> None:
    lines = [
        baseline.HEAD.rstrip("\n"),
        baseline._row("anchor", "active"),
        bad_line,
        baseline._row("k1", "idle"),
    ]
    root = baseline._project(tmp_path / tag, lines)
    before = baseline._authority(root)
    with pytest.raises(projection.ActiveProjectionError) as caught:
        projection.projection_text_from_lines(before.decode("utf-8").splitlines(keepends=True))
    assert "untrusted raw active row" in str(caught.value)
    with pytest.raises(projection.ActiveProjectionError):
        index_parallel.set_claim(
            root, "k1", claim_id="conductor:1", status="active", updated=TS
        )
    assert baseline._authority(root) == before
    assert baseline._projection(root) == b""
    assert not (root / ".mw" / "index.lock").exists()
    assert baseline._tmp_leftovers(root) == []
    print(f"[T18] bad_active_shape=rejected_zero_write tag={tag}", flush=True)


_ILLEGAL_ACTIVE_KEYS = [
    pytest.param("dash_bad", "-bad", id="dash_bad"),
    pytest.param("hash_bad", "#bad", id="hash_bad"),
    pytest.param("reserved_bad", "_scratch", id="reserved_bad"),
    pytest.param("drive_bad", "C:/escape", id="drive_bad"),
    pytest.param("pipe_bad", "bad|key", id="pipe_bad"),
]


@pytest.mark.parametrize("tag,bad_key", _ILLEGAL_ACTIVE_KEYS)
def test_illegal_active_key_names_fail_closed_zero_write(
    tmp_path: pathlib.Path, tag: str, bad_key: str
) -> None:
    lines = [
        baseline.HEAD.rstrip("\n"),
        baseline._row("anchor", "active"),
        baseline._row(bad_key, "active", claim="foreign:1"),
        baseline._row("k1", "idle"),
    ]
    root = baseline._project(tmp_path / tag, lines)
    before = baseline._authority(root)
    with pytest.raises(projection.ActiveProjectionError):
        index_parallel.set_claim(
            root, "k1", claim_id="conductor:1", status="active", updated=TS
        )
    assert baseline._authority(root) == before
    assert baseline._projection(root) == b""
    assert not (root / ".mw" / "index.lock").exists()
    assert baseline._tmp_leftovers(root) == []
    print(f"[T18] illegal_active_key=rejected_zero_write tag={tag}", flush=True)


@pytest.mark.parametrize("tag,bad_line", baseline._T09_UNTRUSTED_ACTIVE_LINES)
def test_existing_untrusted_active_shapes_still_fail_closed(
    tmp_path: pathlib.Path, tag: str, bad_line: str
) -> None:
    lines = [
        baseline.HEAD.rstrip("\n"),
        baseline._row("anchor", "active"),
        bad_line,
        baseline._row("k1", "idle"),
    ]
    root = baseline._project(tmp_path / tag, lines)
    before = baseline._authority(root)
    with pytest.raises(projection.ActiveProjectionError):
        index_parallel.set_claim(
            root, "k1", claim_id="conductor:1", status="active", updated=TS
        )
    assert baseline._authority(root) == before
    assert baseline._projection(root) == b""
    assert not (root / ".mw" / "index.lock").exists()
    assert baseline._tmp_leftovers(root) == []
    print(f"[T18] existing_bad_shape=still_rejected tag={tag}", flush=True)


def test_non_active_bad_lines_are_preserved_byte_exact(tmp_path: pathlib.Path) -> None:
    lines = [
        baseline.HEAD.rstrip("\n"),
        "| broken | idle |",
        "| Key | idle |",
        baseline._row("k1", "idle"),
        baseline._row("foreign", "active"),
    ]
    root = baseline._project(tmp_path / "non_active_bad", lines)
    before = baseline._authority(root)
    assert index_parallel.set_claim(
        root, "k1", claim_id="conductor:1", status="active", updated=TS
    )
    after = baseline._authority(root)
    before_fragments = before.decode("utf-8").splitlines(keepends=True)
    after_fragments = after.decode("utf-8").splitlines(keepends=True)
    target_index = next(
        index for index, fragment in enumerate(before_fragments)
        if fragment.startswith("| k1 ")
    )
    assert len(after_fragments) == len(before_fragments)
    for index, (old, new) in enumerate(zip(before_fragments, after_fragments)):
        if index != target_index:
            assert new == old, (index, old, new)
    assert b"| broken | idle |" in after
    assert b"| Key | idle |" in after
    assert baseline._projection(root) == baseline._expected(["k1", "foreign"])
    assert not (root / ".mw" / "index.lock").exists()
    assert baseline._tmp_leftovers(root) == []
    print("[T18] non_active_bad_lines=byte_preserved", flush=True)


def test_conductor_preserves_mixed_eol_bom_and_non_target_bytes(tmp_path: pathlib.Path) -> None:
    raw = (
        BOM + b"# Index Parallel" + CRLF
        + LF
        + b"| foreign-a | active | EXECUTE | F:1 | - | keep  spaces | 2026-01-01 00:00 |" + LF
        + b"| Key | active | EXECUTE | F:2 | - | desc | " + TS.encode("utf-8") + b" |" + CRLF
        + b"| k1 | idle | EXECUTE | \xe2\x80\x94 | - | desc | " + TS.encode("utf-8") + b" |" + LF
        + b"| legacy | active | old | note | 2026-01-01 00:00 |" + LF
        + b"not a row" + LF
        + CRLF
        + LF
        + b"   "
    )
    root = baseline._project(tmp_path / "mixed_eol", [baseline.HEAD.rstrip("\n")])
    (root / ".agenticdoc" / "_index.parallel").write_bytes(raw)
    before_fragments = raw.decode("utf-8").splitlines(keepends=True)
    assert index_parallel.set_claim(
        root, "k1", claim_id="conductor:new", status="active", updated="2026-11-12 13:00"
    )
    after = baseline._authority(root)
    after_fragments = after.decode("utf-8").splitlines(keepends=True)
    target_index = next(
        index for index, fragment in enumerate(before_fragments)
        if fragment.startswith("| k1 ")
    )
    assert len(after_fragments) == len(before_fragments)
    for index, (old, new) in enumerate(zip(before_fragments, after_fragments)):
        if index != target_index:
            assert new == old, (index, old, new)
    assert after_fragments[target_index].endswith("\n")
    assert after_fragments[target_index].startswith("| k1 ")
    assert after.endswith(b"   ")
    assert BOM in after
    assert baseline._projection(root) == baseline._expected(["foreign-a", "Key", "k1", "legacy"])
    assert b"\r" not in baseline._projection(root)
    assert not (root / ".mw" / "index.lock").exists()
    assert baseline._tmp_leftovers(root) == []
    print("[T18] d005_non_target_bytes=identical mixed_eol=True key_data=True", flush=True)


def test_invalid_utf8_authority_fails_closed_zero_write(tmp_path: pathlib.Path) -> None:
    bad = (
        b"# Index Parallel" + LF + LF
        + b"| foreign | active | EXECUTE | F:1 | - | bad" + bytes([255]) + b" | 2026-01-01 00:00 |" + LF
        + baseline._row("k1", "idle").encode("utf-8") + LF
    )
    root = baseline._project(tmp_path / "utf8_authority", [baseline.HEAD.rstrip("\n")])
    (root / ".agenticdoc" / "_index.parallel").write_bytes(bad)
    with pytest.raises(projection.ActiveProjectionError) as caught:
        projection.strict_rows_from_bytes(bad)
    assert "invalid UTF-8" in str(caught.value)
    with pytest.raises(projection.ActiveProjectionError):
        index_parallel.set_claim(
            root, "k1", claim_id="conductor:1", status="active", updated=TS
        )
    assert baseline._authority(root) == bad
    assert baseline._projection(root) == b""
    assert not (root / ".mw" / "index.lock").exists()
    assert baseline._tmp_leftovers(root) == []
    print("[T18] invalid_utf8_authority=fail_closed_zero_write", flush=True)


def test_invalid_utf8_projection_file_is_preserved(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    custom = (
        b"# AgenticTask Index" + LF + LF
        + b'active_keys: ["k1"]' + LF + bytes([255]) + LF
    )
    lines = [baseline.HEAD.rstrip("\n"), baseline._row("k1", "active")]
    root = baseline._project(tmp_path / "utf8_projection", lines, index_md=custom)
    authority_before = baseline._authority(root)
    assert baseline._run_init(root, monkeypatch) == 1
    captured = capsys.readouterr()
    assert "invalid UTF-8" in captured.err
    assert baseline._projection(root) == custom
    assert baseline._authority(root) == authority_before
    assert not (root / ".mw" / "index.lock").exists()
    assert baseline._tmp_leftovers(root) == []
    print("[T18] invalid_utf8_projection=preserved rc=1", flush=True)


def test_conductor_projection_write_is_inside_shared_lock(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lines = [
        baseline.HEAD.rstrip("\n"),
        baseline._row("k1", "idle"),
        baseline._row("foreign", "active"),
    ]
    root = baseline._project(tmp_path / "lock_hold", lines)
    held: list[bool] = []
    real_write = projection.write_projection

    def spy(project_root: pathlib.Path, text: str) -> None:
        held.append((project_root / ".mw" / "index.lock").exists())
        return real_write(project_root, text)

    monkeypatch.setattr(projection, "write_projection", spy)
    assert index_parallel.set_claim(
        root, "k1", claim_id="conductor:1", status="active", updated=TS
    )
    assert held == [True]
    assert not (root / ".mw" / "index.lock").exists()
    assert baseline._projection(root) == baseline._expected(["k1", "foreign"])
    print("[T18] same_index_lock=True", flush=True)


def test_projection_failure_is_visible_and_recovers(tmp_path: pathlib.Path) -> None:
    lines = [
        baseline.HEAD.rstrip("\n"),
        baseline._row("k1", "idle"),
        baseline._row("foreign", "active"),
    ]
    root = baseline._project(tmp_path / "partial", lines)
    real_replace = os.replace

    def flaky_replace(src: object, dst: object, *args: object, **kwargs: object) -> None:
        if str(dst).endswith("_index.md"):
            raise OSError("simulated projection replace failure")
        return real_replace(src, dst, *args, **kwargs)  # type: ignore[arg-type]

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(projection.os, "replace", flaky_replace)
        with pytest.raises(projection.ActiveProjectionError) as caught:
            index_parallel.set_claim(
                root, "k1", claim_id="conductor:1", status="active", updated=TS
            )
    message = str(caught.value)
    assert "PARTIAL WRITE" in message
    assert "authority was already written" in message
    assert "no cross-file transaction" in message
    assert "next successful mutation" in message
    assert baseline._authority_active(root) == ["k1", "foreign"]
    assert baseline._projection(root) == b""
    assert not (root / ".mw" / "index.lock").exists()
    assert baseline._tmp_leftovers(root) == []
    assert index_parallel.clear_claim(root, "k1", status="idle", updated=TS)
    assert baseline._projection(root) == baseline._expected(["foreign"])
    print("[T18] partial_write=visible recovery=next_mutation", flush=True)
