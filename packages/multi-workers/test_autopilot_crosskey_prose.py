"""test_autopilot_crosskey_prose.py — off-gate prose authorization is
UNAUTHORIZED (T-24 / VC-048, AC-031 / Q-VC-048, G11).

The machine carrier for a cross-key repair authorization is an ANSWERED
``xkey-authorize`` gate (``conductor._xkey_ensure_gate`` writes the request id
into ``context_refs``). The path seen in production is a hand-written
``decision:`` line inside ``_autopilot/evidence/cross-key-repair-request-*.md``
(design D1 §6.2 P4, FM 20260925-n1). This file locks the doctor scan that
flags prose-only authorizations and keeps them fail-closed ("treated as
unauthorized").

Fixture shapes come from the real FM file, never invented:

* ``request_id     : XKEY-2026-09-25-01``
* ``status         : authorized-R1（2026-09-26T03:04:05+00:00 经人工批准）``
* the file's own template line ``…追加一行，`decision: <approved|rejected> by
  <who> at <ts>（备注）`。`` — a decoy that must never match
* the appended answer ``**decision: approved (R1) by user-via-pm-window at
  2026-09-26T03:04:05+00:00**``
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw  # noqa: E402
import mw_common  # noqa: E402

# The real FM file, trimmed to the fields the scan judges (identity + the
# template decoy + the appended hand-written decision). Backticks around the
# template line are part of the shape: only a line STARTING with `decision:`
# is an answer.
CROSS_KEY_REQUEST = """# 跨 key 修复申请：N-1 顶层命令组守卫

```
request_id     : XKEY-2026-09-25-01
created_by     : PM 窗口（user-via-pm-window）
created_at     : 2026-09-25T02:20Z
status         : authorized-R1（2026-09-26T03:04:05+00:00 经人工批准）
```

## 5. 追认入口

在本文末追加一行：`decision: <approved|rejected> by <who> at <ts>（备注）`。
未追认前本窗口不动任何文件。

---

**decision: approved (R1) by user-via-pm-window at 2026-09-26T03:04:05+00:00**
"""

# Only the template line (backticked, placeholders) — no answer yet. This is
# the FM `cross-key-repair-request-20260926-h1.md` shape: pending, not an
# authorization, and it must NOT be reported.
TEMPLATE_ONLY_REQUEST = """# 跨 key 修复申请：pending

```
request_id     : XKEY-2026-09-26-01
status         : pending-user-decision
```

