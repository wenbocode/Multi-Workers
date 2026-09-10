"""
test_autopilot_roadmap.py — L1 tests for autopilot roadmap.py + roadmap_check.py
(T-03, AC-001 / VC-001).

All fixtures build their own project roots under tmp_path and run the check
CLI as a subprocess against them; nothing touches a real project. The check
CLI must stay standalone (no conductor, no config, no service).
"""
import os
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from autopilot import roadmap

CHECK_SCRIPT = pathlib.Path(__file__).parent / "autopilot" / "roadmap_check.py"

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _verify(tag: str, **kv) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()))


def _true(b: bool) -> str:
    return "true" if b else "false"


def write_roadmap(project_dir: pathlib.Path, text: str) -> pathlib.Path:
    path = roadmap.roadmap_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def run_check(
    project_dir: pathlib.Path | None = None,
    *,
    cwd: pathlib.Path | None = None,
) -> subprocess.CompletedProcess:
    """Run the check CLI. Pass project_dir for --project, or cwd only to
    exercise the default (cwd) resolution."""
    args = [sys.executable, str(CHECK_SCRIPT)]
    if project_dir is not None:
        args += ["--project", str(project_dir)]
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"  # force UTF-8 stdio on every platform
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        env=env,
        creationflags=_CREATE_NO_WINDOW,
    )


# A complete, valid roadmap: three elements per stage, a covered key-status
# line on stage 1, no key-status line on stage 2 (fresh proposal), and a
# legal cross-stage dependency (stage 2 -> stage 1).
VALID_ROADMAP = """\
# Roadmap
> generated_at: 2026-09-10T00:00:00+00:00
> goal_mtime: 1789000000000

## Stage 1: foundation modules
> goal: deliver the python infrastructure modules
> status: running
> key-status: k1=done, k2=running
### Keys
| key | role | depends_on |
|-----|------|-----------|
| k1 | parser | - |
| k2 | validator | k1 |

## Stage 2: conductor
> goal: deliver the conductor main loop
> status: pending
### Keys
| key | role | depends_on |
|-----|------|-----------|
| k3 | dispatcher | k1, k2 |
"""


# ── VC-001: valid sample exits 0 ──────────────────────────────────────────────

def test_valid_three_elements_exit_0(tmp_path: pathlib.Path) -> None:
    write_roadmap(tmp_path, VALID_ROADMAP)
    proc = run_check(tmp_path)
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    assert "roadmap OK" in proc.stdout
    assert "2 stage(s), 3 key(s)" in proc.stdout
    # Parse-level spot checks on the same sample.
    parsed = roadmap.parse_roadmap(VALID_ROADMAP)
    assert roadmap.validate_roadmap(parsed) == []
    _verify("VC-001", roadmap_check_exit=0)


def test_cli_default_project_is_cwd(tmp_path: pathlib.Path) -> None:
    write_roadmap(tmp_path, VALID_ROADMAP)
    proc = run_check(cwd=tmp_path)  # no --project: must default to cwd
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    _verify("VC-001", cli_default_cwd_exit=0)


def test_single_key_stage_valid(tmp_path: pathlib.Path) -> None:
    sample = """\
## Stage 1: solo
> goal: one key is enough
> status: pending
### Keys
| key | role | depends_on |
|-----|------|-----------|
| solo | everything | - |
"""
    write_roadmap(tmp_path, sample)
    proc = run_check(tmp_path)
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    _verify("VC-001", single_key_stage_exit=0)


# ── VC-001: missing dependency / empty goal / key-status mismatch → exit 1 ───

def test_missing_dependency_exit_1(tmp_path: pathlib.Path) -> None:
    sample = VALID_ROADMAP.replace("| k3 | dispatcher | k1, k2 |", "| k3 | dispatcher | k1, kX |")
    write_roadmap(tmp_path, sample)
    proc = run_check(tmp_path)
    assert proc.returncode == 1
    assert "kX" in proc.stderr and "not found" in proc.stderr
    _verify("VC-001", roadmap_check_exit=1, missing_dep_reported=_true(True))


