"""test_mwds_t27_service_envelope.py — G-3 service-layer envelope fallback.

mw-dispatch-card-gate T-03: the launcher poll is the only queue consumer that
sees all four dispatch producers (dispatch_worker, /worker, conductor direct
writes, hand-written rows), so it re-checks the dispatch envelope before
`_spawn`. A non-compliant card is never spawned, is never silently archived,
and leaves the reason `[launcher] envelope missing: <items> (<path>)` in the
task's worker.log.

The judge is a Python mirror of the frozen TS leaf
(`packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-card.ts`,
T-01). "Same judgement" is a measured fact, not a comment: the parity class
below drives the real TS module through node and diffs the verdict entry by
entry (fail-closed when node is missing, per the repo P-016 convention).

Migration rule (design P-03/P-07): only envelope-declaring cards (G-2 canonical
heading or a `card_path:` header) are judged — a legacy task.md passes through
untouched, so the historical corpus is never failed retroactively.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import datetime

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import launcher  # noqa: E402
from launcher import (  # noqa: E402
    CODING_EXTRA_SECTIONS,
    ENVELOPE_SECTIONS,
    TYPE_EXTRA_SECTIONS,
    TYPES_WITHOUT_EXTRA_RULES,
    _load_providers,
    _parse_workers_file,
    _poll_once,
    _serialize_entry,
    inspect_envelope,
    type_extras_missing,
)

_HERMETIC_CONFIG = {
    "credentials": {"timi": {"sources": [{"env": "TIMI_API_KEY"}]}},
    "providers": {"timi": {"api_key_env": "TIMI_API_KEY", "credential": "timi"}},
}


@pytest.fixture()
def providers(tmp_path: pathlib.Path) -> dict:
    p = tmp_path / "providers.json"
    p.write_text(json.dumps(_HERMETIC_CONFIG), encoding="utf-8")
    return _load_providers(p)


@pytest.fixture()
def queue_file(tmp_path: pathlib.Path) -> pathlib.Path:
    agentic = tmp_path / ".agenticdoc"
    agentic.mkdir(exist_ok=True)
    return agentic / "_workers.parallel"


class _FakeProc:
    returncode = None

    def poll(self) -> None:
        return None


def _machine_config_off(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MW_AUTOPILOT_FILE", str(tmp_path / "absent-machine-config.json"))


def _write_card(tmp_path: pathlib.Path, text: str, key: str = "t001") -> pathlib.Path:
    d = tmp_path / ".agenticdoc" / "test-key" / "workers" / key
    d.mkdir(parents=True, exist_ok=True)
    card = d / "task.md"
    card.write_text(text, encoding="utf-8")
    return card


def _set_mtime(path: pathlib.Path, iso: str) -> None:
    """Pin a fixture's mtime so the T-12/F-03 boundary cross-check is explicit."""
    ts = datetime.datetime.fromisoformat(iso).replace(tzinfo=datetime.timezone.utc).timestamp()
    os.utime(path, (ts, ts))


def _entry(task_path: pathlib.Path, **overrides: str) -> dict[str, str]:
    # T-09 boundary fixture: the default row is created AT the cutover
    # (ENVELOPE_ENFORCE_SINCE = 2026-10-12), so the refusal tests below are
    # judged regardless of the card's signal. The one legacy-exemption case
    # overrides `dispatched_at` to a pre-boundary timestamp (fixture data, not
    # a loosened criterion).
    entry = {
        "cli": "pi", "provider": "timi", "task_path": str(task_path),
        "task_key": "t001", "status": "pending",
        "dispatched_at": "2026-10-12T00:00:00+00:00",
        "updated_at": "2026-10-12T00:00:00+00:00",
        "model": "",
    }
    entry.update(overrides)
    return entry


def _poll(
    tmp_path: pathlib.Path,
    providers: dict,
    queue_file: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    entry: dict[str, str],
) -> dict:
    _machine_config_off(tmp_path, monkeypatch)
    monkeypatch.setenv("TIMI_API_KEY", "test-timi-key")
    monkeypatch.setattr(launcher.shutil, "which", lambda name: str(tmp_path / "pi.CMD"))
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda cmd, **kw: _FakeProc())
    queue_file.write_text(_serialize_entry(entry) + "\n", encoding="utf-8")
    running: dict = {}
    _poll_once(tmp_path, providers, running, {}, [], None)
    return running


