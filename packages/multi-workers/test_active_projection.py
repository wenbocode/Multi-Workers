"""test_active_projection.py — T-03: conductor/init complete active projection.

Offline, temporary-root only. No real model, no live key claim, no production
`.agenticdoc` index, no dist/global install, no full suite.

Covers design D-002/D-005/D-006 for the two writers owned by this task:
  * `autopilot.index_parallel._mutate` (all reachable conductor mutations:
    set_claim / clear_claim / status / phase / updated / heartbeat),
  * `mw.cmd_init` (fresh root, existing active table with a missing or old
    scalar projection, non-destructive semantics, shared lock, no deadlock).

Assertions: exact frozen bytes (`# AgenticTask Index\\n\\nactive_keys: [...]`),
0/1/N active, row order + normalize de-dup, foreign/unparsable authority rows
byte-identical, projection failure visible + recovered by the next mutation,
and no cross-file transaction claim.

T-09 adds strict raw-active validation, invalid-UTF-8 fail-closed, byte-exact
fragment writes, duplicate-target rejection, safe legacy-scalar migration and
an ordered-barrier / real-process init-race regression.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import socket
import subprocess
import sys
import textwrap
import time

import pytest

_PKG = pathlib.Path(__file__).resolve().parent
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

import mw  # noqa: E402
import mw_common  # noqa: E402
from autopilot import active_projection as projection  # noqa: E402
from autopilot import index_parallel, state  # noqa: E402

HEAD = (
    "# Index Parallel\n\n"
    "| Key | Status | Phase | ClaimId | Deps | Desc | Updated |\n"
    "|-----|--------|-------|---------|------|------|---------|\n"
)
TS = "2026-11-12 12:00"


def _verify(tag: str, **kv: object) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()))


def _row(key: str, status: str = "active", claim: str = "—", phase: str = "EXECUTE") -> str:
    return f"| {key} | {status} | {phase} | {claim} | - | desc | {TS} |"


def _project(tmp_path: pathlib.Path, lines: list[str], *, index_md: bytes | None = None) -> pathlib.Path:
    root = tmp_path / "proj"
    adoc = root / ".agenticdoc"
    adoc.mkdir(parents=True)
    (root / ".mw").mkdir(parents=True)
    (adoc / "_index.parallel").write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    if index_md is not None:
        (adoc / "_index.md").write_bytes(index_md)
    return root


def _authority(root: pathlib.Path) -> bytes:
    return (root / ".agenticdoc" / "_index.parallel").read_bytes()


def _projection(root: pathlib.Path) -> bytes:
    path = root / ".agenticdoc" / "_index.md"
    return path.read_bytes() if path.is_file() else b""


def _expected(keys: list[str]) -> bytes:
    return (
        "# AgenticTask Index\n\nactive_keys: "
        + json.dumps(keys, ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _authority_active(root: pathlib.Path) -> list[str]:
    """Independent read: active keys straight from the frozen row parser."""
    return [
        row["key"] for row in state.read_index(root)
        if row["status"].strip() == "active"
    ]


def _tmp_leftovers(root: pathlib.Path) -> list[str]:
    return sorted(p.name for p in (root / ".agenticdoc").glob("*.tmp*"))


# ── Pure serialization (D-002) ───────────────────────────────────────────────

def test_frozen_bytes_for_zero_one_and_many_active() -> None:
    assert projection.projection_text([]) == "# AgenticTask Index\n\nactive_keys: []\n"
    assert projection.projection_text([{"key": "a", "status": "active"}]) == (
        '# AgenticTask Index\n\nactive_keys: ["a"]\n'
    )
    assert projection.projection_text([
        {"key": "a", "status": "active"},
        {"key": "b", "status": "idle"},
        {"key": "c", "status": "active"},
        {"key": "d", "status": "done"},
    ]) == '# AgenticTask Index\n\nactive_keys: ["a", "c"]\n'
    text = projection.projection_text([{"key": "a", "status": "active"}])
    assert text.encode("utf-8") == _expected(["a"])
    assert b"\r" not in text.encode("utf-8") and not text.startswith("\ufeff")
    _verify("VC-006", bytes_exact=True, zero_one_many=3)


def test_parallel_order_normalize_dedup_and_first_spelling() -> None:
    rows = [
        {"key": "Key-A", "status": "active"},
        {"key": "Beta", "status": "idle"},
        {"key": "key-a", "status": "active"},   # normalized duplicate
        {"key": "gamma", "status": "active"},
        {"key": "Beta", "status": "active"},
    ]
    assert projection.active_keys(rows) == ["Key-A", "gamma", "Beta"]
    assert projection.projection_text(rows) == (
        '# AgenticTask Index\n\nactive_keys: ["Key-A", "gamma", "Beta"]\n'
    )
    # Exact predicate shared with update_index._projection_text / TS writer:
    # a differently-cased status cell is NOT an active row for ANY writer.
    assert projection.active_keys([{"key": "odd", "status": "ACTIVE"}]) == []
    _verify("D-002", row_order=True, dedup_first_spelling=True, exact_status=True)


@pytest.mark.parametrize(
    "key,code",
    [
        ("_index.md", "reserved-key-name"),
        ("_scratch", "reserved-key-name"),
        (".mw", "reserved-key-name"),
        ("../escape", "key-path-escape"),
        ("C:/escape", "key-path-escape"),
        ("bad|key", "key-illegal-shape"),
        ("x" * 65, "key-illegal-shape"),
        ("trailing.", "key-illegal-shape"),
        ("", "empty-key"),
    ],
)
def test_reserved_or_illegal_active_key_fails_closed(key: str, code: str) -> None:
    with pytest.raises(projection.ActiveProjectionError) as caught:
        projection.projection_text([{"key": key, "status": "active"}])
    assert code in str(caught.value)
    assert "refusing to project" in str(caught.value)
    # Idle rows with the same bad name are not projected and do not fail.
    assert projection.projection_text([{"key": key, "status": "idle"}]) == (
        "# AgenticTask Index\n\nactive_keys: []\n"
    )


# ── Conductor mutations (D-005 / D-006) ──────────────────────────────────────

def _mutations(root: pathlib.Path) -> list[tuple[str, object]]:
    """Every reachable mutation of the single claim-cell writer."""
    own = "autopilot@host:1"
    return [
        ("set_claim_plain", lambda: index_parallel.set_claim(root, "k1", claim_id=own)),
        (
            "set_claim_status_active",
            lambda: index_parallel.set_claim(root, "k1", claim_id=own, status="active"),
        ),
        (
            "set_claim_status_and_updated",
            lambda: index_parallel.set_claim(
                root, "k1", claim_id=own, status="active", updated="2026-11-12 13:00"
            ),
        ),
        (
            "heartbeat_updated_only",
            lambda: index_parallel.set_claim(
                root, "k1", claim_id=own, updated="2026-11-12 14:00"
            ),
        ),
        (
            "set_claim_status_idle",
            lambda: index_parallel.set_claim(root, "k1", claim_id=own, status="idle"),
        ),
        ("clear_claim_plain", lambda: index_parallel.clear_claim(root, "k1")),
        (
            "clear_claim_status_and_updated",
            lambda: index_parallel.clear_claim(
                root, "k1", status="idle", updated="2026-11-12 15:00"
            ),
        ),
        (
            "phase_and_status_cells",
            lambda: index_parallel._mutate(
                root,
                "k1",
                lambda cols, idx: _move_phase_and_status(cols),
            ),
        ),
    ]


def _move_phase_and_status(cols: list[str]) -> bool:
    cols[1] = "active"
    cols[2] = "VERIFY"
    return True


def test_all_reachable_mutations_refresh_complete_projection(tmp_path: pathlib.Path) -> None:
    names: list[str] = []
    for name in (
        "set_claim_plain", "set_claim_status_active", "set_claim_status_and_updated",
        "heartbeat_updated_only", "set_claim_status_idle", "clear_claim_plain",
        "clear_claim_status_and_updated", "phase_and_status_cells",
    ):
        root = _project(
            tmp_path / name,
            [HEAD.rstrip("\n"), _row("other-a", "active"),
             _row("k1", "active", claim="OLD:1"), _row("other-b", "active")],
        )
        mutations = dict(_mutations(root))
        before = _authority(root)
        assert mutations[name]() is True, name
        assert _authority(root) != before, name
        active = _authority_active(root)
        assert len(active) in (2, 3), name
        assert _projection(root) == _expected(active), name
        assert not (root / ".mw" / "index.lock").exists(), name
        assert _tmp_leftovers(root) == [], name
        names.append(name)
    assert len(names) == 8
    _verify("VC-006", conductor_mutations=8, projection_exact=True)


def test_zero_one_n_active_through_conductor_writes(tmp_path: pathlib.Path) -> None:
    root = _project(
        tmp_path / "count",
        [HEAD.rstrip("\n"), _row("k1", "idle"), _row("k2", "idle"), _row("k3", "idle")],
    )
    # 0 active: the first successful mutation writes the empty collection.
    assert index_parallel.set_claim(root, "k1", claim_id="autopilot@host:1", updated=TS)
    assert _projection(root) == _expected([])
    # 1 active.
    assert index_parallel.set_claim(
        root, "k1", claim_id="autopilot@host:1", status="active", updated=TS
    )
    assert _projection(root) == _expected(["k1"])
    # N active, in parallel row order.
    assert index_parallel.set_claim(
        root, "k2", claim_id="autopilot@host:2", status="active", updated=TS
    )
    assert index_parallel.set_claim(
        root, "k3", claim_id="autopilot@host:3", status="active", updated=TS
    )
    assert _projection(root) == _expected(["k1", "k2", "k3"])
    # Back to 0 through clear_claim(status=idle).
    for key in ("k1", "k2", "k3"):
        assert index_parallel.clear_claim(root, key, status="idle", updated=TS)
    assert _projection(root) == _expected([])
    assert _authority_active(root) == []
    _verify("VC-006", zero=True, one=True, n=True, projection_exact=True)


def test_non_target_authority_lines_are_byte_identical(tmp_path: pathlib.Path) -> None:
    lines = [
        HEAD.rstrip("\n"),
        "|   spaced  | active | EXECUTE | FOREIGN:99 | - | keep  spaces | 2026-01-01 00:00 |",
        "| k1 | idle | EXECUTE | — | - | desc | " + TS + " |",
        "| legacy | active | old-claim | note | 2026-01-01 00:00 |",  # 5-col legacy
        "this line is not a row and must survive verbatim",
        "",
        "| foreign-b | active | EXECUTE | OTHER:7 | - | desc | " + TS + " |",
    ]
    root = _project(tmp_path / "bytes", lines)
    original = _authority(root).decode("utf-8").splitlines(keepends=True)
    assert index_parallel.set_claim(
        root, "k1", claim_id="autopilot@host:1", status="active", updated=TS
    )
    after = _authority(root).decode("utf-8").splitlines(keepends=True)
    assert len(after) == len(original)
    assert [line for line in after if not line.startswith("| k1 ")] == [
        line for line in original if not line.startswith("| k1 ")
    ]
    # 7-col foreign rows AND the legacy 5-col active row are all projected.
    assert _projection(root) == _expected(
        ["spaced", "k1", "legacy", "foreign-b"]
    )
    assert _projection(root) == _expected(_authority_active(root))
    _verify("D-005", foreign_rows_byte_identical=True, legacy_row_projected=True)


def test_crlf_authority_keeps_crlf_and_projection_stays_lf(tmp_path: pathlib.Path) -> None:
    root = _project(
        tmp_path / "crlf",
        [HEAD.rstrip("\n"), _row("k1", "idle"), _row("k2", "active")],
    )
    path = root / ".agenticdoc" / "_index.parallel"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert index_parallel.set_claim(
        root, "k1", claim_id="autopilot@host:1", status="active", updated=TS
    )
    assert b"\r\n" in _authority(root) and b"\n" not in _authority(root).replace(b"\r\n", b"")
    assert _projection(root) == _expected(["k1", "k2"])
    assert b"\r" not in _projection(root)
    _verify("D-002", authority_crlf_preserved=True, projection_lf=True)


def test_no_change_and_missing_key_write_nothing(tmp_path: pathlib.Path) -> None:
    root = _project(
        tmp_path / "noop",
        [HEAD.rstrip("\n"), _row("k1", "active", claim="autopilot@host:1"), _row("k2", "active")],
    )
    authority_before = _authority(root)
    assert index_parallel.set_claim(
        root, "k1", claim_id="autopilot@host:1", status="active", updated=TS
    ) is False
    assert _authority(root) == authority_before
    assert _projection(root) == b""  # no successful write -> no projection
    assert index_parallel.set_claim(root, "ghost", claim_id="x") is False
    assert _authority(root) == authority_before
    assert _projection(root) == b""
    assert not (root / ".mw" / "index.lock").exists()


def test_t09_projection_io_failure_reports_partial_and_recovers(tmp_path: pathlib.Path) -> None:
    root = _project(
        tmp_path / "partial",
        [HEAD.rstrip("\n"), _row("k1", "idle"), _row("k2", "active")],
    )
    own = "autopilot@host:1"
    real_replace = os.replace

    def flaky_replace(src: object, dst: object, *args: object, **kwargs: object) -> None:
        if str(dst).endswith("_index.md"):
            raise OSError("simulated projection replace failure")
        return real_replace(src, dst, *args, **kwargs)  # type: ignore[arg-type]

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(projection.os, "replace", flaky_replace)
        with pytest.raises(projection.ActiveProjectionError) as caught:
            index_parallel.set_claim(root, "k1", claim_id=own, status="active", updated=TS)
    message = str(caught.value)
    assert "authority was already written" in message
    assert "no cross-file transaction" in message
    assert "next successful mutation" in message
    assert "PARTIAL WRITE" in message
    # Authority really moved; the stale projection was NOT silently reported OK.
    assert _authority_active(root) == ["k1", "k2"]
    assert _projection(root) == b""
    assert not (root / ".mw" / "index.lock").exists()  # finally released the lock
    assert _tmp_leftovers(root) == []
    # Recovery: the very next successful mutation rebuilds the exact projection.
    assert index_parallel.clear_claim(root, "k1", status="idle", updated=TS)
    assert _projection(root) == _expected(["k2"])
    assert _projection(root) == _expected(_authority_active(root))
    _verify("VC-006", partial_failure_visible=True, recovered_by_next_write=True)


def test_t09_write_projection_os_failure_is_a_clear_partial_error(tmp_path: pathlib.Path) -> None:
    root = _project(tmp_path / "osfail", [HEAD.rstrip("\n"), _row("k1", "active")])
    def refuse(src: object, dst: object, *args: object, **kwargs: object) -> None:
        raise OSError(f"EPERM simulated for {dst}")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(projection.os, "replace", refuse)
        with pytest.raises(projection.ActiveProjectionError) as caught:
            projection.write_projection(root, _expected(["k1"]).decode("utf-8"))
    assert "may already have changed" in str(caught.value)
    assert "no cross-file transaction" in str(caught.value)
    assert "PARTIAL WRITE" in str(caught.value)
    assert _projection(root) == b""
    assert _tmp_leftovers(root) == []


def test_conductor_projection_is_written_inside_the_shared_lock(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    root = _project(
        tmp_path / "lockhold",
        [HEAD.rstrip("\n"), _row("k1", "idle"), _row("k2", "active")],
    )
    held: list[bool] = []
    real_write = projection.write_projection

    def spy(project_root: pathlib.Path, text: str) -> None:
        held.append((project_root / ".mw" / "index.lock").exists())
        return real_write(project_root, text)

    monkeypatch.setattr(projection, "write_projection", spy)
    assert index_parallel.set_claim(
        root, "k1", claim_id="autopilot@host:1", status="active", updated=TS
    )
    assert held == [True]
    assert not (root / ".mw" / "index.lock").exists()
    assert _projection(root) == _expected(["k1", "k2"])
    _verify("D-005", same_index_lock=True)


def test_projection_never_uses_index_md_as_identity(tmp_path: pathlib.Path) -> None:
    # A hostile/stale _index.md must not influence the derived active set.
    root = _project(
        tmp_path / "not-authority",
        [HEAD.rstrip("\n"), _row("k1", "idle"), _row("k2", "active")],
        index_md=b'# AgenticTask Index\n\nactive_keys: ["evil", "_index.md"]\n',
    )
    assert index_parallel.set_claim(
        root, "k1", claim_id="autopilot@host:1", updated=TS
    )
    assert _projection(root) == _expected(["k2"])
    assert b"evil" not in _projection(root)
    assert _projection(root) == _expected(_authority_active(root))
    _verify("D-003", index_md_not_authority=True)


def test_illegal_active_authority_fails_closed_with_zero_writes(tmp_path: pathlib.Path) -> None:
    root = _project(
        tmp_path / "illegal",
        [HEAD.rstrip("\n"), _row("k1", "idle"), _row("_index.md", "active")],
    )
    before = _authority(root)
    with pytest.raises(projection.ActiveProjectionError) as caught:
        index_parallel.set_claim(
            root, "k1", claim_id="autopilot@host:1", status="active", updated=TS
        )
    assert "reserved-key-name" in str(caught.value)
    assert _authority(root) == before  # fail-closed BEFORE the authority write
    assert _projection(root) == b""
    assert not (root / ".mw" / "index.lock").exists()
    _verify("D-002", illegal_active_key_zero_write=True)


# ── mw init (D-006) ──────────────────────────────────────────────────────────

def _run_init(project: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    global_dir = project.parent / "global-ext"
    global_dir.mkdir(parents=True, exist_ok=True)
    (global_dir / "agent-team-loop.js").write_text("// offline dummy\n", encoding="utf-8")
    monkeypatch.setattr(mw, "_check_bundle", lambda: True)
    monkeypatch.setattr(mw, "_global_ext_dir", lambda: global_dir)
    monkeypatch.setattr(
        mw, "_install_project_agent_guide", lambda project_dir: (project_dir / "AGENTS.md", "")
    )
    args = argparse.Namespace(
        project=str(project), no_framework=True, codex_scope="project", sync_agentictask=None
    )
    return mw.cmd_init(args)


def test_init_fresh_root_writes_empty_collection(tmp_path: pathlib.Path, monkeypatch) -> None:
    root = tmp_path / "fresh"
    assert _run_init(root, monkeypatch) == 0
    assert _projection(root) == _expected([])
    assert _authority(root) == b""
    assert (root / ".agenticdoc" / "goal.md").is_file()
    assert not (root / ".mw" / "index.lock").exists()
    assert _tmp_leftovers(root) == []
    _verify("VC-006", init_fresh_root=True, zero=True)


def test_init_existing_active_table_missing_projection(tmp_path: pathlib.Path, monkeypatch) -> None:
    lines = [
        HEAD.rstrip("\n"),
        _row("k1", "active"),
        _row("k2", "idle"),
        _row("k3", "active"),
        _row("k4", "active"),
    ]
    root = _project(tmp_path / "missing", lines)
    authority_before = _authority(root)
    user_file = root / ".agenticdoc" / "goal.md"
    user_file.write_bytes(b"# user goal - never overwritten\n")
    notes = root / ".agenticdoc" / "notes.md"
    notes.write_bytes(b"user notes\n")
    assert _run_init(root, monkeypatch) == 0
    assert _projection(root) == _expected(["k1", "k3", "k4"])
    assert _projection(root) == _expected(_authority_active(root))
    assert b"[]" not in _projection(root)  # never blank non-empty active
    assert _authority(root) == authority_before
    assert user_file.read_bytes() == b"# user goal - never overwritten\n"
    assert notes.read_bytes() == b"user notes\n"
    assert not (root / ".mw" / "index.lock").exists()
    assert _tmp_leftovers(root) == []
    _verify("VC-006", init_existing_active=True, no_empty_overwrite=True, other_files_intact=True)


@pytest.mark.parametrize(
    "tag,scalar",
    [
        pytest.param("canonical-blank", b"# AgenticTask Index" + bytes([10, 10]) + b"active: " + bytes([10]), id="canonical-blank"),
        pytest.param("canonical-value", b"# AgenticTask Index" + bytes([10, 10]) + b"active: old-last-writer" + bytes([10]), id="canonical-value"),
        pytest.param("no-header-blank", b"active: " + bytes([10]), id="no-header-blank"),
        pytest.param("no-header-value", b"active: stale" + bytes([10]), id="no-header-value"),
        pytest.param("old-header", b"# legacy" + bytes([10]) + b"active: stale" + bytes([10]), id="old-header"),
        pytest.param("bare-scalar", b"active_keys: stale" + bytes([10]), id="bare-scalar"),
        pytest.param("bare-array", b'active_keys: ["k1"]' + bytes([10]), id="bare-array"),
        pytest.param("header-scalar-array", b"# AgenticTask Index" + bytes([10, 10]) + b"active_keys: stale" + bytes([10]), id="header-scalar-array"),
        pytest.param("header-stale-array", b"# AgenticTask Index" + bytes([10, 10]) + b'active_keys: ["stale"]' + bytes([10]), id="header-stale-array"),
        pytest.param("blank-file", b"", id="blank-file"),
        pytest.param("whitespace-file", bytes([10, 10]), id="whitespace-file"),
    ],
)
def test_t09_init_migrates_safely_recognized_legacy_scalar(
    tmp_path: pathlib.Path, monkeypatch, capsys, tag: str, scalar: bytes
) -> None:
    lines = [HEAD.rstrip("\n"), _row("k1", "active"), _row("k2", "active"), _row("k3", "idle")]
    root = _project(tmp_path / tag, lines, index_md=scalar)
    authority_before = _authority(root)
    assert _run_init(root, monkeypatch) == 0
    assert _projection(root) == _expected(["k1", "k2"])
    assert b"active:" not in _projection(root)
    assert b"active_keys:" in _projection(root)
    assert _authority(root) == authority_before
    captured = capsys.readouterr()
    assert "INCOMPLETE" not in captured.err
    assert not (root / ".mw" / "index.lock").exists()
    assert _tmp_leftovers(root) == []
    _verify("VC-006", legacy_scalar_migrated=True, canonical_projection=True)


def test_init_correct_projection_is_left_untouched(tmp_path: pathlib.Path, monkeypatch) -> None:
    lines = [HEAD.rstrip("\n"), _row("k1", "active"), _row("k2", "active")]
    root = _project(tmp_path / "correct", lines, index_md=_expected(["k1", "k2"]))
    path = root / ".agenticdoc" / "_index.md"
    before_bytes, before_mtime = path.read_bytes(), path.stat().st_mtime_ns
    results: list[str] = []
    real_sync = projection.sync_init_projection

    def spy(project_root: pathlib.Path) -> str:
        outcome = real_sync(project_root)
        results.append(outcome)
        return outcome

    monkeypatch.setattr(mw._ap_projection, "sync_init_projection", spy)
    assert _run_init(root, monkeypatch) == 0
    assert results == ["unchanged"]
    assert path.read_bytes() == before_bytes
    assert path.stat().st_mtime_ns == before_mtime
    _verify("D-006", init_idempotent=True)


def test_init_stale_array_projection_is_corrected(tmp_path: pathlib.Path, monkeypatch) -> None:
    lines = [HEAD.rstrip("\n"), _row("k1", "idle"), _row("k2", "active")]
    root = _project(tmp_path / "stale", lines, index_md=_expected(["k1", "k3"]))
    authority_before = _authority(root)
    assert _run_init(root, monkeypatch) == 0
    assert _projection(root) == _expected(["k2"])
    assert _authority(root) == authority_before
    _verify("VC-006", init_stale_projection_corrected=True)


@pytest.mark.parametrize(
    "tag,custom",
    [
        pytest.param("plain-user", b"# my hand-written index" + bytes([10]) + b"notes stay" + bytes([10]), id="plain-user"),
        pytest.param("header-plus-notes", b"# AgenticTask Index" + bytes([10, 10]) + b'active_keys: ["k1"]' + bytes([10]) + b"user notes" + bytes([10]), id="header-plus-notes"),
        pytest.param("header-scalar-plus-notes", b"# AgenticTask Index" + bytes([10, 10]) + b"active: old" + bytes([10]) + b"user notes" + bytes([10]), id="header-scalar-plus-notes"),
    ],
)
def test_t09_init_preserves_user_content_and_reports_incomplete(
    tmp_path: pathlib.Path, monkeypatch, capsys, tag: str, custom: bytes
) -> None:
    lines = [HEAD.rstrip("\n"), _row("k1", "active")]
    root = _project(tmp_path / tag, lines, index_md=custom)
    authority_before = _authority(root)
    assert _run_init(root, monkeypatch) == 1
    assert _projection(root) == custom
    assert _authority(root) == authority_before
    captured = capsys.readouterr()
    assert "INCOMPLETE" in captured.err
    assert "left untouched" in captured.err
    assert "not a safely migratable" in captured.err
    assert "Project initialized" not in captured.out
    assert not (root / ".mw" / "index.lock").exists()
    assert _tmp_leftovers(root) == []
    _verify("VC-006", user_content_preserved=True, projection_incomplete=True, rc_nonzero=True)


def test_init_takes_shared_index_lock_once_and_releases_it(tmp_path: pathlib.Path, monkeypatch) -> None:
    root = _project(tmp_path / "lock", [HEAD.rstrip("\n"), _row("k1", "active")])
    calls: list[pathlib.Path] = []
    real_acquire = mw_common.acquire_lock

    def spy(lock_file, *args, **kwargs):
        calls.append(pathlib.Path(lock_file))
        return real_acquire(lock_file, *args, **kwargs)

    monkeypatch.setattr(mw.mw_common, "acquire_lock", spy)
    assert _run_init(root, monkeypatch) == 0  # no deadlock: returns normally
    assert calls == [root / ".mw" / "index.lock"]
    assert not (root / ".mw" / "index.lock").exists()
    assert _projection(root) == _expected(["k1"])
    _verify("D-006", shared_lock_once=True, released=True, no_deadlock=True)


def test_init_illegal_active_authority_fails_closed(tmp_path: pathlib.Path, monkeypatch, capsys) -> None:
    lines = [HEAD.rstrip("\n"), _row("k1", "idle"), _row("_scratch", "active")]
    root = _project(tmp_path / "illegal-init", lines, index_md=b"# AgenticTask Index\n\nactive: \n")
    before = _authority(root)
    assert _run_init(root, monkeypatch) == 1
    assert "reserved-key-name" in capsys.readouterr().err
    assert _projection(root) == b"# AgenticTask Index\n\nactive: \n"
    assert _authority(root) == before
    assert not (root / ".mw" / "index.lock").exists()
    _verify("D-002", init_illegal_active_key_zero_write=True)


def test_t09_init_refuses_unparsable_active(tmp_path: pathlib.Path) -> None:
    # Any raw active row the strict parser cannot read must fail closed, even
    # when no valid key was parsed at all (the old empty-list guard was too lax).
    root = _project(tmp_path / 'unparsable', [HEAD.rstrip(chr(10))])
    bad = b'# Index Parallel' + bytes([10, 10]) + b'|k1|active|EXECUTE' + bytes([10])
    (root / '.agenticdoc' / '_index.parallel').write_bytes(bad)
    before = _authority(root)
    with pytest.raises(projection.ActiveProjectionError) as caught:
        projection.sync_init_projection(root)
    assert 'untrusted raw active row' in str(caught.value)
    assert 'cannot read' in str(caught.value)
    assert _authority(root) == before
    assert _projection(root) == b''
    _verify('D-006', no_empty_over_unparsable_active=True)


# ── T-09: strict raw-active validation, byte fragments, init migration/race ──

_REPO_ROOT = _PKG.parents[1]
_T09_NL = bytes([10])
_T09_CRLF = bytes([13, 10])
_T09_BOM = bytes([0xef, 0xbb, 0xbf])

_T09_UNTRUSTED_ACTIVE_LINES = [
    pytest.param('three-cells', '| bad | active | EXECUTE |', id='three-cells'),
    pytest.param('six-cells', '| bad | active | EXECUTE | c | - | extra |', id='six-cells'),
    pytest.param('eight-cells', '| bad | active | EXECUTE | c | - | desc | 2026 | extra |', id='eight-cells'),
    pytest.param('bare-seven', 'bad | active | EXECUTE | c | - | desc | 2026 |', id='bare-seven'),
    pytest.param('no-trailing-pipe', '| bad | active | EXECUTE | c | - | desc | 2026', id='no-trailing-pipe'),
]

_T09_INIT_CHILD = textwrap.dedent(r'''
    from __future__ import annotations

    import argparse
    import contextlib
    import io
    import json
    import os
    import pathlib
    import sys
    import time

    def main():
        root = pathlib.Path(sys.argv[1])
        pkg = pathlib.Path(sys.argv[2])
        global_dir = pathlib.Path(sys.argv[3])
        ready = pathlib.Path(sys.argv[4])
        gate = pathlib.Path(sys.argv[5])
        result = pathlib.Path(sys.argv[6])
        sys.path.insert(0, str(pkg))
        import mw
        import mw_common

        real_write_text = pathlib.Path.write_text
        real_write_bytes = pathlib.Path.write_bytes
        real_acquire = mw_common.acquire_lock
        used = [False]
        hook_name = ['']

        def trigger(hook):
            if used[0]:
                return
            used[0] = True
            hook_name[0] = hook
            lock = root / '.mw' / 'index.lock'
            ready.write_text(json.dumps({
                'hook': hook,
                'lockHeld': lock.exists(),
                'pid': os.getpid(),
            }), encoding='utf-8')
            deadline = time.monotonic() + 30.0
            while not os.path.exists(str(gate)):
                if time.monotonic() > deadline:
                    raise TimeoutError('gate was never released')
                time.sleep(0.01)

        def gated_write_text(self, data, *args, **kwargs):
            if self.name == '_index.parallel' and not used[0]:
                trigger('write_text')
            return real_write_text(self, data, *args, **kwargs)

        def gated_write_bytes(self, data, *args, **kwargs):
            if self.name == '_index.parallel' and not used[0]:
                trigger('write_bytes')
            return real_write_bytes(self, data, *args, **kwargs)

        def gated_acquire(lock_file, *args, **kwargs):
            if pathlib.Path(lock_file).name == 'index.lock' and not used[0]:
                trigger('acquire_lock')
            return real_acquire(lock_file, *args, **kwargs)

        pathlib.Path.write_text = gated_write_text
        pathlib.Path.write_bytes = gated_write_bytes
        mw_common.acquire_lock = gated_acquire

        global_dir.mkdir(parents=True, exist_ok=True)
        (global_dir / 'agent-team-loop.js').write_text('// offline dummy' + chr(10), encoding='utf-8')
        mw._check_bundle = lambda: True
        mw._global_ext_dir = lambda: global_dir
        mw._install_project_agent_guide = lambda project_dir: (project_dir / 'AGENTS.md', '')
        args = argparse.Namespace(
            project=str(root), no_framework=True, codex_scope='project',
            sync_agentictask=None,
        )
        out, err = io.StringIO(), io.StringIO()
        data = {'pid': os.getpid(), 'hook': hook_name[0], 'rc': None,
                'exception': None, 'stdout': '', 'stderr': ''}
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                data['rc'] = mw.cmd_init(args)
        except BaseException as exc:
            data['exception'] = repr(exc)
        data['stdout'] = out.getvalue()
        data['stderr'] = err.getvalue()
        data['hook'] = hook_name[0]
        result.write_text(json.dumps(data), encoding='utf-8')

    if __name__ == '__main__':
        main()
''').lstrip()

_T09_WRITER_CHILD = textwrap.dedent(r'''
    from __future__ import annotations

    import json
    import os
    import pathlib
    import socket
    import sys

    def main():
        root = pathlib.Path(sys.argv[1])
        pkg = pathlib.Path(sys.argv[2])
        done = pathlib.Path(sys.argv[3])
        sys.path.insert(0, str(pkg))
        import mw_common

        adoc = root / '.agenticdoc'
        mw_dir = root / '.mw'
        adoc.mkdir(parents=True, exist_ok=True)
        mw_dir.mkdir(parents=True, exist_ok=True)
        lock = mw_dir / 'index.lock'
        NL = bytes([10])
        authority = NL.join([
            b'# Index Parallel',
            b'',
            b'| Key | Status | Phase | ClaimId | Deps | Desc | Updated |',
            b'|-----|--------|-------|---------|------|------|---------|',
            b'| writer-active | active | EXECUTE | writer:1 | - | keep | 2026-01-01 00:00 |',
        ]) + NL
        projection = NL.join([
            b'# AgenticTask Index',
            b'',
            b'active_keys: [\"writer-active\"]',
        ]) + NL
        mw_common.acquire_lock(lock, retries=4, base_delay=0.02, deadline_s=5)
        try:
            (adoc / '_index.parallel').write_bytes(authority)
            (adoc / '_index.md').write_bytes(projection)
        finally:
            mw_common.release_lock(lock)
        done.write_text(json.dumps({
            'pid': os.getpid(), 'host': socket.gethostname(),
            'lock': str(lock), 'authority': authority.hex(),
        }), encoding='utf-8')

    if __name__ == '__main__':
        main()
''').lstrip()


def _t09_wait_for_file(path: pathlib.Path, timeout_s: float = 20.0) -> dict:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding='utf-8'))
            except (json.JSONDecodeError, OSError):
                pass
        time.sleep(0.01)
    raise AssertionError('timed out waiting for %s' % path)


def _t09_reap(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.kill()
    try:
        proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()


@pytest.mark.parametrize('tag,bad_line', _T09_UNTRUSTED_ACTIVE_LINES)
def test_t09_untrusted_active_row_shapes_are_rejected(tag: str, bad_line: str) -> None:
    lines = [HEAD.rstrip(chr(10)), _row('anchor', 'active'), bad_line, _row('k1', 'idle')]
    with pytest.raises(projection.ActiveProjectionError) as caught:
        projection.projection_text_from_lines(lines)
    assert 'untrusted raw active row' in str(caught.value)
    _verify('D-002', untrusted_shape_rejected=tag)


def test_t09_legacy_five_column_active_row_is_projected() -> None:
    lines = [
        HEAD.rstrip(chr(10)),
        '| legacy | active | old | note | 2026-01-01 00:00 |',
        _row('anchor', 'active'),
    ]
    assert projection.projection_text_from_lines(lines) == _expected(['legacy', 'anchor']).decode('utf-8')
    _verify('D-002', legacy_five_col_trusted=True)


def test_t09_non_active_unparsable_rows_are_preserved(tmp_path: pathlib.Path) -> None:
    lines = [HEAD.rstrip(chr(10)), '| broken | idle |', _row('k1', 'idle'), _row('foreign', 'active')]
    root = _project(tmp_path / 'non-active-bad', lines)
    before = _authority(root)
    assert index_parallel.set_claim(root, 'k1', claim_id='conductor:1', status='active', updated=TS)
    after = _authority(root)
    before_fragments = before.decode('utf-8').splitlines(keepends=True)
    after_fragments = after.decode('utf-8').splitlines(keepends=True)
    target_index = next(i for i, f in enumerate(before_fragments) if f.startswith('| k1 '))
    assert len(after_fragments) == len(before_fragments)
    for i, (b, a) in enumerate(zip(before_fragments, after_fragments)):
        if i != target_index:
            assert a == b, (i, b, a)
    assert b'| broken | idle |' in after
    assert _projection(root) == _expected(_authority_active(root))
    _verify('D-005', non_active_bad_rows_preserved=True)


def test_t09_mixed_valid_and_untrusted_active_rows_fail_closed_conductor(tmp_path: pathlib.Path) -> None:
    lines = [HEAD.rstrip(chr(10)), _row('anchor', 'active'), '| lost | active | EXECUTE |', _row('k1', 'idle')]
    root = _project(tmp_path / 'mixed-conductor', lines)
    before = _authority(root)
    with pytest.raises(projection.ActiveProjectionError) as caught:
        index_parallel.set_claim(root, 'k1', claim_id='conductor:1', status='active', updated=TS)
    assert 'untrusted raw active row' in str(caught.value)
    assert _authority(root) == before
    assert _projection(root) == b''
    assert not (root / '.mw' / 'index.lock').exists()
    _verify('VC-006', mixed_bad_active_zero_write=True, writer='conductor')


def test_t09_mixed_valid_and_untrusted_active_rows_fail_closed_init(tmp_path: pathlib.Path, monkeypatch, capsys) -> None:
    lines = [HEAD.rstrip(chr(10)), _row('anchor', 'active'), '| lost | active | EXECUTE |', _row('k1', 'idle')]
    root = _project(tmp_path / 'mixed-init', lines)
    before = _authority(root)
    with pytest.raises(projection.ActiveProjectionError) as caught:
        projection.sync_init_projection(root)
    assert 'untrusted raw active row' in str(caught.value)
    assert _authority(root) == before
    assert _projection(root) == b''
    assert _run_init(root, monkeypatch) == 1
    captured = capsys.readouterr()
    assert 'untrusted raw active row' in captured.err
    assert _authority(root) == before
    assert _projection(root) == b''
    assert not (root / '.mw' / 'index.lock').exists()
    _verify('VC-006', mixed_bad_active_zero_write=True, writer='init')


def test_t09_invalid_utf8_authority_fails_closed_conductor(tmp_path: pathlib.Path) -> None:
    root = _project(tmp_path / 'utf8-conductor', [HEAD.rstrip(chr(10))])
    bad = (
        b'# Index Parallel' + bytes([10, 10])
        + b'| foreign | active | EXECUTE | F:1 | - | bad' + bytes([255]) + b' | 2026-01-01 00:00 |' + bytes([10])
        + b'| k1 | idle | EXECUTE | ' + bytes([0xe2, 0x80, 0x94]) + b' | - | desc | ' + TS.encode('utf-8') + b' |' + bytes([10])
    )
    (root / '.agenticdoc' / '_index.parallel').write_bytes(bad)
    with pytest.raises(projection.ActiveProjectionError) as caught:
        index_parallel.set_claim(root, 'k1', claim_id='conductor:1', status='active', updated=TS)
    assert 'invalid UTF-8' in str(caught.value)
    assert _authority(root) == bad
    assert _projection(root) == b''
    assert not (root / '.mw' / 'index.lock').exists()
    _verify('D-005', invalid_utf8_zero_write=True, writer='conductor')


def test_t09_invalid_utf8_authority_fails_closed_init(tmp_path: pathlib.Path, monkeypatch, capsys) -> None:
    root = _project(tmp_path / 'utf8-init', [HEAD.rstrip(chr(10))])
    bad = (
        b'# Index Parallel' + bytes([10, 10])
        + b'| foreign | active | EXECUTE | F:1 | - | bad' + bytes([255]) + b' | 2026-01-01 00:00 |' + bytes([10])
        + b'| k1 | idle | EXECUTE | ' + bytes([0xe2, 0x80, 0x94]) + b' | - | desc | ' + TS.encode('utf-8') + b' |' + bytes([10])
    )
    (root / '.agenticdoc' / '_index.parallel').write_bytes(bad)
    assert _run_init(root, monkeypatch) == 1
    captured = capsys.readouterr()
    assert 'invalid UTF-8' in captured.err
    assert _authority(root) == bad
    assert _projection(root) == b''
    assert not (root / '.mw' / 'index.lock').exists()
    _verify('D-005', invalid_utf8_zero_write=True, writer='init')


def test_t09_invalid_utf8_projection_file_fails_closed_and_is_preserved(tmp_path: pathlib.Path, monkeypatch, capsys) -> None:
    lines = [HEAD.rstrip(chr(10)), _row('k1', 'active')]
    custom = (
        b'# AgenticTask Index' + bytes([10, 10])
        + b'active_keys: [\"k1\"]' + bytes([10]) + bytes([255]) + bytes([10])
    )
    root = _project(tmp_path / 'utf8-projection', lines, index_md=custom)
    before = _authority(root)
    assert _run_init(root, monkeypatch) == 1
    captured = capsys.readouterr()
    assert 'invalid UTF-8' in captured.err
    assert _projection(root) == custom
    assert _authority(root) == before
    assert not (root / '.mw' / 'index.lock').exists()
    _verify('D-006', invalid_utf8_projection_preserved=True, rc_nonzero=True)


def test_t09_conductor_preserves_mixed_eol_no_trailing_newline_and_trailing_blank_lines(tmp_path: pathlib.Path) -> None:
    raw = (
        _T09_BOM + b'# Index Parallel' + _T09_CRLF
        + _T09_NL
        + b'| foreign-a | active | EXECUTE | F:1 | - | keep  spaces | 2026-01-01 00:00 |' + _T09_NL
        + b'| k1 | idle | EXECUTE | ' + bytes([0xe2, 0x80, 0x94]) + b' | - | desc | ' + TS.encode('utf-8') + b' |' + _T09_CRLF
        + b'| legacy | active | old | note | 2026-01-01 00:00 |' + _T09_NL
        + b'not a row' + _T09_NL
        + _T09_CRLF
        + _T09_NL
        + b'   '
    )
    root = _project(tmp_path / 'mixed-eol', [HEAD.rstrip(chr(10))])
    (root / '.agenticdoc' / '_index.parallel').write_bytes(raw)
    before_fragments = raw.decode('utf-8').splitlines(keepends=True)
    assert index_parallel.set_claim(root, 'k1', claim_id='conductor:new', status='active', updated=TS)
    after = _authority(root)
    after_fragments = after.decode('utf-8').splitlines(keepends=True)
    target_index = next(i for i, f in enumerate(before_fragments) if f.startswith('| k1 '))
    assert len(after_fragments) == len(before_fragments)
    for i, (b, a) in enumerate(zip(before_fragments, after_fragments)):
        if i != target_index:
            assert a == b, (i, b, a)
    assert after_fragments[target_index].endswith(chr(13) + chr(10))
    assert after_fragments[target_index].startswith('| k1 ')
    assert after.endswith(b'   ')
    assert _T09_BOM in after
    assert _projection(root) == _expected(['foreign-a', 'k1', 'legacy'])
    assert not (root / '.mw' / 'index.lock').exists()
    _verify('D-005', mixed_eol=True, no_trailing_newline=True, multiple_trailing_blank_lines=True, non_target_bytes_identical=True)


def test_t09_conductor_target_last_line_without_newline_keeps_no_newline(tmp_path: pathlib.Path) -> None:
    raw = (
        b'# Index Parallel' + _T09_NL
        + b'| foreign | active | EXECUTE | F:1 | - | desc | 2026-01-01 00:00 |' + _T09_NL
        + b'| k1 | idle | EXECUTE | ' + bytes([0xe2, 0x80, 0x94]) + b' | - | desc | ' + TS.encode('utf-8') + b' |'
    )
    root = _project(tmp_path / 'target-last-line', [HEAD.rstrip(chr(10))])
    (root / '.agenticdoc' / '_index.parallel').write_bytes(raw)
    before_fragments = raw.decode('utf-8').splitlines(keepends=True)
    assert index_parallel.set_claim(root, 'k1', claim_id='conductor:new', status='active', updated=TS)
    after = _authority(root)
    after_fragments = after.decode('utf-8').splitlines(keepends=True)
    target_index = len(before_fragments) - 1
    assert len(after_fragments) == len(before_fragments)
    for i, (b, a) in enumerate(zip(before_fragments, after_fragments)):
        if i != target_index:
            assert a == b, (i, b, a)
    assert not after_fragments[target_index].endswith((chr(10), chr(13)))
    assert not after.endswith(bytes([10]))
    assert _projection(root) == _expected(['foreign', 'k1'])
    _verify('D-005', target_line_no_newline_preserved=True)


def test_t09_duplicate_normalized_target_is_rejected_with_zero_writes(tmp_path: pathlib.Path) -> None:
    lines = [HEAD.rstrip(chr(10)), _row('K1', 'active', claim='one'), _row('k1', 'active', claim='two')]
    root = _project(tmp_path / 'duplicate-target', lines)
    before = _authority(root)
    with pytest.raises(projection.ActiveProjectionError) as caught:
        index_parallel.set_claim(root, 'k1', claim_id='conductor:new')
    assert 'ambiguous' in str(caught.value).lower()
    assert _authority(root) == before
    assert _projection(root) == b''
    assert not (root / '.mw' / 'index.lock').exists()
    _verify('D-005', duplicate_normalized_target_rejected=True, zero_write=True)


def test_t09_init_creates_missing_authority_inside_shared_lock(tmp_path: pathlib.Path, monkeypatch) -> None:
    root = tmp_path / 'lock-create'
    held: list[bool] = []
    real_write_bytes = pathlib.Path.write_bytes

    def spy(self, data, *args, **kwargs):
        if self.name == '_index.parallel':
            held.append((self.parent.parent / '.mw' / 'index.lock').exists())
        return real_write_bytes(self, data, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, 'write_bytes', spy)
    assert _run_init(root, monkeypatch) == 0
    assert held == [True]
    assert _authority(root) == b''
    assert _projection(root) == _expected([])
    assert not (root / '.mw' / 'index.lock').exists()
    _verify('VC-004', init_creation_inside_shared_lock=True)


def test_t09_init_missing_table_race_preserves_existing_writer_active(tmp_path: pathlib.Path) -> None:
    root = tmp_path / 'race'
    (root / '.agenticdoc').mkdir(parents=True)
    (root / '.mw').mkdir(parents=True)
    helper_dir = tmp_path / 'helpers'
    helper_dir.mkdir(parents=True, exist_ok=True)
    init_helper = helper_dir / 'init_child.py'
    writer_helper = helper_dir / 'writer_child.py'
    init_helper.write_text(_T09_INIT_CHILD, encoding='utf-8')
    writer_helper.write_text(_T09_WRITER_CHILD, encoding='utf-8')
    global_dir = helper_dir / 'global-ext'
    ready_path = helper_dir / 'observed-missing.json'
    gate_path = helper_dir / 'go'
    result_path = helper_dir / 'init-result.json'
    done_path = helper_dir / 'writer-done.json'

    env = os.environ.copy()
    env.update({
        'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8',
        'PYTHONDONTWRITEBYTECODE': '1',
    })
    init_proc = subprocess.Popen(
        [sys.executable, str(init_helper), str(root), str(_PKG), str(global_dir),
         str(ready_path), str(gate_path), str(result_path)],
        cwd=str(_REPO_ROOT), env=env, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace',
    )
    try:
        ready = _t09_wait_for_file(ready_path, timeout_s=20)
        assert init_proc.poll() is None, 'init child did not wait on the ordered barrier'
        assert ready['lockHeld'] is False
        assert ready['hook'] in {'write_text', 'write_bytes', 'acquire_lock'}

        writer = subprocess.run(
            [sys.executable, str(writer_helper), str(root), str(_PKG), str(done_path)],
            cwd=str(_REPO_ROOT), env=env, capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=30,
        )
        assert writer.returncode == 0, (writer.stdout, writer.stderr)
        writer_done = _t09_wait_for_file(done_path, timeout_s=20)
        assert writer_done['pid'] != ready['pid']
        assert writer_done['host'] == socket.gethostname()

        gate_path.write_text('go', encoding='utf-8')
        _out, _err = init_proc.communicate(timeout=30)
        assert init_proc.returncode == 0, (_out, _err)
        init_result = json.loads(result_path.read_text(encoding='utf-8'))
        assert init_result['rc'] == 0, init_result
        assert init_result['exception'] is None
        assert init_result['hook'] == ready['hook']
        assert _authority(root) == bytes.fromhex(writer_done['authority'])
        assert b'writer-active' in _authority(root)
        assert _authority_active(root) == ['writer-active']
        assert _projection(root) == _expected(['writer-active'])
        assert not (root / '.mw' / 'index.lock').exists()
        assert _tmp_leftovers(root) == []
        print('[RACE] init_pid=%s writer_pid=%s hook=%s active_preserved=True'
              % (ready['pid'], writer_done['pid'], ready['hook']), flush=True)
        _verify('VC-004', init_writer_race=True, active_not_lost=True, real_process=True)
    finally:
        if not gate_path.exists():
            gate_path.write_text('go', encoding='utf-8')
        _t09_reap(init_proc)


def test_t09_init_projection_io_failure_is_visible_and_preserves_authority(tmp_path: pathlib.Path, monkeypatch, capsys) -> None:
    root = _project(tmp_path / 'init-io-failure', [HEAD.rstrip(chr(10)), _row('k1', 'active')])
    before = _authority(root)

    def refuse(src, dst, *args, **kwargs):
        raise OSError('EPERM simulated for %s' % dst)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(projection.os, 'replace', refuse)
        assert _run_init(root, monkeypatch) == 1
    captured = capsys.readouterr()
    assert 'Error syncing active-key projection' in captured.err
    assert 'PARTIAL WRITE' in captured.err
    assert _authority(root) == before
    assert _projection(root) == b''
    assert not (root / '.mw' / 'index.lock').exists()
    assert _tmp_leftovers(root) == []
    _verify('VC-006', init_projection_io_failure_visible=True, authority_preserved=True)