def test_empty_goal_exit_1(tmp_path: pathlib.Path) -> None:
    sample = VALID_ROADMAP.replace(
        "> goal: deliver the python infrastructure modules", "> goal:"
    )
    write_roadmap(tmp_path, sample)
    proc = run_check(tmp_path)
    assert proc.returncode == 1
    assert "goal is empty" in proc.stderr
    assert "stage 1" in proc.stderr
    _verify("VC-001", roadmap_check_exit=1, empty_goal_reported=_true(True))


def test_key_status_set_mismatch_exit_1(tmp_path: pathlib.Path) -> None:
    # Missing: table has k1+k2 but the key-status line covers only k1.
    missing = VALID_ROADMAP.replace(
        "> key-status: k1=done, k2=running", "> key-status: k1=done"
    )
    write_roadmap(tmp_path, missing)
    proc = run_check(tmp_path)
    assert proc.returncode == 1
    assert "key-status missing key(s): k2" in proc.stderr

    # Unknown: key-status references k9 which is not in the Keys table.
    unknown = VALID_ROADMAP.replace(
        "> key-status: k1=done, k2=running", "> key-status: k1=done, k2=running, k9=stalled"
    )
    write_roadmap(tmp_path, unknown)
    proc = run_check(tmp_path)
    assert proc.returncode == 1
    assert "key-status has unknown key(s): k9" in proc.stderr
    _verify("VC-001", roadmap_check_exit=1, key_status_mismatch_reported=_true(True))


def test_zero_key_rows_exit_1(tmp_path: pathlib.Path) -> None:
    # Stage 1 keeps its table but has no data rows; stage 2 has no '### Keys'
    # section at all — both must be reported as key-less stages.
    sample = (
        "## Stage 1: empty table\n> goal: g\n> status: pending\n"
        "### Keys\n| key | role | depends_on |\n|-----|------|-----------|\n"
        "\n"
        "## Stage 2: no table at all\n> goal: g2\n> status: pending\n"
    )
    write_roadmap(tmp_path, sample)
    proc = run_check(tmp_path)
    assert proc.returncode == 1
    assert "no key rows" in proc.stderr
    assert proc.stderr.count("no key rows") == 2
    _verify("VC-001", zero_keys_exit=1)


# ── dependency direction: cross-stage legal, forward illegal ─────────────────

def test_cross_stage_dep_legal_forward_illegal(tmp_path: pathlib.Path) -> None:
    # Cross-stage (stage 2 -> stage 1) is part of VALID_ROADMAP: exit 0.
    write_roadmap(tmp_path, VALID_ROADMAP)
    assert run_check(tmp_path).returncode == 0

    # Forward (stage 1 key depends on a stage 2 key): illegal.
    forward = VALID_ROADMAP.replace("| k2 | validator | k1 |", "| k2 | validator | k3 |")
    write_roadmap(tmp_path, forward)
    proc = run_check(tmp_path)
    assert proc.returncode == 1
    assert "points to later stage 2" in proc.stderr
    assert "'k2'" in proc.stderr
    _verify("VC-001", cross_stage_dep_exit=0, forward_dep_exit=1)


def test_self_and_cyclic_dependencies_rejected(tmp_path: pathlib.Path) -> None:
    self_dep = """\
## Stage 1: a
> goal: g
> status: pending
### Keys
| key | role | depends_on |
|-----|------|-----------|
| k1 | r | k1 |
"""
    write_roadmap(tmp_path, self_dep)
    proc = run_check(tmp_path)
    assert proc.returncode == 1
    assert "depends on itself" in proc.stderr

    cycle = """\
## Stage 1: a
> goal: g
> status: pending
### Keys
| key | role | depends_on |
|-----|------|-----------|
| k1 | r | k2 |
| k2 | r | k1 |
"""
    write_roadmap(tmp_path, cycle)
    proc = run_check(tmp_path)
    assert proc.returncode == 1
    assert "dependency cycle" in proc.stderr
    _verify("VC-001", self_dep_exit=1, cycle_exit=1)