_HEADER = "type: coding\nphase: EXECUTE\n"
_EXTRAS = (
    "写入允许面: packages/multi-workers/x.py\n"
    "写入禁止面: packages/coding-agent/**\n"
    "验收命令: python -X utf8 -m pytest packages/multi-workers/x.py -q\n"
    "改动历史: trace.log 写入事件\n"
)
_CONTEXT = "\n## 上下文\n背景：本卡说明为什么做。\n"
_REQUIREMENTS = "\n## 要求\n实现 X；AC-001 必须通过。\n"
_DELIVERABLES = "\n## 交付格式\n产物 packages/multi-workers/x.py。\n"


def _assert_refused(
    tmp_path: pathlib.Path,
    providers: dict,
    queue_file: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    card_text: str,
    expect_items: list[str],
) -> str:
    card = _write_card(tmp_path, card_text)
    running = _poll(tmp_path, providers, queue_file, monkeypatch, _entry(card))

    assert running == {}, "non-compliant card must never spawn"
    rows = _parse_workers_file(queue_file)
    assert len(rows) == 1
    assert rows[0]["status"] == "failed"
    # Envelope refusals are terminal rows, never silent stale-archive entries.
    stale = tmp_path / ".agenticdoc" / "_workers.stale.parallel"
    assert not stale.exists(), "envelope refusal must not use the stale archive"

    log = (card.parent / "worker.log").read_text(encoding="utf-8")
    assert "[launcher] envelope missing:" in log
    assert f"({card})" in log
    for item in expect_items:
        assert item in log, f"reason must name the missing item {item!r}: {log!r}"
    return log


