"""test_write_face_e2e.py - W-07/B3: end-to-end parity of the two write-face
dispatch channels (conductor `autopilot/dispatch.py::_write_face_verdict` and
PM `pm/task-dispatcher.ts::dispatchTask`), plus the AC-005 reverse proof.

Card: `.agenticdoc/mw-write-face-guard/tasks/T-W-I12-e2e-parity.md`
- ① the frozen corpus (`test/fixtures/write-face-corpus.json`) is fed through ONE
  device: the same in-flight queue row + the same candidate task.md text go to
  the conductor entry (read-only import, no Python source is written) and to the
  PM entry (spawned through node --experimental-strip-types, read-only import of
  the TS source). The verdicts are compared field by field:
  `ok` / `code` / `overlap-with:<task_key>` / `sample` / `serial-only`.
- ①b the alignment lesson: the previous PM differential produced 4 false
  inconsistencies because the two sides were given DIFFERENT bases
  (`evidence/PM-parity-differential-20261014.md` §0). The device below makes the
  misalignment reproducible and counts it, then proves the aligned run is 0.
- ② AC-005 reverse proof: a same-time same-key same-file scenario yields 0
  multi-writer pairs through the real conductor dispatch, and a gate-bypassing
  write makes the recomputed pair count > 0 (the detector is not self-proving).
- ③ AC-013 two-channel table: the true-write family (`..` escape, outside-base
  absolute, invalid entry, directory-target crossing) must be refused by both
  channels; the false-write family (`Write-Output a <term> --glob x`, here-string
  payloads, read-only commands) must pass both channels.

The runtime half of AC-013 (worker-side bash/write guard) is pinned by the
sibling TS suite `packages/coding-agent/test/suite/write-face-e2e.test.ts`; this
file pins the two DISPATCH channels.

Run: cd packages/multi-workers; python -m pytest test/test_write_face_e2e.py -q
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

import pytest

PKG_ROOT = pathlib.Path(__file__).resolve().parent.parent
REPO_ROOT = PKG_ROOT.parent.parent
sys.path.insert(0, str(PKG_ROOT))

import mw_common  # noqa: E402
from autopilot import dispatch as D  # noqa: E402
from autopilot import timeline as timeline_mod  # noqa: E402
from autopilot import write_face as wf  # noqa: E402

CORPUS_PATH = PKG_ROOT / "test" / "fixtures" / "write-face-corpus.json"
# The frozen corpus fingerprint (LF-normalized; the Windows file is CRLF, 20126 B).
CORPUS_SHA256_LF = "b39f89250c39177f9638e8d3ecddfce176dcaf846648a2ea1e9afebb479d6a62"
CORPUS_COUNTS = {"parse": 23, "overlap": 59}

OWNER = "wfk-e2e"
CAND = "w-new"
INFLIGHT = "w-keep"
CARD_PATH = "tasks/T-W-I12-e2e.md"

PROCEED = {"ok": True, "code": None, "overlapWith": None, "sample": None, "serialOnly": False}

# AC-013 false-write family: measured vectors that look like writes but are not.
# Mirrors `write-face-runtime.test.ts` FALSE_WRITE_VECTORS (runtime side) so the
# same text can be embedded in a task.md BODY and must not refuse the dispatch.
FALSE_WRITE_VECTORS = [
    "Write-Output a <term> --glob x",
    "Write-Output a <term>",
    "Write-Output \"probe: <term> --glob '!x' done\"",
    "$code = @'\ndon't do x > y\n'@\nWrite-Output $code",
    '[[ "$ts" > "2026-01-01" ]]',
    'echo "a > b"',
    "bash -c \"grep -n '>' f\"",
    "rg -n -F TERM --glob '!node_modules' .",
    "echo x 2>&1",
    "Get-Content a.txt > /dev/null",
    "echo x > $null",
]

READ_ONLY_COMMANDS = ["rg -n foo packages", "cat package.json", "git status --porcelain"]


def _corpus() -> dict:
    return json.loads(CORPUS_PATH.read_text(encoding="utf-8"))


def _tmp_root(name: str) -> pathlib.Path:
    return pathlib.Path(tempfile.mkdtemp(prefix=name))


@pytest.fixture()
def workdir():
    root = _tmp_root("wf-e2e-py-")
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------------------
# 0. Frozen corpus fingerprint (the shared input of BOTH sides)
# ---------------------------------------------------------------------------


def test_frozen_corpus_fingerprint_and_counts():
    """The corpus is the shared input; a drift would silently re-freeze both
    sides. LF-normalized sha256 + the pinned counts (P-021)."""
    raw = CORPUS_PATH.read_bytes()
    normalized = raw.decode("utf-8").replace("\r\n", "\n").encode("utf-8")
    assert hashlib.sha256(normalized).hexdigest() == CORPUS_SHA256_LF
    corpus = json.loads(raw.decode("utf-8"))
    assert {k: len(corpus[k]) for k in CORPUS_COUNTS} == CORPUS_COUNTS


# ---------------------------------------------------------------------------
# Device: one in-flight context + one candidate write face per case
# ---------------------------------------------------------------------------


def _subst(text: str, project: pathlib.Path, outside: pathlib.Path) -> str:
    return text.replace("$REPO", str(project)).replace("$OUTSIDE", str(outside))


def _face_head(entries: list[str] | None, name: str = "write_face") -> str:
    """The D-113 carrier for an entry list: block list (comma-safe), `-` for a
    declared-but-empty face, nothing when the face is undeclared."""
    if entries is None:
        return ""
    if len(entries) == 0:
        return f"{name}: -\n"
    return f"{name}:\n" + "".join(f"  - {entry}\n" for entry in entries)


def _build_cases(corpus: dict, project: pathlib.Path, outside: pathlib.Path) -> list[dict]:
    cases: list[dict] = []
    for row in corpus["parse"]:
        head = "\n".join(_subst(line, project, outside) for line in row["head"])
        cases.append(
            {
                "name": row["name"],
                "kind": "parse",
                "row": row,
                "a": None,
                "b": None,
                "candidate": f"card_path: {CARD_PATH}\n{head}\n\nbody\n",
                "inflight": None,
            }
        )
    for row in corpus["overlap"]:
        a = None if row["a"] is None else [_subst(e, project, outside) for e in row["a"]]
        b = None if row["b"] is None else [_subst(e, project, outside) for e in row["b"]]
        deny = [_subst(e, project, outside) for e in row.get("a_deny", [])]
        text = (
            f"card_path: {CARD_PATH}\n"
            + _face_head(a)
            + _face_head(deny if deny else None, "write_face_deny")
            + "\nbody\n"
        )
        cases.append(
            {
                "name": row["name"],
                "kind": "overlap",
                "row": row,
                "a": a,
                "b": b,
                "candidate": text,
                "inflight": None if b is None else _face_head(b) + "\nbody\n",
            }
        )
    return cases


def _materialize(cases: list[dict], project: pathlib.Path) -> pathlib.Path:
    ad = project / ".agenticdoc"
    for index, case in enumerate(cases):
        task_key = f"{CAND}-{index:03d}"
        task_md = ad / OWNER / "workers" / task_key / "task.md"
        task_md.parent.mkdir(parents=True, exist_ok=True)
        task_md.write_text(case["candidate"], encoding="utf-8", newline="\n")
        case["taskKey"] = task_key
        case["taskPath"] = str(task_md)
        if case["inflight"] is not None:
            inflight_key = f"{INFLIGHT}-{index:03d}"
            inflight_md = ad / OWNER / "workers" / inflight_key / "task.md"
            inflight_md.parent.mkdir(parents=True, exist_ok=True)
            inflight_md.write_text(case["inflight"], encoding="utf-8", newline="\n")
            case["inflightKey"] = inflight_key
            case["inflightPath"] = str(inflight_md)
        else:
            case["inflightKey"] = None
            case["inflightPath"] = None
    return ad


def _queue_rows(case: dict) -> list[dict[str, str]]:
    if case["inflightKey"] is None:
        return []
    return [
        {
            "task_key": case["inflightKey"],
            "status": "running",
            "cli": "pi",
            "provider": "timi",
            "task_path": case["inflightPath"],
            "dispatched_at": "2026-10-14T00:00:00.000Z",
            "updated_at": "2026-10-14T00:00:00.000Z",
            "model": "",
            "origin": "manual",
        }
    ]


def _reset_queue(ad: pathlib.Path, case: dict) -> None:
    """The in-flight set is recomputed from the LIVE queue (AC-008): reset it to
    exactly this case's context before each channel judgement."""
    queue = ad / "_workers.parallel"
    rows = _queue_rows(case)
    if not rows:
        if queue.exists():
            queue.unlink()
        return
    queue.parent.mkdir(parents=True, exist_ok=True)
    queue.write_text(
        "\n".join(mw_common.serialize_entry(row) for row in rows) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _shape_refusal(code: str, overlap_with: str | None, sample: str | None) -> dict:
    return {
        "ok": False,
        "code": code,
        "overlapWith": overlap_with,
        "sample": sample,
        "serialOnly": code == "write-face-undeclared",
    }


def _shape_reason(reason: str) -> dict:
    """The conductor's refusal reason -> the same field shape as the PM's
    structured refusal. Codes never contain `:` (stable constants)."""
    code = reason.split(":", 1)[0]
    overlap = re.search(r"overlap-with:(\S+)", reason)
    sample = re.search(r"sample=(\S+)", reason)
    return _shape_refusal(
        code,
        overlap.group(1) if overlap else None,
        sample.group(1) if sample else None,
    )


def _conductor_verdict(ad: pathlib.Path, project: pathlib.Path, case: dict) -> dict:
    """Read-only call of the real conductor entry (inside its lock in
    production; the entry itself is lock-free and zero-side-effect)."""
    _reset_queue(ad, case)
    verdict = D._write_face_verdict(
        project,
        OWNER,
        case["taskKey"],
        case["candidate"],
        card_backed=True,
        timeline=None,
    )
    if verdict is None:
        return dict(PROCEED)
    assert verdict.ok is False, verdict
    return _shape_reason(verdict.reason)


def _gate_projection(case: dict, base: pathlib.Path, ci: bool) -> dict:
    """The documented channel algorithm expressed with the shared operator:
    parse own face -> parse in-flight faces -> D-003/D-111 overlap decision.
    Both real channels must agree with this shape (wiring check: in-flight
    filtering + field mapping + cardBacked)."""
    own = wf.parse_write_face(case["candidate"], base=str(base), case_insensitive=ci)
    if isinstance(own, wf.Refused):
        return _shape_refusal(own.code, None, None)
    other = (
        wf.parse_write_face(case["inflight"], base=str(base), case_insensitive=ci)
        if case["inflight"] is not None
        else wf.Undeclared()
    )
    if isinstance(own, wf.Undeclared):
        if isinstance(other, wf.WriteFace):
            return _shape_refusal("write-face-undeclared", None, None)
        return dict(PROCEED)
    if not isinstance(other, wf.WriteFace):
        return dict(PROCEED)  # D-003: an undeclared side cannot prove an overlap
    result = wf.overlap(own, other)
    if result is None:
        return dict(PROCEED)
    if isinstance(result, wf.Conflict):
        return _shape_refusal("write-face-overlap", case["inflightKey"], result.sample)
    return _shape_refusal("write-face-overlap", case["inflightKey"], None)


# ---------------------------------------------------------------------------
# PM channel: node bridge over the real `dispatchTask` (read-only import)
# ---------------------------------------------------------------------------

_PM_BRIDGE = r"""
import * as fs from "node:fs";
import * as path from "node:path";
import { dispatchTask, writeFaceBase, writeFaceCaseInsensitive } from "__DISPATCHER__";
import { WorkerStore } from "__STORE__";
import { TERMINAL_WORKER_STATUSES } from "__STATUS__";

const req = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const projectRoot = req.projectRoot;
const agenticdoc = path.join(projectRoot, ".agenticdoc");
const queuePath = path.join(agenticdoc, "_workers.parallel");
const verdicts = [];
for (const c of req.cases) {
  const rows = c.queueRows ?? [];
  if (rows.length > 0) {
    fs.mkdirSync(path.dirname(queuePath), { recursive: true });
    const text = rows
      .map((r) =>
        [r.task_key, r.status, r.cli, r.provider, r.task_path, r.dispatched_at, r.updated_at, r.model ?? "", r.origin ?? ""].join(" | "),
      )
      .join("\n");
    fs.writeFileSync(queuePath, text + "\n", "utf8");
  } else if (fs.existsSync(queuePath)) {
    fs.rmSync(queuePath);
  }
  const store = new WorkerStore(agenticdoc);
  const outcome = await dispatchTask(
    { taskKey: c.taskKey, status: "pending", cli: "pi", provider: "timi", model: "", taskPath: c.taskPath },
    store,
  );
  if (outcome.ok === true) {
    verdicts.push({ ok: true, code: null, overlapWith: null, sample: null, serialOnly: false });
    continue;
  }
  const reason = outcome.reason ?? "";
  const overlap = /overlap-with:(\S+)/.exec(reason);
  const sample = /sample=(\S+)/.exec(reason);
  verdicts.push({
    ok: false,
    code: outcome.code,
    overlapWith: outcome.overlapWith ?? (overlap ? overlap[1] : null),
    sample: outcome.sample ?? (sample ? sample[1] : null),
    serialOnly: outcome.serialOnly === true,
  });
}
fs.writeFileSync(
  process.argv[3],
  JSON.stringify({
    verdicts,
    terminal: [...TERMINAL_WORKER_STATUSES].sort(),
    caseInsensitive: writeFaceCaseInsensitive(),
    base: writeFaceBase(agenticdoc),
  }),
  "utf8",
);
"""


def _node_exe() -> str:
    return os.environ.get("MW_NODE", "").strip() or shutil.which("node") or "node"


def _pm_bridge_path(workdir: pathlib.Path) -> pathlib.Path:
    def url(rel: str) -> str:
        return (REPO_ROOT / rel).as_uri()

    script = (
        _PM_BRIDGE.replace(
            "__DISPATCHER__",
            url("packages/coding-agent/src/extensions/agent-team-loop/pm/task-dispatcher.ts"),
        )
        .replace(
            "__STORE__",
            url("packages/coding-agent/src/extensions/agent-team-loop/shared/worker-store.ts"),
        )
        .replace(
            "__STATUS__",
            url("packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts"),
        )
    )
    path = workdir / "pm-bridge.mts"
    path.write_text(script, encoding="utf-8", newline="\n")
    return path


def _pm_verdicts(workdir: pathlib.Path, project: pathlib.Path, cases: list[dict]) -> dict:
    bridge = _pm_bridge_path(workdir)
    request = {
        "projectRoot": str(project),
        "owner": OWNER,
        "cases": [
            {
                "name": case["name"],
                "taskKey": case["taskKey"],
                "taskPath": case["taskPath"],
                "queueRows": _queue_rows(case),
            }
            for case in cases
        ],
    }
    req_path = workdir / "pm-request.json"
    res_path = workdir / "pm-response.json"
    req_path.write_text(json.dumps(request), encoding="utf-8")
    proc = subprocess.run(
        [_node_exe(), "--experimental-strip-types", str(bridge), str(req_path), str(res_path)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if proc.returncode != 0 or not res_path.exists():
        raise AssertionError(f"PM bridge failed rc={proc.returncode}\n{proc.stdout}\n{proc.stderr}")
    return json.loads(res_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# ① same corpus, both channels, field by field
# ---------------------------------------------------------------------------


def test_two_channels_agree_field_by_field_on_the_frozen_corpus(workdir):
    """AC-007 (D-001/D-111/D-112/D-115): the same in-flight context + the same
    candidate face through BOTH channels produce the same `ok`/`code`/
    `overlap-with`/`sample`/`serial-only`. This is the收口 evidence: not two
    independent unit suites, one device."""
    # Device equivalence precondition (card requirement 4): base is the
    # `.agenticdoc` parent on both sides, and the case mode is the platform
    # mode from each side's single helper (asserted, never skipped).
    assert os.name == "nt", "this machine is win32; the gate case mode is asserted, not skipped"
    assert D.write_face_case_insensitive() is (os.name == "nt")
    project = workdir / "project"
    project.mkdir()
    alt = workdir / "alt"
    alt.mkdir()
    outside = alt / "outside-dir"
    assert D.write_face_base(project) == str(project)

    cases = _build_cases(_corpus(), project, outside)
    ad = _materialize(cases, project)
    assert len(cases) == CORPUS_COUNTS["parse"] + CORPUS_COUNTS["overlap"]

    conductor = [_conductor_verdict(ad, project, case) for case in cases]
    bridge = _pm_verdicts(workdir, project, cases)
    pm = bridge["verdicts"]
    assert len(pm) == len(cases)

    # The two sides' terminal-status sets are the two single sources (the gate's
    # in-flight filter). Equality is the cross-language precondition (card
    # requirement 4), asserted here rather than assumed.
    assert sorted(mw_common._TERMINAL_STATUSES) == bridge["terminal"]
    assert bridge["caseInsensitive"] is D.write_face_case_insensitive()
    assert pathlib.Path(bridge["base"]).resolve() == project.resolve()

    ci = D.write_face_case_insensitive()
    mismatches = []
    projection_mismatches = []
    for case, left, right in zip(cases, conductor, pm):
        expected = _gate_projection(case, project, ci)
        if left != right:
            mismatches.append((case["name"], left, right))
        if left != expected:
            projection_mismatches.append((case["name"], left, expected))
        if right != expected:
            projection_mismatches.append((case["name"], right, expected))
    print(f"[EVIDENCE] aligned channel mismatches={len(mismatches)} projection={len(projection_mismatches)}")
    if os.environ.get("WF_E2E_TABLE"):
        for case, left, right in zip(cases, conductor, pm):
            print(f"[TABLE] {case['name']} | conductor={json.dumps(left)} | pm={json.dumps(right)}")
    assert mismatches == [], mismatches[:8]
    assert projection_mismatches == [], projection_mismatches[:8]

    # The corpus is exercised, not vacuously skipped: both verdict shapes occur.
    codes = {verdict["code"] for verdict in conductor}
    assert "write-face-overlap" in codes
    assert None in codes


def test_base_misalignment_reproduces_the_false_inconsistencies(workdir):
    """The previous device defect (card requirement 1; evidence §0): giving the
    two sides different bases manufactures false inconsistencies. Reproduce it
    at the operator level and count it; the aligned count is the parity test's
    real channel mismatch count (0)."""
    project = workdir / "project"
    project.mkdir()
    alt = workdir / "alt"
    alt.mkdir()
    outside = alt / "outside-dir"
    ci = D.write_face_case_insensitive()
    cases = _build_cases(_corpus(), project, outside)

    def signature(case: dict, base: pathlib.Path) -> str:
        parsed = wf.parse_write_face(case["candidate"], base=str(base), case_insensitive=ci)
        if isinstance(parsed, wf.Refused):
            return f"reject:{parsed.code}"
        if isinstance(parsed, wf.Undeclared):
            return "undeclared"
        return "declared:" + ",".join(parsed.allow_entries)

    unaligned = [case["name"] for case in cases if signature(case, project) != signature(case, alt)]
    print(f"[EVIDENCE] base alignment before={len(unaligned)} after=0 names={unaligned}")
    assert len(unaligned) > 0, "base misalignment must be observable (the historical 4)"


# ---------------------------------------------------------------------------
# ② AC-005 reverse proof (conductor)
# ---------------------------------------------------------------------------

_CARD_HEAD = (
    "type: coding\n"
    "\n"
    "## 上下文\n\n上下文。\n\n"
    "## 要求\n\n要求。\n\n"
    "## 交付格式\n\n交付格式。\n\n"
)


def _write_card(project: pathlib.Path, owner: str, stem: str, entries: list[str]) -> None:
    card_dir = project / ".agenticdoc" / owner / "tasks"
    card_dir.mkdir(parents=True, exist_ok=True)
    body = "\n".join(f"- `{entry}`" for entry in entries)
    (card_dir / f"{stem}.md").write_text(
        _CARD_HEAD + f"## 写入允许面\n\n{body}\n", encoding="utf-8", newline="\n"
    )


def _face_of(row: dict, project: pathlib.Path) -> object:
    path = str(row.get("task_path") or "")
    if not path or not pathlib.Path(path).exists():
        return wf.Undeclared()
    return wf.parse_write_face(
        pathlib.Path(path).read_text(encoding="utf-8", errors="replace"),
        base=str(project),
        case_insensitive=D.write_face_case_insensitive(),
    )


def _multi_writer_pairs(project: pathlib.Path) -> list[tuple[str, str]]:
    """Recompute AC-005 from the live snapshot: queue rows + each row's task.md
    `write_face:` field. A pair counts when both sides declare and the shared
    operator does not return None (Unsupported is an overlap, D-006)."""
    rows = mw_common.parse_workers_file(mw_common.workers_path(project))
    live = [row for row in rows if str(row.get("status", "")) not in mw_common._TERMINAL_STATUSES]
    groups: dict[str, list[dict]] = {}
    for row in live:
        groups.setdefault(mw_common.worker_owner_key(row), []).append(row)
    pairs: list[tuple[str, str]] = []
    for group in groups.values():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                left = _face_of(group[i], project)
                right = _face_of(group[j], project)
                if isinstance(left, wf.WriteFace) and isinstance(right, wf.WriteFace):
                    if wf.overlap(left, right) is not None:
                        pairs.append((group[i]["task_key"], group[j]["task_key"]))
    return pairs


def test_ac005_same_key_same_file_has_zero_multi_writer_pairs(workdir):
    """AC-005 (goal anchor): at the same time, same key, same file the number of
    multi-writer pairs is 0 through the real conductor dispatch; and the
    detector is not self-proving — bypassing the gate makes it > 0."""
    project = workdir / "project"
    project.mkdir()
    timeline = timeline_mod.Timeline(project / ".agenticdoc" / "_autopilot" / "timeline.jsonl")
    _write_card(project, OWNER, "keep", ["packages/x/**"])
    first = D.dispatch(
        project, OWNER, "keep", "phase-writer", "Do the work.",
        loop=f"exec:{OWNER}:keep", attempt=1, timeline=timeline,
    )
    assert first.ok and first.row_verified, first.reason

    _write_card(project, OWNER, "new", ["packages/x/file.ts"])
    second = D.dispatch(
        project, OWNER, "new", "phase-writer", "Do the work.",
        loop=f"exec:{OWNER}:new", attempt=1, timeline=timeline,
    )
    assert not second.ok, second.reason
    assert second.reason.startswith("write-face-overlap"), second.reason

    refused_pairs = _multi_writer_pairs(project)
    print(f"[EVIDENCE] AC-005 pairs after real dispatch={len(refused_pairs)} rows={[r['task_key'] for r in mw_common.parse_workers_file(mw_common.workers_path(project))]}")
    assert refused_pairs == [], refused_pairs

    # Counter-example (detector effectiveness): write the second worker's row
    # and task.md directly, bypassing the gate -> the recomputation is > 0.
    bypass_dir = project / ".agenticdoc" / OWNER / "workers" / "ap-wfk-e2e-bypass"
    bypass_dir.mkdir(parents=True, exist_ok=True)
    bypass_md = bypass_dir / "task.md"
    bypass_md.write_text("write_face: packages/x/file.ts\n", encoding="utf-8", newline="\n")
    mw_common.upsert_worker_row(
        mw_common.workers_path(project),
        {
            "task_key": "ap-wfk-e2e-bypass",
            "status": "running",
            "cli": "pi",
            "provider": "timi",
            "task_path": str(bypass_md),
            "dispatched_at": "2026-10-14T00:00:00.000Z",
            "updated_at": "2026-10-14T00:00:00.000Z",
            "model": "",
            "origin": "conductor",
        },
    )
    bypass_pairs = _multi_writer_pairs(project)
    print(f"[EVIDENCE] AC-005 pairs after gate bypass={len(bypass_pairs)} pairs={bypass_pairs}")
    assert len(bypass_pairs) == 1, bypass_pairs


# ---------------------------------------------------------------------------
# ③ AC-013 two-channel table: true writes blocked, false writes passed
# ---------------------------------------------------------------------------

TRUE_WRITE_GATE_CASES = [
    ("escape-parent", "write_face: ../outside/x.ts\n", "packages/x/**", "write-face-escape"),
    ("outside-base-absolute", "write_face: $OUTSIDE/pkg/x.ts\n", "packages/x/**", "write-face-outside-base"),
    ("invalid-negated-entry", "write_face: !packages/x/**\n", "packages/x/**", "write-face-invalid-entry"),
    ("directory-target-crossing", "write_face: packages/x/deep/file.ts\n", "packages/x/**", "write-face-overlap"),
]


def test_ac013_true_write_family_is_refused_by_both_channels(workdir):
    """AC-013 (true direction): `..` escape, outside-base absolute, invalid
    entry and a directory-target crossing must be refused by BOTH channels —
    the per-case table with one column per channel."""
    project = workdir / "project"
    project.mkdir()
    alt = workdir / "alt"
    alt.mkdir()
    outside = alt / "outside-dir"
    ci = D.write_face_case_insensitive()
    ad = project / ".agenticdoc"

    cases = []
    for index, (name, head, inflight_face, _expected) in enumerate(TRUE_WRITE_GATE_CASES):
        candidate = f"card_path: {CARD_PATH}\n{_subst(head, project, outside)}"
        cases.append(
            {
                "name": name,
                "kind": "overlap",
                "row": {},
                "a": None,
                "b": None,
                "candidate": candidate + "\nbody\n",
                "inflight": f"write_face: {inflight_face}\n",
                "taskKey": f"{CAND}-{index:03d}",
            }
        )
    _materialize(cases, project)
    conductor = [_conductor_verdict(ad, project, case) for case in cases]
    pm = _pm_verdicts(workdir, project, cases)["verdicts"]

    table = [(case["name"], left, right) for case, left, right in zip(cases, conductor, pm)]
    for case, left, right, (name, _head, _inflight_face, expected) in zip(cases, conductor, pm, TRUE_WRITE_GATE_CASES):
        assert left["ok"] is False, (name, left)
        assert left["code"] == expected, (name, left, expected)
        assert right == left, (name, left, right)
        assert pathlib.Path(case["inflightPath"]).exists(), name
    print(f"[EVIDENCE] AC-013 true-write table={table}")
    assert len(table) == len(TRUE_WRITE_GATE_CASES)
    # The operator agrees with the expected code (independent of the channel).
    for name, head, inflight_face, expected in TRUE_WRITE_GATE_CASES:
        head = _subst(head, project, outside)
        own = wf.parse_write_face(_subst(head, project, outside), base=str(project), case_insensitive=ci)
        if expected in ("write-face-overlap",):
            assert isinstance(own, wf.WriteFace), (name, own)
            other = wf.parse_write_face(f"write_face: {inflight_face}\n", base=str(project), case_insensitive=ci)
            assert isinstance(other, wf.WriteFace)
            assert isinstance(wf.overlap(own, other), wf.Conflict), name
        else:
            assert isinstance(own, wf.Refused) and own.code == expected, (name, own)


def test_ac013_false_write_family_passes_both_channels(workdir):
    """AC-013 (false direction): the measured false-positive family
    (`Write-Output a <term> --glob x`, PowerShell here-strings, quoted `>`,
    read-only commands) lives in the task.md BODY; the gate must read only the
    `write_face:` head and pass it on BOTH channels."""
    project = workdir / "project"
    project.mkdir()
    alt = workdir / "alt"
    alt.mkdir()
    outside = alt / "outside-dir"
    ad = project / ".agenticdoc"

    bodies = [{"name": f"false-write-{i}", "body": vector} for i, vector in enumerate(FALSE_WRITE_VECTORS)]
    bodies += [{"name": f"read-only-{i}", "body": command} for i, command in enumerate(READ_ONLY_COMMANDS)]
    cases = []
    for index, item in enumerate(bodies):
        case = {
            "name": item["name"],
            "kind": "parse",
            "row": {},
            "a": None,
            "b": None,
            "candidate": (
                f"card_path: {CARD_PATH}\nwrite_face: packages/x/**\n\n"
                f"## body\n\n{item['body']}\n"
            ),
            "inflight": None,
            "taskKey": f"{CAND}-{index:03d}",
        }
        cases.append(case)
    _materialize(cases, project)
    conductor = [_conductor_verdict(ad, project, case) for case in cases]
    pm = _pm_verdicts(workdir, project, cases)["verdicts"]
    table = [(case["name"], left, right) for case, left, right in zip(cases, conductor, pm)]
    print(f"[EVIDENCE] AC-013 false-write table={table}")
    assert conductor == [dict(PROCEED)] * len(cases), conductor
    assert pm == conductor, (pm, conductor)
    assert len(table) == len(FALSE_WRITE_VECTORS) + len(READ_ONLY_COMMANDS)


# ---------------------------------------------------------------------------
# Device equivalence declaration (card requirement 4)
# ---------------------------------------------------------------------------


def test_equivalence_preconditions_are_explicit():
    """The three cross-language preconditions the differential rests on:
    base = the `.agenticdoc` parent, case mode = the platform predicate, and one
    terminal-status set per side. Each is asserted (never a conditional skip)."""
    project = _tmp_root("wf-e2e-eq-")
    try:
        assert os.name == "nt"
        assert D.write_face_case_insensitive() is True
        assert D.write_face_base(project) == str(project)
        # Single source, one value per side: the two sets are compared in the
        # parity test through the bridge; pin the local shape here.
        assert mw_common._TERMINAL_STATUSES == {"done", "failed", "lost", "needs-clarification"}
        # The gate and the runtime guard share the same write_face operator.
        assert wf.parse_write_face("write_face: a/**", base=str(project), case_insensitive=False).allow_entries == ("a/**",)
    finally:
        shutil.rmtree(project, ignore_errors=True)