def test_duplicate_key_across_stages_exit_1(tmp_path: pathlib.Path) -> None:
    sample = VALID_ROADMAP.replace("| k3 | dispatcher | k1, k2 |", "| k1 | dispatcher | - |")
    write_roadmap(tmp_path, sample)
    proc = run_check(tmp_path)
    assert proc.returncode == 1
    assert "declared in both stage 1 and stage 2" in proc.stderr
    _verify("VC-001", duplicate_key_exit=1)


# ── format tolerance: enums, commas, trailing spaces, UTF-8, CRLF ─────────────

def test_status_enum_comma_and_trailing_space_tolerance(tmp_path: pathlib.Path) -> None:
    sample = """\
# Roadmap
> generated_at:  2026-09-10T00:00:00+00:00
> goal_mtime:  1789000000000

## Stage 1:  padded title
> goal:    a goal with heavy padding
> status:    running
> key-status:  k1=running ,  k2=done ,
### Keys
| key | role | depends_on |
| ----- | ------ | ----------- |
| k1   | parser   |   -   |
| k2 | validator | k1 ,   |

## Stage 2: second stage
> goal: 中文阶段目标（UTF-8 全链路）
> status: approved
### Keys
| key | role | depends_on |
|-----|------|-----------|
| k3 | dep | k1,k2 |
"""
    parsed = roadmap.parse_roadmap(sample)
    stage1 = roadmap.stage_by_number(parsed, 1)
    assert stage1 is not None
    assert stage1.status == "running"
    assert stage1.goal == "a goal with heavy padding"
    assert stage1.key_status == {"k1": "running", "k2": "done"}
    assert stage1.keys[0].depends_on == ()
    assert stage1.keys[1].depends_on == ("k1",)
    stage2 = roadmap.stage_by_number(parsed, 2)
    assert stage2 is not None
    assert stage2.keys[0].depends_on == ("k1", "k2")
    assert roadmap.validate_roadmap(parsed) == []

    write_roadmap(tmp_path, sample)
    proc = run_check(tmp_path)
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    _verify("VC-001", format_tolerance_exit=0)


def test_crlf_text_parses_and_updates(tmp_path: pathlib.Path) -> None:
    crlf = VALID_ROADMAP.replace("\n", "\r\n")
    parsed = roadmap.parse_roadmap(crlf)  # splitlines handles CRLF
    assert roadmap.validate_roadmap(parsed) == []

    updated = roadmap.update_stage_status(crlf, 1, "closed")
    assert "> status: closed\r" in updated.split("\n")
    assert updated.count("\r\n") == crlf.count("\r\n")  # no line gained/lost a CR
    assert roadmap.parse_roadmap(updated).stages[0].status == "closed"

    updated = roadmap.update_key_status(crlf, 2, "k3", "running")
    assert "> key-status: k3=running\r" in updated.split("\n")
    assert roadmap.parse_roadmap(updated).stages[1].key_status == {"k3": "running"}
    _verify("VC-001", crlf_roundtrip=_true(True))


# ── explicit parse failures (never silently swallowed) ────────────────────────

