"""Tests for the AC-010 action-(3) upgrade (design §6.1, mw-worktree-junction-guard T-W09).

A fresh `collapse` event whose same-window junction inventory also moved must
become a `mw_common._doctor_issues` issue (so `mw doctor` rc flips). A collapse
without a link delta, a stale collapse, and a missing / corrupt / wrong-typed
state file must all stay silent and must never raise.

Every fixture lives under `%TEMP%` (`tempfile.mkdtemp`); no git command and no
junction is needed here - the state file is plain JSON and the real tree is
never touched. Junctions only appear in the `test_tree_watch.py` companion.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import sys
import tempfile
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw_common  # noqa: E402
import tree_watch  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def project() -> pathlib.Path:
    base = pathlib.Path(tempfile.mkdtemp(prefix="wjg-w09-"))
    root = base / "repo"
    root.mkdir()
    try:
        yield root
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _report(project: pathlib.Path, *, service_running: bool = True) -> dict:
    """The minimal `_doctor_issues` consumer shape with a clean baseline.

    `service.running=True` + an empty queue keeps this report at zero issues, so
    a single tree-watch finding is the only thing that can flip rc. The
    `worktree_links.registry_path` is the real hook `doctor_report` supplies and
    the consumption point derives the project root from it.
    """
    return {
        "service": {"running": service_running},
        "proxy_log": {},
        "queue": {
            "stale_count": 0,
            "unparsable_count": 0,
            "unparsable": [],
            "rows_total": 0,
            "non_terminal_count": 0,
            "alarm_delta": 50,
            "run_ledger_conflict": [],
        },
        "launcher_log": {},
        "bundle": {},
        "orphan_proxy": {"detected": False},
        "credentials": {"routes": []},
        "worktree_links": {
            "leftover": [],
            "stale_entries": [],
            "registry_path": str(project / ".mw" / "worktree-registry.json"),
        },
    }


def _rc(issues: list[str]) -> int:
    """`mw doctor`'s exit code: 0 healthy, 1 with any issue (summary.healthy)."""
    return 1 if issues else 0


def _write_state(project: pathlib.Path, payload: object) -> pathlib.Path:
    path = tree_watch.state_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _collapse_event(**overrides: object) -> dict:
    event: dict = {
        "kind": "collapse",
        "ts": time.time() - 5.0,
        "deleted_non_dist": 300,
        "delta": 300,
        "threshold": 28,
        "tracked_non_dist": 2822,
        "paths": ["packages/a/src/a.ts"],
        "link_delta": {"removed": 1, "changed": 0, "added": 0},
    }
    event.update(overrides)
    return event


def _tree_watch_issues(issues: list[str]) -> list[str]:
    return [issue for issue in issues if "tree-watch" in issue]


# ---------------------------------------------------------------------------
# Upgrade: fresh collapse + same-window link delta
# ---------------------------------------------------------------------------

def test_fresh_collapse_with_link_delta_upgrades_and_flips_rc(project: pathlib.Path) -> None:
    event = _collapse_event()

    baseline, baseline_suggestions = mw_common._doctor_issues(_report(project))
    assert baseline == []
    assert baseline_suggestions == []
    assert _rc(baseline) == 0

    _write_state(project, {"version": tree_watch.STATE_VERSION, "ts": event["ts"], "events": [event]})
    issues, suggestions = mw_common._doctor_issues(_report(project))
    found = _tree_watch_issues(issues)
    assert len(found) == 1
    text = found[0]
    assert f"ts={event['ts']}" in text
    assert "deleted_non_dist=300" in text
    assert "delta=300" in text
    assert "removed/changed/added=1/0/0" in text
    assert issues == found  # nothing else fired
    assert suggestions == []
    assert _rc(issues) == 1  # rc flipped 0 -> 1


def test_changed_and_added_counts_upgrade_too(project: pathlib.Path) -> None:
    event = _collapse_event(link_delta={"removed": 0, "changed": 2, "added": 3})
    _write_state(project, {"events": [event]})
    issues, _ = mw_common._doctor_issues(_report(project))
    assert len(_tree_watch_issues(issues)) == 1
    assert "removed/changed/added=0/2/3" in _tree_watch_issues(issues)[0]


def test_evaluate_persists_link_delta_through_write_state(project: pathlib.Path) -> None:
    """Requirement 1: the collapse event field must land in the state file."""
    previous = {
        "deleted_non_dist": 0,
        "links": [
            {"path": str(project / "node_modules" / "pkg"), "target_key": "t", "target": "t"},
        ],
    }
    sample = {
        "ts": time.time() - 3.0,
        "iso": "iso",
        "root": str(project),
        "tracked_total": 400,
        "tracked_non_dist": 400,
        "deleted_total": 300,
        "deleted_non_dist": 300,
        "deleted_paths": ["a"],
        "threshold": 20,
        "links": [],  # the junction was removed in the same window
    }
    verdict = tree_watch.evaluate(previous, sample)
    assert verdict["collapse"] is True
    event = next(item for item in verdict["events"] if item["kind"] == "collapse")
    assert event["link_delta"] == {"removed": 1, "changed": 0, "added": 0}

    tree_watch.write_state(project, sample, verdict)
    state = json.loads(tree_watch.state_path(project).read_text(encoding="utf-8"))
    persisted = next(item for item in state["events"] if item["kind"] == "collapse")
    assert persisted["link_delta"] == {"removed": 1, "changed": 0, "added": 0}
    # ... and the persisted field is what the doctor consumes.
    issues, _ = mw_common._doctor_issues(_report(project))
    assert len(_tree_watch_issues(issues)) == 1


