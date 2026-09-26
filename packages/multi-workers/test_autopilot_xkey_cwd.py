"""test_autopilot_xkey_cwd.py — T-06 conductor workspace-root anchoring
(AC-013 / VC-013).

The xkey channel has two roots. The *coordination* root is the control/project
root (ledger, tickets, evidence, runs, timeline) and never moves; the
*workspace* root is where the verified artifacts and the worker cwd live
(partition -> partition root, dual -> game root, single/legacy -> control
root). This suite pins:

* ``xkey_verify_cwd`` resolution (``""`` = auto = ``workspace_root``;
  ``control``/``partition``/``parent``/``<root name>``; unknown selector ->
  ``TargetConfigError("invalid-config")``).
* the S4 verify cwd is the resolved workspace root, not ``project_root``.
* the same-family re-anchor of the five workspace-relative anchors: the frozen
  block is located in the partition root, the zero-residue sha is the
  partition file's, the proposal prompt points at the partition file, apply
  writes the partition file and the S3 existence check reads it. A decoy with
  the same relative path under the control root proves no wrong file is hit.
* the machine layer's ``xkey_verify_cmd`` reaches ``xkey.run_verification``
  (captured argv), not just ``load_effective``'s return value.
* ``xkey_repair=false`` -> the whole anchoring surface stays unreachable.
"""

import hashlib
import json
import pathlib
import re
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import mw_common  # noqa: E402
from autopilot import conductor, config, effective_config, timeline, xkey  # noqa: E402


def _verify(tag: str, **kv) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()))


# ── partition fixture (shape mirroring test_partition_dispatch.py) ──────────

_PARTITION_YML = """\
active: partition
partition:
  parent: '{parent}'
  partition: '{partition}'
  roots:
    sdk: '{sdk}'
  toolchain:
    build: 'make -C {partition} SDK={sdk}'
"""

_ROADMAP = (
    "# Roadmap\n"
    "> generated_at: 2026-09-26T00:00:00+00:00\n"
    "> goal_mtime: 1\n"
    "\n"
    "## Stage 1: work\n"
    "> goal: deliver\n"
    "> status: running\n"
)


def _write_yml(control: pathlib.Path, text: str) -> None:
    path = mw_common.target_yml_path(control)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _partition_fixture(
    base: pathlib.Path, *, partition: pathlib.Path | None = None
) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path, pathlib.Path]:
    """control != partition != parent (siblings, none nested)."""
    control = base / "control"
    parent = base / "parent"
    shard = partition if partition is not None else base / "shard"
    sdk = base / "sdk"
    for directory in (control, parent, shard, sdk):
        directory.mkdir(parents=True, exist_ok=True)
    _write_yml(
        control,
        _PARTITION_YML.format(parent=parent, partition=shard, sdk=sdk),
    )
    return control, parent, shard, sdk


def _work_project(control: pathlib.Path, keys: tuple[str, ...], *, statuses: str) -> None:
    autopilot = control / ".agenticdoc" / "_autopilot"
    autopilot.mkdir(parents=True, exist_ok=True)
    (control / ".agenticdoc" / "goal.md").write_text("# Goal\n\nShip.\n", encoding="utf-8")
    rows = "\n".join(f"| {key} | worker | - |" for key in keys)
    (autopilot / "_roadmap.md").write_text(
        _ROADMAP
        + f"> key-status: {statuses}\n"
        + "### Keys\n"
        + "| key | role | depends_on |\n"
        + "|-----|------|-----------|\n"
        + rows
        + "\n",
        encoding="utf-8",
    )


# ── synthetic frozen-constant project (same shape as test_autopilot_e2e) ────

_TEST_REL = "tests/test_frozen.py"
_TEST_ID = "test_groups_unchanged"
_BLOCK_12 = (
    'GROUPS_FROZEN = ("agent", "analyze", "branch", "config", "gate", "gui", "init",\n'
    '                 "install-hooks", "mcp", "mr", "project", "validate")\n'
)
_BLOCK_13 = (
    'GROUPS_FROZEN = ("agent", "analyze", "branch", "config", "gate", "gui", "init",\n'
    '                 "install-hooks", "mcp", "mr", "project", "runs", "validate")\n'
)
_MACHINE_LINE = (
    "[VERIFY] XKEY-T06: "
    "cross_key_test=tests/test_frozen.py::test_groups_unchanged "
    "rc=1 cli_groups=13 frozen_groups=12 owner=k-owner "
    "handoff=registered not_fixed_by_this_key=True"
)
_SOURCE = (
    _BLOCK_12
    + "\n"
    + "def _measured_groups():\n"
    + '    return ("agent", "analyze", "branch", "config", "gate", "gui", "init",\n'
    + '            "install-hooks", "mcp", "mr", "project", "runs", "validate")\n'
    + "\n"
    + "\n"
    + "def test_groups_unchanged():\n"
    + "    measured = _measured_groups()\n"
    + '    print(f"[COUNT] cli_groups={len(measured)} groups={measured}")\n'
    + '    assert tuple(measured) == GROUPS_FROZEN, f"groups changed: {measured}"\n'
)
_DECOY = b"# control-root decoy: same relative path, must never be touched\n"