BAD_SAMPLES: dict[str, str] = {
    "no_stages": "# Roadmap\n> generated_at: x\nnothing else\n",
    "malformed_stage_header": (
        "## Stage x: title\n> goal: g\n> status: pending\n"
        "### Keys\n| key | role | depends_on |\n|-----|------|-----------|\n| k1 | r | - |\n"
    ),
    "duplicate_stage_number": (
        "## Stage 1: a\n> goal: g\n> status: pending\n"
        "### Keys\n| key | role | depends_on |\n|-----|------|-----------|\n| k1 | r | - |\n"
        "## Stage 1: b\n> goal: g\n> status: pending\n"
        "### Keys\n| key | role | depends_on |\n|-----|------|-----------|\n| k2 | r | - |\n"
    ),
    "missing_status_line": (
        "## Stage 1: a\n> goal: g\n### Keys\n| key | role | depends_on |\n|-----|------|-----------|\n| k1 | r | - |\n"
    ),
    "missing_goal_line": (
        "## Stage 1: a\n> status: pending\n### Keys\n| key | role | depends_on |\n|-----|------|-----------|\n| k1 | r | - |\n"
    ),
    "bad_status_enum": (
        "## Stage 1: a\n> goal: g\n> status: complete\n"
        "### Keys\n| key | role | depends_on |\n|-----|------|-----------|\n| k1 | r | - |\n"
    ),
    "bad_key_status_value": (
        "## Stage 1: a\n> goal: g\n> status: pending\n> key-status: k1=finished\n"
        "### Keys\n| key | role | depends_on |\n|-----|------|-----------|\n| k1 | r | - |\n"
    ),
    "malformed_key_status_entry": (
        "## Stage 1: a\n> goal: g\n> status: pending\n> key-status: k1\n"
        "### Keys\n| key | role | depends_on |\n|-----|------|-----------|\n| k1 | r | - |\n"
    ),
    "duplicate_key_status_entry": (
        "## Stage 1: a\n> goal: g\n> status: pending\n> key-status: k1=done, k1=running\n"
        "### Keys\n| key | role | depends_on |\n|-----|------|-----------|\n| k1 | r | - |\n"
    ),
    "duplicate_goal_line": (
        "## Stage 1: a\n> goal: g\n> goal: h\n> status: pending\n"
        "### Keys\n| key | role | depends_on |\n|-----|------|-----------|\n| k1 | r | - |\n"
    ),
    "duplicate_keys_section": (
        "## Stage 1: a\n> goal: g\n> status: pending\n### Keys\n"
        "| key | role | depends_on |\n|-----|------|-----------|\n| k1 | r | - |\n"
        "### Keys\n| key | role | depends_on |\n|-----|------|-----------|\n| k2 | r | - |\n"
    ),
    "bad_table_row_columns": (
        "## Stage 1: a\n> goal: g\n> status: pending\n### Keys\n"
        "| key | role | depends_on |\n|-----|------|-----------|\n| k1 | r |\n"
    ),
    "empty_key_cell": (
        "## Stage 1: a\n> goal: g\n> status: pending\n### Keys\n"
        "| key | role | depends_on |\n|-----|------|-----------|\n| | r | - |\n"
    ),
    "duplicate_key_row": (
        "## Stage 1: a\n> goal: g\n> status: pending\n### Keys\n"
        "| key | role | depends_on |\n|-----|------|-----------|\n| k1 | r | - |\n| k1 | r2 | - |\n"
    ),
}


@pytest.mark.parametrize("sample_id", sorted(BAD_SAMPLES))
def test_parse_failures_raise_explicit(sample_id: str) -> None:
    with pytest.raises(roadmap.RoadmapError):
        roadmap.parse_roadmap(BAD_SAMPLES[sample_id])


def test_parse_failures_surface_via_cli(tmp_path: pathlib.Path) -> None:
    write_roadmap(tmp_path, BAD_SAMPLES["bad_status_enum"])
    proc = run_check(tmp_path)
    assert proc.returncode == 1
    assert "roadmap parse error" in proc.stderr
    assert "invalid status 'complete'" in proc.stderr
    _verify("VC-001", parse_errors_explicit=len(BAD_SAMPLES))


def test_missing_roadmap_file(tmp_path: pathlib.Path) -> None:
    with pytest.raises(roadmap.RoadmapError) as excinfo:
        roadmap.load_roadmap(roadmap.roadmap_path(tmp_path))
    assert "not found" in str(excinfo.value)
    assert str(roadmap.roadmap_path(tmp_path)) in str(excinfo.value)

    proc = run_check(tmp_path)
    assert proc.returncode == 1
    assert "roadmap parse error" in proc.stderr
    assert "not found" in proc.stderr
    _verify("VC-001", missing_file_exit=1)


# ── stage enumeration + key dependency graph ─────────────────────────────────