class TestServiceEnvelopeFallback:
    def test_missing_section_refused(
        self, tmp_path: pathlib.Path, providers: dict, queue_file: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # 缺段: canonical headings present, deliverables section absent.
        log = _assert_refused(
            tmp_path, providers, queue_file, monkeypatch,
            _HEADER + _CONTEXT + _REQUIREMENTS + "\n" + _EXTRAS,
            ["交付格式"],
        )
        items = log.split("envelope missing:", 1)[1].split("(", 1)[0]
        assert "上下文" not in items
        assert "要求" not in items

    def test_missing_type_refused(
        self, tmp_path: pathlib.Path, providers: dict, queue_file: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # 缺 type: — sections and extras are complete, only the header is gone.
        _assert_refused(
            tmp_path, providers, queue_file, monkeypatch,
            _CONTEXT + _REQUIREMENTS + _DELIVERABLES + "\n" + _EXTRAS,
            ["type:"],
        )

    def test_missing_type_extras_refused(
        self, tmp_path: pathlib.Path, providers: dict, queue_file: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # 缺类型附加项: coding card without write surface / acceptance / history.
        _assert_refused(
            tmp_path, providers, queue_file, monkeypatch,
            _HEADER + _CONTEXT + _REQUIREMENTS + _DELIVERABLES,
            ["写入允许面", "写入禁止面", "验收命令", "改动历史"],
        )

    def test_unknown_type_refused(
        self, tmp_path: pathlib.Path, providers: dict, queue_file: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _assert_refused(
            tmp_path, providers, queue_file, monkeypatch,
            "type: bogus\nphase: EXECUTE\n" + _CONTEXT + _REQUIREMENTS + _DELIVERABLES,
            ["unknown-type:bogus"],
        )

    def test_card_path_header_opts_into_the_contract(
        self, tmp_path: pathlib.Path, providers: dict, queue_file: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # A `card_path:` header opts a card into the contract even without a
        # canonical G-2 heading (the T-06 tracking header).
        _assert_refused(
            tmp_path, providers, queue_file, monkeypatch,
            "type: coding\ncard_path: .agenticdoc/test-key/tasks/T-01.md\nBody only.\n",
            ["上下文", "要求", "交付格式", "写入允许面"],
        )

    def test_compliant_card_spawns(
        self, tmp_path: pathlib.Path, providers: dict, queue_file: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        card = _write_card(
            tmp_path, _HEADER + _CONTEXT + _REQUIREMENTS + _DELIVERABLES + "\n" + _EXTRAS
        )
        running = _poll(tmp_path, providers, queue_file, monkeypatch, _entry(card))

        assert "t001" in running, "a compliant envelope must spawn"
        rows = _parse_workers_file(queue_file)
        assert rows[0]["status"] == "running"
        log_path = card.parent / "worker.log"
        assert not log_path.exists() or "envelope missing" not in log_path.read_text(
            encoding="utf-8"
        )

    def test_legacy_card_without_envelope_still_spawns(
        self, tmp_path: pathlib.Path, providers: dict, queue_file: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Migration rule (P-03/P-07): a pre-cutover row is exempt no matter
        # what its card looks like — the boundary is the row's creation time,
        # not the card's shape (T-09). T-12/F-03: the task.md mtime must not be
        # later than the claimed row time, so the fixture pins both together.
        card = _write_card(tmp_path, "type: coding\nDo something useful.")
        _set_mtime(card, "2026-08-14T00:00:00+00:00")
        early = _entry(card, dispatched_at="2026-08-14T00:00:00+00:00")
        running = _poll(tmp_path, providers, queue_file, monkeypatch, early)

        assert "t001" in running
        assert _parse_workers_file(queue_file)[0]["status"] == "running"

    def test_missing_task_md_keeps_stale_semantics_with_a_logged_reason(
        self, tmp_path: pathlib.Path, providers: dict, queue_file: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        # Requirement 3: the missing task.md path (not an envelope problem)
        # keeps the existing stale archive, but must no longer be silent.
        missing = tmp_path / ".agenticdoc" / "test-key" / "workers" / "t001" / "task.md"
        running = _poll(tmp_path, providers, queue_file, monkeypatch, _entry(missing))

        assert running == {}
        assert _parse_workers_file(queue_file) == []
        stale = (tmp_path / ".agenticdoc" / "_workers.stale.parallel").read_text(encoding="utf-8")
        assert "t001" in stale
        err = capsys.readouterr().err
        assert "archived stale (task.md not found): t001" in err


class TestBoundaryCrossCheck:
    """T-12/F-03: the row timestamps alone are hand-writable, so the boundary
    decision is cross-checked against the artifact before granting the
    historical exemption."""

    def test_task_md_mtime_after_row_timestamp_is_judged(
        self, tmp_path: pathlib.Path, providers: dict, queue_file: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # A task.md written AFTER the claimed dispatch time cannot be that old
        # row -> the timestamp is not trusted, the row is judged.
        card = _write_card(tmp_path, "type: coding\nDo something useful.")
        _set_mtime(card, "2026-10-13T00:00:00+00:00")
        early = _entry(card, dispatched_at="2026-08-14T00:00:00+00:00")
        running = _poll(tmp_path, providers, queue_file, monkeypatch, early)

        assert running == {}
        rows = _parse_workers_file(queue_file)
        assert rows[0]["status"] == "failed"
        log = (card.parent / "worker.log").read_text(encoding="utf-8")
        assert "[launcher] envelope missing:" in log

    def test_canonical_task_md_is_judged_despite_an_old_timestamp(
        self, tmp_path: pathlib.Path, providers: dict, queue_file: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # The G-2 headings prove a current generator wrote the file, so the
        # row is judged even though the row and the file both claim 2026-08.
        # The card is deliberately incomplete (no 交付格式), so "judged" and
        # "refused" are the same observation.
        card_text = (
            "type: coding\n\n## 上下文\n\n动机。\n\n## 要求\n\nAC-001。\n"
            "写入允许面: a.py\n写入禁止面: b/**\n验收命令: pytest -q\n改动历史: trace.log\n"
        )
        card = _write_card(tmp_path, card_text)
        _set_mtime(card, "2026-08-14T00:00:00+00:00")
        early = _entry(card, dispatched_at="2026-08-14T00:00:00+00:00")
        running = _poll(tmp_path, providers, queue_file, monkeypatch, early)

        assert running == {}
        assert _parse_workers_file(queue_file)[0]["status"] == "failed"
        log = (card.parent / "worker.log").read_text(encoding="utf-8")
        assert "envelope missing" in log and "交付格式" in log


class TestEnvelopeJudge:
    """The wide (T1e) judge: heading-with-body OR paragraph-semantic fallback."""

    def test_canonical_card_is_complete(self) -> None:
        ok, missing, task_type, detected = inspect_envelope(
            _HEADER + _CONTEXT + _REQUIREMENTS + _DELIVERABLES + "\n" + _EXTRAS
        )
        assert ok is True
        assert missing == []
        assert task_type == "coding"
        assert detected["context"] == "heading:上下文"
        assert detected["requirements"] == "heading:要求"
        assert detected["deliverables"] == "heading:交付格式"

    def test_wide_heading_variants_and_numbering(self) -> None:
        text = (
            "type: research\n\n## 1. 目标\n\n现状与动机。\n\n"
            "## (2) 验收标准\n\n必须做到。\n\n## A. 预期产出\n\nevidence/only.md。\n"
        )
        ok, _missing, _t, detected = inspect_envelope(text)
        assert ok is True
        assert detected["context"] == "heading:目标"
        assert detected["requirements"] == "heading:验收标准"
        assert detected["deliverables"] == "heading:预期产出"

    def test_empty_heading_body_does_not_count(self) -> None:
        text = "type: coding\n\n## 上下文\n\n## 要求\n\nAC-001 成立。\n\n## 交付格式\n\n产物 report.md。\n"
        ok, missing, _t, detected = inspect_envelope(text)
        assert ok is False
        assert missing == ["context"]
        assert detected["context"] == ""

    def test_semantics_and_bullet_labels_detect_a_headingless_card(self) -> None:
        semantics = inspect_envelope(
            "type: research\n\n因为历史卡常无标题。\n\n判据 AC-007 成立。\n\n产物 report.md。\n"
        )
        assert semantics[0] is True
        assert semantics[3] == {
            "context": "semantics", "requirements": "semantics", "deliverables": "semantics",
        }
        bullets = inspect_envelope(
            "type: research\n\n- 背景: 无标题键值卡\n- 验收: 判据成立\n- 交付: report.md\n"
        )
        assert bullets[0] is True
        assert bullets[3]["deliverables"] == "semantics"

    def test_inline_pm_type_conventions(self) -> None:
        assert inspect_envelope("- Key: k｜Wave: 1｜type: coding\n\n## 上下文\n\n动机。\n")[2] == "coding"
        assert inspect_envelope("> key: k | type: review | deps: -\n\n## 上下文\n\n动机。\n")[2] == "review"

    def test_bom_and_crlf_are_equivalent(self) -> None:
        base = _HEADER + _CONTEXT + _REQUIREMENTS + _DELIVERABLES + "\n" + _EXTRAS
        assert inspect_envelope("\ufeff" + base) == inspect_envelope(base)
        assert inspect_envelope(base.replace("\n", "\r\n")) == inspect_envelope(base)

    def test_type_extras_for_each_role(self) -> None:
        assert CODING_EXTRA_SECTIONS == ("写入允许面", "写入禁止面", "验收命令", "改动历史")
        assert TYPE_EXTRA_SECTIONS["research"] == ("唯一证据文件",)
        assert TYPE_EXTRA_SECTIONS["review"] == ("审计目标", "未覆盖面声明")
        # Known roles without T-01 extra rules pass rather than go unknown.
        for role in TYPES_WITHOUT_EXTRA_RULES:
            assert type_extras_missing(role, "") == []
        # T-07/P-08: the in-use runtime roles are in the single-source dispatch
        # vocabulary, so the extras check passes them (never names them
        # unknown); only a genuinely unknown value is named.
        for role in ("verifier", "phase-writer", "reviewer", "repair", "roadmap-writer", "codex"):
            assert type_extras_missing(role, "") == []
        assert type_extras_missing("bogus", "") == ["unknown-type:bogus"]

    def test_missing_type_extras_names_every_gap(self) -> None:
        text = _HEADER + _CONTEXT + _REQUIREMENTS + _DELIVERABLES
        assert type_extras_missing("coding", text) == [
            "写入允许面", "写入禁止面", "验收命令", "改动历史",
        ]
        complete = text + "\n" + _EXTRAS
        assert type_extras_missing("coding", complete) == []

    def test_legacy_shape_is_not_envelope_declaring(self) -> None:
        assert not launcher._envelope_declaring("type: coding\nDo something useful.")
        assert launcher._envelope_declaring("## 上下文\nx\n")
        assert launcher._envelope_declaring("card_path: tasks/T-01.md\n")


# ── Cross-language parity (P-04): real TS judge via node ──────────────────────

_TS_MODULE = (
    pathlib.Path(__file__).resolve().parents[1]
    / "coding-agent/src/extensions/agent-team-loop/shared/dispatch-card.ts"
)

_TS_SCRIPT = r"""
const fs = require("node:fs");
const { pathToFileURL } = require("node:url");
(async () => {
  const mod = await import(pathToFileURL(process.env.MW_T03_TS_MODULE).href);
  const cases = JSON.parse(fs.readFileSync(process.env.MW_T03_CASES, "utf8"));
  const out = cases.map(([id, text]) => {
    const e = mod.inspectEnvelope(text);
    return {
      id,
      ok: e.ok,
      missing: e.missing,
      type: e.type,
      detected: e.detected,
      extras: mod.typeExtrasMissing(e.type, text),
    };
  });
  process.stdout.write("T03_JSON_BEGIN" + JSON.stringify(out) + "T03_JSON_END");
})().catch((err) => { console.error(err); process.exit(1); });
"""

_PARITY_CASES: list[tuple[str, str]] = [
    ("compliant", _HEADER + _CONTEXT + _REQUIREMENTS + _DELIVERABLES + "\n" + _EXTRAS),
    ("missing-context", "type: coding\n" + _REQUIREMENTS + _DELIVERABLES),
    ("missing-requirements", "type: coding\n" + _CONTEXT + _DELIVERABLES),
    ("missing-deliverables", "type: coding\n" + _CONTEXT + _REQUIREMENTS),
    ("empty-context-body", "type: coding\n\n## 上下文\n\n## 要求\n\nAC-1。\n\n## 交付格式\n\nreport.md。\n"),
    ("missing-type", _CONTEXT + _REQUIREMENTS + _DELIVERABLES),
    ("empty-card", ""),
    ("bom", "\ufeff" + _HEADER + _CONTEXT + _REQUIREMENTS + _DELIVERABLES),
    ("crlf", (_HEADER + _CONTEXT + _REQUIREMENTS + _DELIVERABLES).replace("\n", "\r\n")),
    ("heading-variant", "type: coding\n\n## 目标\n\n动机。\n\n## 验收标准\n\nAC-1。\n\n## 预期产出\n\nreport.md。\n"),
    ("numbering", "type: coding\n\n## 1. 上下文\n\n动机。\n\n## (2) 要求\n\nAC-1。\n\n## A. 交付格式\n\nreport.md。\n"),
    ("h3", "type: coding\n\n### 上下文\n\n动机。\n\n### 要求\n\nAC-1。\n\n### 交付格式\n\nreport.md。\n"),
    ("semantics", "type: research\n\n因为历史卡常无标题。\n\n判据 AC-007 成立。\n\n产物 report.md。\n"),
    ("bullets", "type: research\n\n- 背景: 无标题键值卡\n- 验收: 判据成立\n- 交付: report.md\n"),
    ("inline-bullet-type", "- Key: k｜Wave: 1｜type: coding\n\n## 上下文\n\n动机。\n\n## 要求\n\nAC-1。\n\n## 交付格式\n\nreport.md。\n"),
    ("inline-quote-type", "> key: k | type: review | deps: -\n\n## 上下文\n\n动机。\n\n## 要求\n\nAC-1。\n\n## 交付格式\n\nreport.md。\n"),
    ("body-type-ignored", "type: coding\n\n## 上下文\n\n正文里写着 type: review 一行。\n\n## 要求\n\nAC-1。\n\n## 交付格式\n\nreport.md。\n"),
    ("legacy", "type: coding\nDo something useful."),
    ("coding-extras-partial", "type: coding\n\n## 上下文\n\n动机。\n\n## 要求\n\nAC-1。\n\n## 交付格式\n\nreport.md。\n\n## 写入允许面\n\n仅 x.py。\n\n## 写入禁止面\n\npm/**。\n\n## 改动历史\n\ntrace.log。\n"),
    ("coding-write-scope", "---\ntype: coding\nwrite_scope: .agenticdoc/k/workers/t\n---\n\n## 上下文\n\n动机。\n\n## 要求\n\nAC-1。\n\n## 交付格式\n\nreport.md。\n\n## 写入禁止面\n\n不得写 pm/**。\n\n## 验收命令\n\nnode x.test.ts\n\n## 改动历史\n\ntrace.log。\n"),
    ("research-missing-extra", "type: research\n\n## 上下文\n\n动机。\n\n## 要求\n\nAC-1。\n\n## 交付格式\n\nevidence/only.md。\n"),
    ("review-partial", "type: review\n\n## 上下文\n\n动机。\n\n## 要求\n\nAC-1。\n\n## 交付格式\n\nreport.md。\n\n## 审计目标\n\n要回答：投递链是否读卡。\n"),
    ("unknown-type", "type: verifier\n\n## 上下文\n\n动机。\n\n## 要求\n\nAC-1。\n\n## 交付格式\n\nreport.md。\n"),
    ("vision-no-extras", "type: vision\n\n## 上下文\n\n动机。\n\n## 要求\n\nAC-1。\n\n## 交付格式\n\nreport.md。\n"),
    ("rag-research-no-extras", "type: rag-research\n\n## 上下文\n\n动机。\n\n## 要求\n\nAC-1。\n\n## 交付格式\n\nreport.md。\n"),
]


def _run_ts_parity(cases: list[tuple[str, str]]) -> list[dict]:
    node = shutil.which("node")
    if node is None:
        pytest.fail("node interpreter not found; TS parity cannot be measured (fail-closed, P-016)")
    if not _TS_MODULE.is_file():
        pytest.fail(f"TS mirror missing: {_TS_MODULE} (fail-closed)")
    with tempfile.TemporaryDirectory() as tmp:
        cases_path = pathlib.Path(tmp) / "cases.json"
        cases_path.write_text(json.dumps(cases), encoding="utf-8")
        env = dict(os.environ)
        env["MW_T03_TS_MODULE"] = str(_TS_MODULE)
        env["MW_T03_CASES"] = str(cases_path)
        proc = subprocess.run(
            [node, "--experimental-strip-types", "-e", _TS_SCRIPT],
            capture_output=True, text=True, timeout=180, env=env,
        )
    if proc.returncode != 0 or "T03_JSON_BEGIN" not in proc.stdout:
        pytest.fail(
            f"node TS parity harness failed (exit {proc.returncode}):\n"
            f"stdout:\n{proc.stdout[-2000:]}\nstderr:\n{proc.stderr[-2000:]}"
        )
    payload = proc.stdout.split("T03_JSON_BEGIN", 1)[1].split("T03_JSON_END", 1)[0].strip()
    return json.loads(payload)


class TestCrossLanguageParity:
    def test_python_mirror_matches_the_real_ts_judge(self) -> None:
        ts_rows = _run_ts_parity(_PARITY_CASES)
        assert len(ts_rows) == len(_PARITY_CASES)
        for ts, (case_id, text) in zip(ts_rows, _PARITY_CASES):
            ok, missing, task_type, detected = inspect_envelope(text)
            py = {
                "id": case_id, "ok": ok, "missing": missing,
                "type": task_type, "detected": detected,
                "extras": type_extras_missing(task_type, text),
            }
            assert py == ts, f"parity drift on case {case_id!r}: python={py} ts={ts}"

    def test_node_missing_is_fail_not_skip(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(shutil, "which", lambda _name: None)
        with pytest.raises(pytest.fail.Exception):
            _run_ts_parity([("x", "")])


class TestEnvelopeConstantsArePinned:
    """The mirror's vocabulary/thresholds are fixed here so drift fails."""

    def test_sections_and_labels_are_the_frozen_sets(self) -> None:
        assert ENVELOPE_SECTIONS == ("context", "requirements", "deliverables")
        assert launcher.ENVELOPE_SECTION_LABELS == {
            "context": "上下文", "requirements": "要求", "deliverables": "交付格式",
        }