# ---------------------------------------------------------------------------
# Reverse control: the design's "and" condition
# ---------------------------------------------------------------------------

def test_collapse_without_link_delta_does_not_upgrade(project: pathlib.Path) -> None:
    # (a) explicit zeros (files deleted, links untouched)
    _write_state(project, {"events": [_collapse_event(link_delta={"removed": 0, "changed": 0, "added": 0})]})
    issues, _ = mw_common._doctor_issues(_report(project))
    assert issues == []
    assert _rc(issues) == 0

    # (b) the field is absent entirely (older state file) - still silent
    event = _collapse_event()
    event.pop("link_delta")
    _write_state(project, {"events": [event]})
    issues, _ = mw_common._doctor_issues(_report(project))
    assert issues == []


def test_stale_collapse_with_link_delta_does_not_upgrade(project: pathlib.Path) -> None:
    stale = _collapse_event(ts=time.time() - (mw_common.TREE_WATCH_ISSUE_WINDOW_SEC + 60))
    _write_state(project, {"events": [stale]})
    issues, _ = mw_common._doctor_issues(_report(project))
    assert issues == []
    assert _rc(issues) == 0

    # Well inside the window is still upgraded (inclusive upper bound).
    inside = _collapse_event(ts=time.time() - (mw_common.TREE_WATCH_ISSUE_WINDOW_SEC - 60))
    _write_state(project, {"events": [inside]})
    issues, _ = mw_common._doctor_issues(_report(project))
    assert len(_tree_watch_issues(issues)) == 1

    # A future ts (clock skew) is not "fresh evidence" and stays silent.
    future = _collapse_event(ts=time.time() + 600)
    _write_state(project, {"events": [future]})
    issues, _ = mw_common._doctor_issues(_report(project))
    assert issues == []


# ---------------------------------------------------------------------------
# Fail-open-to-verdict: missing / corrupt / wrong-typed state
# ---------------------------------------------------------------------------

def test_missing_state_file_is_silent(project: pathlib.Path) -> None:
    assert not tree_watch.state_path(project).exists()
    issues, _ = mw_common._doctor_issues(_report(project))
    assert issues == []


@pytest.mark.parametrize(
    "payload",
    [
        "{not json",
        "[]",
        '"a string"',
        "42",
        '{"events": "nope"}',
        '{"events": {"kind": "collapse"}}',
        '{"events": [123, "x", null]}',
        '{"events": [{"kind": "collapse", "ts": "now", "link_delta": {"removed": 1}}]}',
        '{"events": [{"kind": "collapse", "ts": true, "link_delta": {"removed": 1}}]}',
        '{"events": [{"kind": "collapse", "ts": 1.0, "link_delta": "nope"}]}',
        '{"events": [{"kind": "collapse", "ts": 1.0, "link_delta": {"removed": "1"}}]}',
        '{"events": [{"kind": "collapse", "ts": 1.0, "link_delta": {"removed": true}}]}',
        '{"events": [{"kind": "broken-link", "path": "x"}]}',
    ],
)
def test_corrupt_or_wrong_typed_state_is_silent(project: pathlib.Path, payload: str) -> None:
    path = tree_watch.state_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    issues, suggestions = mw_common._doctor_issues(_report(project))  # must not raise
    assert issues == []
    assert suggestions == []


def test_state_path_is_a_directory_is_silent(project: pathlib.Path) -> None:
    tree_watch.state_path(project).mkdir(parents=True)
    issues, _ = mw_common._doctor_issues(_report(project))  # IsADirectoryError swallowed
    assert issues == []


def test_report_without_worktree_section_is_silent(project: pathlib.Path) -> None:
    report = _report(project)
    report.pop("worktree_links")
    _write_state(project, {"events": [_collapse_event()]})
    issues, _ = mw_common._doctor_issues(report)
    assert issues == []


# ---------------------------------------------------------------------------
# Coexistence: the new issue must not swallow existing ones
# ---------------------------------------------------------------------------

def test_coexists_with_existing_issues_preserves_order_and_count(project: pathlib.Path) -> None:
    baseline, _ = mw_common._doctor_issues(_report(project, service_running=False))
    assert len(baseline) == 1

    _write_state(project, {"events": [_collapse_event()]})
    issues, _ = mw_common._doctor_issues(_report(project, service_running=False))

    assert len(issues) == 2
    assert issues[0].startswith("mw service not running")
    assert "tree-watch-collapse" in issues[1]
    # The pre-existing issue is byte-identical to the no-state baseline.
    assert issues[0] == baseline[0]


def test_two_fresh_collapse_events_yield_two_issues(project: pathlib.Path) -> None:
    """The state file carries one sample, but the loop must not collapse
    multiple findings into one (order/count honesty)."""
    first = _collapse_event(deleted_non_dist=300, delta=300)
    second = _collapse_event(deleted_non_dist=350, delta=50)
    _write_state(project, {"events": [first, second]})
    issues, _ = mw_common._doctor_issues(_report(project))
    found = _tree_watch_issues(issues)
    assert len(found) == 2
    assert "deleted_non_dist=300" in found[0]
    assert "deleted_non_dist=350" in found[1]
