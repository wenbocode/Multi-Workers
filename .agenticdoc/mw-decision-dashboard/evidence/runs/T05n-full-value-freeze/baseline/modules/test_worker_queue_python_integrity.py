"""T-18 / mw-gate-verdict-hardening: the Python half of the queue-integrity
guarantees and the three stateless doctor shape criteria (AC-021, AC-023).

IN-3 rebuilt `.agenticdoc/_workers.parallel` as 252 non-terminal rows in one
second because (a) every Python writer re-serialized the whole file from the
parsed view, silently deleting rows no parser could read (amplifier F4), and
(b) nothing on the read-only doctor surface could see the shape (F5). These
tests pin the fixes:

* `parse_workers_queue` counts rows and unparsable lines separately, so a row
  can never disappear without the count moving;
* `update_status`, `archive_stale_entries` and `upsert_worker_row` rewrite only
  the lines they own and keep every other slot verbatim;
* `_workers.acked` is a fail-safe signal (unreadable rows are "no information");
* doctor reports `queue-rows-unparsable`, `queue-burst-shape` and
  `run-ledger-conflict` from a pure read (no snapshot file is created).

Run: cd packages/multi-workers && python -X utf8 -m pytest test_worker_queue_python_integrity.py -q
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw_common

_MACHINE_ENV = "MW_AUTOPILOT_FILE"


@pytest.fixture(autouse=True)
def _isolate_machine_layer(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    """Keep the machine config layer out of the way (missing file = empty
    layer, never a fallback to the real HOME)."""
    monkeypatch.setenv(_MACHINE_ENV, str(tmp_path / "no-machine-layer.json"))


def _queue_path(root: pathlib.Path) -> pathlib.Path:
    path = root / ".agenticdoc" / "_workers.parallel"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _row(root: pathlib.Path, key: str, status: str = "pending", **overrides: str) -> dict[str, str]:
    """A 9-column row whose task.md really exists (so the stale archiver keeps
    it)."""
    task_dir = root / ".agenticdoc" / "k" / "workers" / key
    task_dir.mkdir(parents=True, exist_ok=True)
    task_md = task_dir / "task.md"
    task_md.write_text("type: coding\nwork\n", encoding="utf-8")
    row = {
        "task_key": key,
        "status": status,
        "cli": "pi",
        "provider": "claude",
        "task_path": str(task_md),
        "dispatched_at": "2026-10-10T02:50:05+00:00",
        "updated_at": "2026-10-10T02:50:05+00:00",
        "model": "",
        "origin": "manual",
    }
    row.update(overrides)
    return row


def _write(root: pathlib.Path, lines: list[str]) -> pathlib.Path:
    path = _queue_path(root)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


def _serialize(row: dict[str, str]) -> str:
    return mw_common.serialize_entry(row)


def _write_config(root: pathlib.Path, **overrides: object) -> None:
    path = root / ".agenticdoc" / "_autopilot" / "config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(overrides, indent=2) + "\n", encoding="utf-8")


def _issues(root: pathlib.Path) -> list[str]:
    report = mw_common.doctor_report(root, fix=False, config=mw_common.load_providers(None))
    return report["summary"]["issues"]


# ── read side: nothing disappears without the count moving ───────────────────


def test_parse_workers_queue_counts_rows_and_unparsable_slots(tmp_path: pathlib.Path) -> None:
    """7 / 8 / 9 column rows all parse; every other non-comment line lands in
    `unparsable` with its line number and column count (VC-024)."""
    task_md = _row(tmp_path, "t7")["task_path"]
    stamp = "2026-10-10T02:50:05+00:00"
    seven = f"t7 | pending | pi | claude | {task_md} | {stamp} | {stamp}"
    eight = f"t8 | pending | pi | claude | {task_md} | {stamp} | {stamp} | m1"
    nine = f"t9 | pending | pi | claude | {task_md} | {stamp} | {stamp} | m1 | manual"
    path = _write(
        tmp_path,
        ["# mw-queue:v2", seven, eight, nine, "junk with no columns", "a | b | c", "# a comment"],
    )

    queue = mw_common.parse_workers_queue(path)

    assert [row["task_key"] for row in queue["rows"]] == ["t7", "t8", "t9"]
    assert [row["origin"] for row in queue["rows"]] == ["", "", "manual"]
    assert [row["model"] for row in queue["rows"]] == ["", "m1", "m1"]
    assert queue["version"] == 2
    assert [entry["line"] for entry in queue["unparsable"]] == [5, 6]
    assert [entry["cols"] for entry in queue["unparsable"]] == [1, 3]
    # Row count + unparsable count == non-comment lines: no silent third path.
    non_comment = [
        line for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert len(queue["rows"]) + len(queue["unparsable"]) == len(non_comment)


def test_headerless_file_is_version_one(tmp_path: pathlib.Path) -> None:
    path = _write(tmp_path, [_serialize(_row(tmp_path, "t1"))])

    assert mw_common.parse_workers_queue(path)["version"] == 1


# ── write side: slot preservation (the IN-3 amplifier F4) ────────────────────


def test_update_status_preserves_unparsable_rows(tmp_path: pathlib.Path) -> None:
    path = _write(
        tmp_path,
        ["# mw-queue:v2", _serialize(_row(tmp_path, "t1")), "unreadable | row", _serialize(_row(tmp_path, "t2"))],
    )

    mw_common.update_status(tmp_path, "t1", "done")

    text = path.read_text(encoding="utf-8")
    assert "unreadable | row" in text  # the old writer deleted this line
    assert "# mw-queue:v2" in text
    queue = mw_common.parse_workers_queue(path)
    assert [(row["task_key"], row["status"]) for row in queue["rows"]] == [("t1", "done"), ("t2", "pending")]
    assert len(queue["unparsable"]) == 1


def test_update_status_leaves_the_file_untouched_when_no_row_matches(tmp_path: pathlib.Path) -> None:
    path = _write(tmp_path, [_serialize(_row(tmp_path, "t1")), "unreadable | row"])
    before = path.read_bytes()

    mw_common.update_status(tmp_path, "not-in-this-queue", "done")

    assert path.read_bytes() == before


def test_archive_stale_entries_preserves_unparsable_rows(tmp_path: pathlib.Path) -> None:
    gone = _row(tmp_path, "gone")
    pathlib.Path(gone["task_path"]).unlink()  # task.md missing -> stale
    path = _write(
        tmp_path,
        ["unreadable | row", _serialize(gone), _serialize(_row(tmp_path, "alive"))],
    )

    archived = mw_common.archive_stale_entries(tmp_path)

    assert archived == ["gone"]
    text = path.read_text(encoding="utf-8")
    assert "unreadable | row" in text
    assert [row["task_key"] for row in mw_common.parse_workers_queue(path)["rows"]] == ["alive"]
    stale_text = (tmp_path / ".agenticdoc" / "_workers.stale.parallel").read_text(encoding="utf-8")
    assert "gone" in stale_text


def test_upsert_worker_row_replaces_in_slot_and_appends(tmp_path: pathlib.Path) -> None:
    path = _write(tmp_path, [_serialize(_row(tmp_path, "t1")), "unreadable | row"])

    mw_common.upsert_worker_row(path, _row(tmp_path, "t1", status="running"))
    mw_common.upsert_worker_row(path, _row(tmp_path, "t2"))

    queue = mw_common.parse_workers_queue(path)
    assert [(row["task_key"], row["status"]) for row in queue["rows"]] == [
        ("t1", "running"),
        ("t2", "pending"),
    ]
    assert "unreadable | row" in path.read_text(encoding="utf-8")


# ── ack sidecar: fail-safe, never a skip-everything switch (VC-031) ──────────


def test_read_acked_skips_garbage_and_keeps_good_rows(tmp_path: pathlib.Path) -> None:
    (tmp_path / ".agenticdoc").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".agenticdoc" / "_workers.acked").write_text(
        "t1 | 2026-10-10T02:00:00+00:00\nno-separator\n | 2026-10-10T02:00:00+00:00\nt2 | \n# comment\n",
        encoding="utf-8",
    )

    assert mw_common.read_acked(tmp_path) == {"t1": "2026-10-10T02:00:00+00:00"}


def test_read_acked_missing_file_is_no_information(tmp_path: pathlib.Path) -> None:
    assert mw_common.read_acked(tmp_path) == {}


# ── doctor: three stateless shape criteria (AC-021 / F36) ────────────────────


def test_doctor_flags_unparsable_rows(tmp_path: pathlib.Path) -> None:
    _write(tmp_path, [_serialize(_row(tmp_path, "t1")), "unreadable | row"])

    issues = _issues(tmp_path)

    assert any(issue.startswith("queue-rows-unparsable") for issue in issues), issues
    report = mw_common.doctor_report(tmp_path, fix=False, config=mw_common.load_providers(None))
    assert report["queue"]["unparsable_count"] == 1
    assert "1 unparsable" in mw_common.format_doctor_text(report)


def test_doctor_burst_shape_flags_the_in3_fingerprint(tmp_path: pathlib.Path) -> None:
    path = _write(tmp_path, [_serialize(_row(tmp_path, f"t{i:03d}")) for i in range(252)])

    issues = _issues(tmp_path)

    assert any(issue.startswith("queue-burst-shape") for issue in issues), issues
    assert path.exists()  # read-only: the report never rewrites the queue


def test_doctor_burst_shape_needs_size_and_ratio(tmp_path: pathlib.Path) -> None:
    # Big queue, but mostly terminal: not the IN-3 shape.
    rows = [_serialize(_row(tmp_path, f"d{i:03d}", status="done")) for i in range(60)]
    rows += [_serialize(_row(tmp_path, f"p{i:03d}")) for i in range(2)]
    _write(tmp_path, rows)
    assert not [i for i in _issues(tmp_path) if i.startswith("queue-burst-shape")]

    # All non-terminal but below the configured threshold: also not flagged.
    _write(tmp_path, [_serialize(_row(tmp_path, f"t{i:03d}")) for i in range(20)])
    assert not [i for i in _issues(tmp_path) if i.startswith("queue-burst-shape")]

    # The threshold is read from the config, not hardcoded.
    _write_config(tmp_path, queue_alarm_delta=10)
    assert [i for i in _issues(tmp_path) if i.startswith("queue-burst-shape")]


def test_doctor_run_ledger_conflict(tmp_path: pathlib.Path) -> None:
    row = _row(tmp_path, "t1", status="pending")
    (pathlib.Path(row["task_path"]).parent / "run.json").write_text(
        json.dumps({"task_key": "t1", "status": "done"}) + "\n", encoding="utf-8"
    )
    _write(tmp_path, [_serialize(row)])

    issues = _issues(tmp_path)

    assert any(issue.startswith("run-ledger-conflict") for issue in issues), issues


def test_doctor_text_line_keeps_a_healthy_queue_byte_identical(tmp_path: pathlib.Path) -> None:
    _write(tmp_path, [_serialize(_row(tmp_path, "t1"))])

    report = mw_common.doctor_report(tmp_path, fix=False, config=mw_common.load_providers(None))

    # Zero perturbation (P-018): a readable queue keeps the historical text line.
    assert "queue: 1 non-terminal task(s), 0 stale, 0 archived\n" in mw_common.format_doctor_text(report)