在本文末追加一行：`decision: <approved|rejected> by <who> at <ts>（备注）`。
"""


@pytest.fixture(autouse=True)
def _isolate_machine_layer(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    """No real ~/.agents/autopilot-defaults.json may leak into these cases."""
    monkeypatch.setenv("MW_AUTOPILOT_FILE", str(tmp_path / "no-machine-layer.json"))
    monkeypatch.delenv("MW_AUTOPILOT_HOME", raising=False)


def _iso_ago(hours: float) -> str:
    moment = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
    return moment.isoformat(timespec="seconds")


def _gates_dir(project: pathlib.Path) -> pathlib.Path:
    return project / ".agenticdoc" / "_autopilot" / "gates"


def _evidence_dir(project: pathlib.Path) -> pathlib.Path:
    return project / ".agenticdoc" / "_autopilot" / "evidence"


def _gate_text(
    gate_id: str,
    *,
    kind: str = "xkey-authorize",
    status: str = "pending",
    refs: tuple[str, ...] = (),
    key: str = "owner-key",
    created_at: str | None = None,
    extra: dict[str, str] | None = None,
) -> str:
    """A parser-valid schema-2 gate; answered statuses carry answered_at/by."""
    if created_at is None:
        created_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    lines = [
        "---",
        f"id: {gate_id}",
        "gate_schema: 2",
        f"kind: {kind}",
        "stage:",
        f"key: {key}",
        f"created_at: {created_at}",
        "created_by: conductor",
        f"question: authorize cross-key repair for {gate_id}",
    ]
    if refs:
        lines.append("context_refs:")
        lines.extend(f"  - {ref}" for ref in refs)
    else:
        lines.append("context_refs: []")
    lines.append(f"status: {status}")
    fields: dict[str, str] = {}
    if status != "pending":
        fields["answered_at"] = _iso_ago(1)
        fields["answered_by"] = "human"
    else:
        fields["answered_at"] = ""
        fields["answered_by"] = ""
    fields.update(extra or {})
    for name, value in fields.items():
        lines.append(f"{name}: {value}" if value else f"{name}:")
    lines += ["---", "", f"# Gate {gate_id}", ""]
    return "\n".join(lines)


def _write_gate(project: pathlib.Path, gate_id: str, text: str) -> pathlib.Path:
    gdir = _gates_dir(project)
    gdir.mkdir(parents=True, exist_ok=True)
    path = gdir / f"{gate_id}.md"
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _write_request(project: pathlib.Path, name: str, text: str) -> pathlib.Path:
    edir = _evidence_dir(project)
    edir.mkdir(parents=True, exist_ok=True)
    path = edir / name
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _snapshot(root: pathlib.Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))


def _make_service_running(project: pathlib.Path) -> None:
    """Remove the 'mw service not running' issue so cross-key alerts are the
    only variable under test."""
    (project / ".mw").mkdir(parents=True, exist_ok=True)
    mw_common.pid_file(project).write_text(str(os.getpid()), encoding="utf-8")


def _report(project: pathlib.Path) -> dict:
    return mw_common.doctor_report(project, fix=False, config=mw_common.load_providers(None))


def _doctor_args(project: pathlib.Path, as_json: bool = False) -> argparse.Namespace:
    return argparse.Namespace(
        project=str(project), providers=None, fix=False, json=as_json, stale_after=90,
    )


def _gates_args(project: pathlib.Path, as_json: bool = False) -> argparse.Namespace:
    return argparse.Namespace(
        project=str(project), autopilot_action="gates", as_json=as_json,
    )


# ── positive: hand-written decision line == prose-only == unauthorized ───────


def test_prose_only_decision_is_reported_as_unauthorized(tmp_path: pathlib.Path, capsys) -> None:
    _make_service_running(tmp_path)
    _write_request(tmp_path, "cross-key-repair-request-20260925-n1.md", CROSS_KEY_REQUEST)

    report = _report(tmp_path)
    section = report["gates"]["crosskey_prose"]
    assert section["exists"] is True
    assert [r["authorization"] for r in section["requests"]] == ["prose"]
    entry = section["requests"][0]
    # Identity comes from the real shape, not an invented field.
    assert entry["request_id"] == "XKEY-2026-09-25-01"
    assert entry["status"].startswith("authorized-R1")
    assert entry["prose_decision"] == {
        "verdict": "approved",
        "by": "user-via-pm-window",
        "at": "2026-09-26T03:04:05+00:00",
        "line": "**decision: approved (R1) by user-via-pm-window at 2026-09-26T03:04:05+00:00**",
    }
    # Fail-closed: prose is NOT an authorization carrier.
    assert entry["machine_authorized"] is False
    assert entry["carrier_gate"] is None
    assert entry["treated_as_authorized"] is False
    assert section["prose_only"] == 1
    assert section["machine_authorized"] == 0
    assert section["fail_closed"] is True

    assert report["summary"]["healthy"] is False
    issues = report["summary"]["issues"]
    match = [i for i in issues if "authorized by prose only" in i]
    assert len(match) == 1
    assert "XKEY-2026-09-25-01" in match[0]
    assert "treated as unauthorized (VC-048)" in match[0]
    # Visibility: the doctor text line and the exit code both flip.
    text = mw_common.format_doctor_text(report)
    assert "gates:" in text and "1 prose-only cross-key" in text
    rc = mw.cmd_doctor(_doctor_args(tmp_path))
    capsys.readouterr()
    assert rc == 1


def test_default_verdict_lowercased_and_asterisks_stripped(tmp_path: pathlib.Path) -> None:
    """The detector normalizes the verdict token and tolerates `**…**`."""
    assert mw_common._crosskey_prose_decision(
        "**decision: Approved by user-via-pm-window at 2026-09-26T03:04:05+00:00**"
    ) == {
        "verdict": "approved",
        "by": "user-via-pm-window",
        "at": "2026-09-26T03:04:05+00:00",
        "line": "**decision: Approved by user-via-pm-window at 2026-09-26T03:04:05+00:00**",
    }


def test_template_placeholder_decision_is_not_an_authorization(tmp_path: pathlib.Path) -> None:
    """Anti-false-positive (FM 20260926-h1 shape): the file's own template line
    uses placeholders inside backticks and is NOT appended prose consent."""
    _make_service_running(tmp_path)
    _write_request(tmp_path, "cross-key-repair-request-20260926-h1.md", TEMPLATE_ONLY_REQUEST)

    report = _report(tmp_path)
    section = report["gates"]["crosskey_prose"]
    assert section["requests"][0]["authorization"] == "none"
    assert section["requests"][0]["prose_decision"] is None
    assert section["prose_only"] == 0
    assert report["summary"]["healthy"] is True
    assert not any("prose only" in i for i in report["summary"]["issues"])


# ── negative 1: an ANSWERED xkey-authorize gate is the machine carrier ───────


def test_answered_xkey_gate_is_the_machine_carrier(
    tmp_path: pathlib.Path, capsys
) -> None:
    _make_service_running(tmp_path)
    _write_request(tmp_path, "cross-key-repair-request-20260925-n1.md", CROSS_KEY_REQUEST)
    _write_gate(
        tmp_path, "gate-0001",
        _gate_text(
            "gate-0001", status="approved",
            refs=("XKEY-2026-09-25-01", ".agenticdoc/_autopilot/xkey/XKEY-2026-09-25-01/ticket.md"),
            extra={"expires_at": _iso_ago(-24), "default_action": "escalate-to-human"},
        ),
    )

    report = _report(tmp_path)
    section = report["gates"]["crosskey_prose"]
    assert section["machine_authorized"] == 1
    assert section["prose_only"] == 0
    entry = section["requests"][0]
    assert entry["machine_authorized"] is True
    assert entry["carrier_gate"] == "gate-0001"
    assert entry["authorization"] == "machine"
    assert entry["treated_as_authorized"] is True  # the gate is the carrier
    assert not any("prose only" in i for i in report["summary"]["issues"])
    assert report["summary"]["healthy"] is True
    with capsys.disabled():
        print(
            "[CONTROL] answered-carrier: "
            f"machine_authorized={section['machine_authorized']} "
            f"prose_only={section['prose_only']} "
            f"carrier_gate={entry['carrier_gate']} healthy={report['summary']['healthy']}"
        )


def test_pending_xkey_gate_does_not_authorize(tmp_path: pathlib.Path) -> None:
    """Fail-closed: only the ANSWER authorizes. A pending gate leaves the
    prose-only request unauthorized."""
    _make_service_running(tmp_path)
    _write_request(tmp_path, "cross-key-repair-request-20260925-n1.md", CROSS_KEY_REQUEST)
    _write_gate(
        tmp_path, "gate-0001",
        _gate_text(
            "gate-0001", status="pending", refs=("XKEY-2026-09-25-01",),
            extra={"expires_at": _iso_ago(-24), "default_action": "escalate-to-human"},
        ),
    )

    report = _report(tmp_path)
    section = report["gates"]["crosskey_prose"]
    assert section["machine_authorized"] == 0
    assert section["prose_only"] == 1
    assert section["requests"][0]["treated_as_authorized"] is False
    assert any("prose only" in i for i in report["summary"]["issues"])


# ── negative 2: no request files at all ──────────────────────────────────────


def test_no_request_files_no_crosskey_issue(tmp_path: pathlib.Path) -> None:
    _make_service_running(tmp_path)
    report = _report(tmp_path)
    section = report["gates"]["crosskey_prose"]
    assert section["exists"] is False
    assert section["requests"] == []
    assert section["prose_only"] == 0
    assert section["machine_authorized"] == 0
    assert report["summary"]["healthy"] is True
    assert not any("cross-key repair request" in i for i in report["summary"]["issues"])
    assert "gates:" not in mw_common.format_doctor_text(report)


def test_unrelated_evidence_file_is_ignored(tmp_path: pathlib.Path) -> None:
    """Only `cross-key-repair-request-*.md` is in scope (no broad globbing)."""
    _make_service_marker = _make_service_running
    _make_service_marker(tmp_path)
    _write_request(tmp_path, "xkey-n1-repair-20260926.txt", "decision: approved by nobody\n")
    report = _report(tmp_path)
    section = report["gates"]["crosskey_prose"]
    assert section["exists"] is True
    assert section["requests"] == []
    assert report["summary"]["healthy"] is True


# ── read-only discipline + visibility in the gates view ──────────────────────


def test_crosskey_scan_is_read_only(tmp_path: pathlib.Path) -> None:
    _write_request(tmp_path, "cross-key-repair-request-20260925-n1.md", CROSS_KEY_REQUEST)
    _write_gate(tmp_path, "gate-0001", _gate_text("gate-0001"))
    before = _snapshot(tmp_path)
    _report(tmp_path)
    mw_common.format_doctor_text(_report(tmp_path))
    assert _snapshot(tmp_path) == before
    # No gate is created or answered by the scan either.
    assert sorted(p.name for p in _gates_dir(tmp_path).iterdir()) == ["gate-0001.md"]


def test_gates_cli_surfaces_prose_only_request(tmp_path: pathlib.Path, capsys) -> None:
    _write_request(tmp_path, "cross-key-repair-request-20260925-n1.md", CROSS_KEY_REQUEST)
    assert mw.cmd_autopilot(_gates_args(tmp_path, as_json=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["crosskey_prose"]["prose_only"] == 1
    assert payload["crosskey_prose"]["fail_closed"] is True
    assert payload["crosskey_prose"]["requests"][0]["authorization"] == "prose"

    assert mw.cmd_autopilot(_gates_args(tmp_path)) == 0
    out = capsys.readouterr().out
    assert "authorized by prose only" in out
    assert "treated as unauthorized (VC-048)" in out


# ── non-vacuous counterfactuals (≥2, with raw output) ────────────────────────


def test_control_remove_prose_detector_turns_positive_green(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """Control 1: with the prose predicate removed the positive fixture goes
    green, proving THIS predicate (not some other gate alert) is what fires."""
    _make_service_running(tmp_path)
    _write_request(tmp_path, "cross-key-repair-request-20260925-n1.md", CROSS_KEY_REQUEST)
    before = _report(tmp_path)
    monkeypatch.setattr(mw_common, "_crosskey_prose_decision", lambda text: None)
    after = _report(tmp_path)
    with capsys.disabled():
        print(
            "[CONTROL] prose-detector=on: "
            f"prose_only={before['gates']['crosskey_prose']['prose_only']} "
            f"issues={[i for i in before['summary']['issues'] if 'prose only' in i]!r} "
            f"healthy={before['summary']['healthy']}"
        )
        print(
            "[CONTROL] prose-detector=off: "
            f"prose_only={after['gates']['crosskey_prose']['prose_only']} "
            f"issues={[i for i in after['summary']['issues'] if 'prose only' in i]!r} "
            f"healthy={after['summary']['healthy']}"
        )
    assert before["gates"]["crosskey_prose"]["prose_only"] == 1
    assert before["summary"]["healthy"] is False
    assert after["gates"]["crosskey_prose"]["prose_only"] == 0
    assert after["summary"]["healthy"] is True


def test_control_linking_an_answered_gate_turns_positive_green(tmp_path: pathlib.Path) -> None:
    """Control 2 = negative 1, asserted here as the explicit counterfactual:
    the SAME prose fixture stops being reported once an answered
    `xkey-authorize` gate carries the request id."""
    _write_request(tmp_path, "cross-key-repair-request-20260925-n1.md", CROSS_KEY_REQUEST)
    without = _report(tmp_path)
    _write_gate(
        tmp_path, "gate-0001",
        _gate_text(
            "gate-0001", status="approved", refs=("XKEY-2026-09-25-01",),
            extra={"expires_at": _iso_ago(-24), "default_action": "escalate-to-human"},
        ),
    )
    with_gate = _report(tmp_path)
    print(
        "[CONTROL] link-answered-gate: "
        f"before prose_only={without['gates']['crosskey_prose']['prose_only']} "
        f"after prose_only={with_gate['gates']['crosskey_prose']['prose_only']} "
        f"after machine_authorized={with_gate['gates']['crosskey_prose']['machine_authorized']} "
        f"after carrier={with_gate['gates']['crosskey_prose']['requests'][0]['carrier_gate']}"
    )
    assert without["gates"]["crosskey_prose"]["prose_only"] == 1
    assert with_gate["gates"]["crosskey_prose"]["prose_only"] == 0
    assert with_gate["gates"]["crosskey_prose"]["machine_authorized"] == 1


def test_verified_metrics_are_measured(tmp_path: pathlib.Path) -> None:
    """P-023: the [VERIFY] values are computed from a two-request fixture
    (one prose-only, one machine-carried), never hardcoded literals."""
    _make_service_running(tmp_path)
    _write_request(tmp_path, "cross-key-repair-request-20260925-n1.md", CROSS_KEY_REQUEST)
    _write_request(
        tmp_path, "cross-key-repair-request-20260925-n2.md",
        CROSS_KEY_REQUEST.replace("XKEY-2026-09-25-01", "XKEY-2026-09-25-02"),
    )
    _write_gate(
        tmp_path, "gate-0001",
        _gate_text(
            "gate-0001", status="approved", refs=("XKEY-2026-09-25-02",),
            extra={"expires_at": _iso_ago(-24), "default_action": "escalate-to-human"},
        ),
    )
    report = _report(tmp_path)
    section = report["gates"]["crosskey_prose"]
    requests = len(section["requests"])
    machine_authorized = section["machine_authorized"]
    prose_only = section["prose_only"]
    issues = len([i for i in report["summary"]["issues"] if "authorized by prose only" in i])
    fail_closed = all(
        not r["treated_as_authorized"] for r in section["requests"] if r["authorization"] == "prose"
    )
    print(
        f"[VERIFY] T-24 crosskey-prose: requests={requests} "
        f"machine_authorized={machine_authorized} prose_only={prose_only} "
        f"issues={issues} fail_closed={str(fail_closed).lower()}"
    )
    assert (requests, machine_authorized, prose_only, issues, fail_closed) == (2, 1, 1, 1, True)
    assert section["fail_closed"] is True