def test_stage_enumeration_and_dependency_graph() -> None:
    parsed = roadmap.parse_roadmap(VALID_ROADMAP)
    assert [s.number for s in parsed.stages] == [1, 2]
    assert parsed.generated_at == "2026-09-10T00:00:00+00:00"
    assert parsed.goal_mtime == "1789000000000"
    assert roadmap.stage_by_number(parsed, 1).title == "foundation modules"
    assert roadmap.stage_by_number(parsed, 3) is None
    assert roadmap.stage_of_key(parsed) == {"k1": 1, "k2": 1, "k3": 2}
    assert roadmap.dependency_graph(parsed) == {"k1": set(), "k2": {"k1"}, "k3": {"k1", "k2"}}
    # key-status line absent on stage 2 → exempt, present on stage 1 → covered.
    assert roadmap.stage_by_number(parsed, 1).key_status_present is True
    assert roadmap.stage_by_number(parsed, 2).key_status_present is False
    _verify("VC-001", stage_enum=_true(True), dep_graph=_true(True))


# ── update helpers: only the status / key-status line changes ─────────────────

def test_update_stage_status_single_line_change() -> None:
    updated = roadmap.update_stage_status(VALID_ROADMAP, 2, "approved")
    old_lines = VALID_ROADMAP.split("\n")
    new_lines = updated.split("\n")
    assert len(old_lines) == len(new_lines)
    diff = [(a, b) for a, b in zip(old_lines, new_lines) if a != b]
    assert diff == [("> status: pending", "> status: approved")]
    parsed = roadmap.parse_roadmap(updated)
    assert roadmap.stage_by_number(parsed, 2).status == "approved"
    assert roadmap.stage_by_number(parsed, 1).status == "running"  # untouched
    _verify("VC-001", update_status_single_line=_true(True))


def test_update_key_status_replace_append_create() -> None:
    # Replace an existing entry (order preserved).
    updated = roadmap.update_key_status(VALID_ROADMAP, 1, "k2", "done")
    diff = [
        (a, b)
        for a, b in zip(VALID_ROADMAP.split("\n"), updated.split("\n"))
        if a != b
    ]
    assert diff == [("> key-status: k1=done, k2=running", "> key-status: k1=done, k2=done")]

    # Append a new entry when the line exists but covers fewer keys.
    partial = VALID_ROADMAP.replace(
        "> key-status: k1=done, k2=running", "> key-status: k1=done"
    )
    updated = roadmap.update_key_status(partial, 1, "k2", "running")
    assert "> key-status: k1=done, k2=running" in updated.split("\n")

    # Create the line (right after '> status:') when absent.
    updated = roadmap.update_key_status(VALID_ROADMAP, 2, "k3", "running")
    assert len(updated.split("\n")) == len(VALID_ROADMAP.split("\n")) + 1
    assert "> status: pending\n> key-status: k3=running" in updated
    parsed = roadmap.parse_roadmap(updated)
    assert roadmap.stage_by_number(parsed, 2).key_status == {"k3": "running"}
    assert roadmap.stage_by_number(parsed, 1).key_status == {"k1": "done", "k2": "running"}
    _verify("VC-001", update_key_status_line_only=_true(True))


def test_update_helpers_reject_bad_input() -> None:
    with pytest.raises(roadmap.RoadmapError, match="invalid stage status"):
        roadmap.update_stage_status(VALID_ROADMAP, 1, "finished")
    with pytest.raises(roadmap.RoadmapError, match="stage 9 not found"):
        roadmap.update_stage_status(VALID_ROADMAP, 9, "running")
    with pytest.raises(roadmap.RoadmapError, match="invalid key status"):
        roadmap.update_key_status(VALID_ROADMAP, 1, "k1", "complete")
    with pytest.raises(roadmap.RoadmapError, match="not in stage 1 Keys table"):
        roadmap.update_key_status(VALID_ROADMAP, 1, "kX", "done")
    with pytest.raises(roadmap.RoadmapError):  # structural failure, not silent
        roadmap.update_stage_status(BAD_SAMPLES["bad_status_enum"], 1, "running")
    _verify("VC-001", update_rejects_bad_input=_true(True))