def _plant_below(control: pathlib.Path, source_key: str, registration: dict) -> None:
    key_dir = control / ".agenticdoc" / source_key
    key_dir.mkdir(parents=True, exist_ok=True)
    (key_dir / "l3-verdict-provenance.json").write_text(
        json.dumps(
            [{
                "raw_verdict": "below",
                "verdict": "below",
                "round": 1,
                "fail_line": _MACHINE_LINE,
                "deciding_source": f"{source_key}/workers/l3-a1/output.md",
                "registration": registration,
            }],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _write_proposal(
    control: pathlib.Path,
    request_id: str,
    file: str,
    line_range: list[int],
    old_sha: str,
    new_text: str,
) -> pathlib.Path:
    directory = xkey.evidence_dir(str(control), request_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "proposal.md"
    path.write_text(
        "---\n"
        f"file: {file}\n"
        f"line_range: [{line_range[0]}, {line_range[1]}]\n"
        f"old_block_sha256: {old_sha}\n"
        "reason: T-06 partition anchoring replay\n"
        "---\n"
        "\n"
        "```python\n"
        f"{new_text}"
        "```\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _pending_gate(control: pathlib.Path, kind: str) -> pathlib.Path | None:
    for gate in conductor.gates.enumerate(conductor.gates_dir(control)):
        if gate.kind == kind and gate.status == "pending":
            return gate.path
    return None


def _answer_gate(gate_path: pathlib.Path, decision: str, note: str) -> None:
    text = gate_path.read_text(encoding="utf-8")

    def sub(field: str, value: str) -> None:
        nonlocal text
        text, count = re.subn(
            rf"^{field}:.*$", f"{field}: {value}", text, count=1, flags=re.M
        )
        assert count == 1, f"gate field {field} not found in {gate_path}"

    sub("status", decision)
    sub("answered_at", timeline._iso_now())
    sub("answered_by", "t06-human")
    sub("note", note)
    gate_path.write_text(text, encoding="utf-8", newline="\n")


def _state(control: pathlib.Path) -> conductor.ConductorState:
    return conductor.ConductorState(
        timeline.Timeline(timeline.timeline_path(control)),
        conductor.goal_mtime_ns(control),
    )


def _config(
    control: pathlib.Path, verify_cmd: list[str], *, cwd: str = "", repair: bool = True
) -> dict:
    cfg = config.default_config()
    cfg["enabled"] = True
    cfg["xkey_repair"] = repair
    cfg["xkey_verify_cmd"] = list(verify_cmd)
    cfg["xkey_verify_timeout_s"] = 300
    cfg["xkey_verify_cwd"] = cwd
    config.save_config(control, cfg)
    return cfg


def _capture_verify(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Spy on the real ``xkey.run_verification``; records cmd + cwd."""
    captured: dict = {}
    real = xkey.run_verification

    def spy(cmd, cwd, run_dir, timeout):  # noqa: ANN001, ANN202
        captured["cmd"] = [str(part) for part in cmd]
        captured["cwd"] = str(cwd)
        captured["run_dir"] = str(run_dir)
        return real(cmd, cwd=cwd, run_dir=run_dir, timeout=timeout)

    monkeypatch.setattr(xkey, "run_verification", spy)
    return captured


def _drive_to_ticket(
    control: pathlib.Path, cfg: dict, status_of: dict
) -> tuple[list[dict], str, dict, conductor.ConductorState, str, pathlib.Path]:
    """aggregate -> approve -> proposal on disk; returns the ticket context."""
    registration = xkey.parse_registration(_MACHINE_LINE)
    assert registration is not None
    _plant_below(control, "k-source", registration)
    st = _state(control)
    conductor._xkey_aggregate(control, st, status_of, cfg)
    rows = xkey.ledger_load(str(control))["rows"]
    assert len(rows) == 1, rows
    request_id = rows[0]["request_id"]
    gate = _pending_gate(control, "xkey-authorize")
    assert gate is not None, "xkey-authorize gate not raised"
    _answer_gate(gate, "approved", "T-06 approval")
    conductor._consume_answered_gates(control, st, cfg)
    ticket = xkey.ticket_load(str(control), request_id)
    assert ticket is not None and ticket["status"] == "approved"
    proposal = _write_proposal(
        control,
        request_id,
        ticket["frozen_block"]["file"],
        ticket["frozen_block"]["line_range"],
        ticket["frozen_block"]["old_block_sha256"],
        _BLOCK_13,
    )
    return rows, request_id, ticket, st, str(ticket["frozen_block"]["file"]), proposal


# ── 1. partition: verify cwd + same-family re-anchor ────────────────────────


def test_partition_verify_cwd_and_family_reanchor(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    control, parent, partition, _sdk = _partition_fixture(tmp_path)
    _work_project(control, ("k-source", "k-owner"), statuses="k-source=running, k-owner=running")

    target = partition / _TEST_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_SOURCE.encode("utf-8"))
    decoy = control / _TEST_REL
    decoy.parent.mkdir(parents=True, exist_ok=True)
    decoy.write_bytes(_DECOY)

    # "{partition}" is deliberate: the ticket and the executed argv must carry
    # the expanded element, not the raw template (a whole argv element, per
    # render_argv's fail-closed contract). The script itself checks a
    # *workspace-relative* path, so its verdict depends on the subprocess cwd:
    # run from the control root it reads the decoy and fails. That is what makes
    # the counter-proof (cwd back to project_root -> this case red) non-vacuous.
    verify_cmd = [
        sys.executable,
        "-c",
        (
            "import pathlib,sys;"
            "p=pathlib.Path('tests/test_frozen.py');"
            "sys.exit(0 if p.is_file() and b'\"runs\"' in p.read_bytes() else 1)"
        ),
        "{partition}",
    ]
    cfg = _config(control, verify_cmd, cwd="")  # "" = auto
    status_of = {"k-source": "done", "k-owner": "done"}

    rows, request_id, ticket, st, file_rel, _proposal = _drive_to_ticket(
        control, cfg, status_of
    )
    expected_root = str(partition.resolve())
    expected_arg = str(partition.resolve())
    frozen = ticket["frozen_block"]

    # (1) frozen block located in the partition root, not the control root
    located = xkey.locate_frozen_block(expected_root, file_rel, _TEST_ID)
    assert located is not None, "frozen block not found in the partition root"
    assert frozen["old_block_sha256"] == located["old_block_sha256"]
    # (2) zero-residue anchor is the partition file's whole-file sha
    assert ticket["target_file_sha256"] == hashlib.sha256(target.read_bytes()).hexdigest()
    assert ticket["target_file_sha256"] != hashlib.sha256(_DECOY).hexdigest()
    # (3) proposal prompt points the worker at the partition file
    prompt = conductor._xkey_proposal_prompt(control, ticket, partition.resolve())
    assert str(partition.resolve() / file_rel) in prompt
    assert str(control.resolve() / file_rel) not in prompt
    # cwd + expanded argv recorded on the ticket
    assert ticket["verification"]["cwd"] == expected_root, ticket["verification"]
    assert ticket["verification"]["argv"] == [*verify_cmd[:-1], expected_arg], ticket["verification"]

    captured = _capture_verify(monkeypatch)
    # (4)(5) apply writes the partition file, S3 reads the partition file
    conductor._xkey_apply_stage(control, st, status_of, cfg)
    ticket = xkey.ticket_load(str(control), request_id)
    assert ticket["status"] == "closed", ticket.get("status")
    row = xkey.ledger_load(str(control))["rows"][0]
    assert row["status"] == "closed"
    # S4 really ran in the partition root with the expanded argv
    assert captured["cmd"] == ticket["verify"]["verify_cmd"]
    assert captured["cwd"] == expected_root, captured
    # the partition file was repaired; the control-root decoy is untouched
    assert b'"runs"' in target.read_bytes()
    assert decoy.read_bytes() == _DECOY
    # coordination root unchanged: evidence lives under the control root
    assert (xkey.evidence_dir(str(control), request_id) / "bundle.json").is_file()
    assert not (partition / ".agenticdoc" / "_autopilot" / "xkey").exists()

    assert rows[0]["file"] == file_rel
    _verify(
        "VC-013", case="partition", cwd=expected_root,
        cwd_is_partition=str(expected_root == str(partition.resolve())),
        anchors="locate+sha+prompt+apply+existence",
        control_decoy_untouched="true", apply_target="partition",
        coordination_root="control", **{"pass": "true"},
    )


# ── 2. unknown selector: fail closed, verification never runs ───────────────


def test_unknown_selector_fails_closed_without_verify(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    control, parent, partition, sdk = _partition_fixture(tmp_path)
    _work_project(control, ("k-source", "k-owner"), statuses="k-source=running, k-owner=running")

    target = partition / _TEST_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_SOURCE.encode("utf-8"))

    verify_cmd = [sys.executable, "-X", "utf8", "-c", "print('1 passed in 0.01s')"]
    cfg_ok = _config(control, verify_cmd, cwd="")
    status_of = {"k-source": "done", "k-owner": "done"}
    _rows, request_id, _ticket, st, _rel, _proposal = _drive_to_ticket(
        control, cfg_ok, status_of
    )

    target_config = mw_common.load_target_config(control)
    with pytest.raises(mw_common.TargetConfigError) as excinfo:
        conductor.resolve_verify_cwd("nope", target_config)
    assert excinfo.value.kind == "invalid-config"
    assert "unknown root selector 'nope'" in str(excinfo.value)
    assert conductor.resolve_verify_cwd("", target_config) == str(partition.resolve())
    assert conductor.resolve_verify_cwd("parent", target_config) == str(parent.resolve())
    assert conductor.resolve_verify_cwd("sdk", target_config) == str(sdk.resolve())

    def no_verify(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        raise AssertionError("verification must not run with an invalid selector")

    monkeypatch.setattr(xkey, "run_verification", no_verify)
    cfg_bad = dict(cfg_ok)
    cfg_bad["xkey_verify_cwd"] = "nope"
    conductor._xkey_apply_stage(control, st, status_of, cfg_bad)

    ticket = xkey.ticket_load(str(control), request_id)
    assert ticket["status"] == "boundary_violation", ticket.get("status")
    detail = ticket["boundary_violation"]["detail"]
    assert "invalid-config" in detail and "nope" in detail, detail
    assert target.read_bytes() == _SOURCE.encode("utf-8"), "no write on fail-closed"
    _verify(
        "VC-013", case="invalid-selector", kind=excinfo.value.kind,
        verify_executed="false", ticket_status=ticket["status"],
        target_untouched="true", **{"pass": "true"},
    )


# ── 3. E2 shape regression (active: partition, control == partition) ────────


def test_e2_shape_partition_defaults(tmp_path: pathlib.Path) -> None:
    control = tmp_path / "control"
    control.mkdir()
    control, parent, partition, sdk = _partition_fixture(tmp_path, partition=control)
    assert partition == control
    target_config = mw_common.load_target_config(control)
    assert target_config["mode"] == "partition"
    assert conductor.resolve_verify_cwd("", target_config) == str(partition.resolve())
    assert conductor.resolve_verify_cwd("partition", target_config) == str(partition.resolve())
    assert conductor.resolve_verify_cwd("parent", target_config) == str(parent.resolve())
    assert conductor.resolve_verify_cwd("sdk", target_config) == str(sdk.resolve())
    _verify(
        "VC-013", case="e2-shape", mode=target_config["mode"],
        auto_cwd=str(partition.resolve()),
        control_eq_partition=str(partition.resolve() == control.resolve()),
        parent_cwd=str(parent.resolve()), **{"pass": "true"},
    )


@pytest.mark.skipif(
    not pathlib.Path(r"H:\git\E2Feature").exists(),
    reason="E2 live workspace not present on this machine",
)
def test_e2_live_anchor(tmp_path: pathlib.Path) -> None:
    """Live E2 anchor (absolute paths): partition=H:\\git\\E2Feature,
    parent=E:\\UEMigrator. Skipped when the workspace is absent."""
    control = tmp_path / "control"
    control.mkdir()
    _write_yml(
        control,
        "active: partition\n"
        "partition:\n"
        f"  parent: '{pathlib.Path(r'E:\\UEMigrator')}'\n"
        f"  partition: '{pathlib.Path(r'H:\\git\\E2Feature')}'\n",
    )
    target_config = mw_common.load_target_config(control)
    assert conductor.resolve_verify_cwd("", target_config) == str(
        pathlib.Path(r"H:\git\E2Feature").resolve()
    )
    assert conductor.resolve_verify_cwd("parent", target_config) == str(
        pathlib.Path(r"E:\UEMigrator").resolve()
    )
    _verify("VC-013", case="e2-live", cwd=r"H:\git\E2Feature", **{"pass": "true"})


# ── 4. machine layer command is what the conductor executes ─────────────────


def test_machine_layer_verify_cmd_is_consumed(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    control = tmp_path / "proj"
    _work_project(control, ("k-source", "k-owner"), statuses="k-source=running, k-owner=running")
    target = control / _TEST_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_SOURCE.encode("utf-8"))

    machine_cmd = [sys.executable, "-X", "utf8", "-c", "print('1 passed in 0.01s')"]
    # Project file deliberately omits xkey_verify_cmd (raw partial write, not
    # save_config which would materialise the key and shadow the machine layer).
    project_path = config.config_path(control)
    project_path.parent.mkdir(parents=True, exist_ok=True)
    project_path.write_text(
        json.dumps(
            {"enabled": True, "xkey_repair": True, "xkey_verify_timeout_s": 300}
        ),
        encoding="utf-8",
    )
    machine_path = tmp_path / "machine.json"
    machine_path.write_text(
        json.dumps({"xkey_verify_cmd": machine_cmd}), encoding="utf-8"
    )
    monkeypatch.setenv("MW_AUTOPILOT_FILE", str(machine_path))

    # Non-vacuous: the project layer alone carries no command (load_config
    # returns exactly the file's keys; the key is absent, not empty).
    assert "xkey_verify_cmd" not in config.cached_load(control)
    assert effective_config.load_effective(control).origins["xkey_verify_cmd"] == "machine"
    cfg = conductor._load_effective_config(control)  # the seam tick/orchestrate use
    assert cfg["xkey_verify_cmd"] == machine_cmd

    status_of = {"k-source": "done", "k-owner": "done"}
    _rows, request_id, ticket, st, _rel, _proposal = _drive_to_ticket(
        control, cfg, status_of
    )
    assert ticket["verification"]["command"] == machine_cmd
    assert ticket["verification"]["argv"] == machine_cmd

    captured = _capture_verify(monkeypatch)
    conductor._xkey_apply_stage(control, st, status_of, cfg)
    ticket = xkey.ticket_load(str(control), request_id)
    assert ticket["status"] == "closed", ticket.get("status")
    assert captured["cmd"] == machine_cmd, captured
    assert captured["cwd"] == str(control.resolve())
    assert ticket["verify"]["verify_cmd"] == machine_cmd
    _verify(
        "VC-013", case="machine-layer",
        project_cmd="[]", machine_cmd=" ".join(machine_cmd),
        executed_cmd=" ".join(captured["cmd"]),
        consumed=str(captured["cmd"] == machine_cmd).lower(), **{"pass": "true"},
    )


# ── 5. xkey_repair=false: the anchoring surface stays unreachable ───────────


def test_disabled_channel_zero_change(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    control, _parent, partition, _sdk = _partition_fixture(tmp_path)
    _work_project(control, ("k-source", "k-owner"), statuses="k-source=done, k-owner=done")
    # Even an invalid selector must be irrelevant with the channel off.
    cfg = _config(
        control,
        [sys.executable, "-X", "utf8", "-c", "print('1 passed in 0.01s')"],
        cwd="nope",
        repair=False,
    )
    assert cfg["xkey_repair"] is False
    registration = xkey.parse_registration(_MACHINE_LINE)
    _plant_below(control, "k-source", registration)

    def unreachable(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        raise AssertionError("xkey anchoring must be unreachable with xkey_repair=false")

    monkeypatch.setattr(conductor, "_xkey_target_root", unreachable)
    monkeypatch.setattr(conductor, "_xkey", unreachable)
    monkeypatch.setattr(xkey, "run_verification", unreachable)

    st = _state(control)
    status = conductor.tick(control, st)
    events = timeline.query_events(timeline.timeline_path(control)).events
    leaked = [
        str(event.get("detail"))
        for event in events
        if event.get("ev") == "config" and "unreachable" in str(event.get("detail"))
    ]
    assert status != "error", (status, leaked)
    assert leaked == []
    assert not (control / ".agenticdoc" / "_autopilot" / "xkey").exists()
    assert xkey.tickets_iter(str(control)) == []
    assert xkey.ledger_load(str(control))["rows"] == []
    # the partition target is untouched (nothing ran)
    assert partition.exists()
    _verify(
        "VC-013", case="repair-off", tick_status=status,
        xkey_artifacts="0", verify_executed="false",
        anchoring_calls="0", zero_change="true",
    )
