"""test_mwds_t29_producer_signal.py — T-09/T-10 producer signal coverage.

mw-dispatch-card-gate T-09 closes the T-03 residual: T-03 decided *whether* to
judge a card from the card's own signal (a canonical heading or a
`card_path:` header), so the two producers that bypass the tool gate —
conductor direct writes and hand-written queue rows — were exempt by
construction (they simply omit the signal).

T-09 changes two things and this file pins both:

1. Generation side (`packages/multi-workers/autopilot/dispatch.py`): a
   card-backed conductor dispatch renders the T-02 shape — the canonical
   `## 上下文` / `## 要求` / `## 交付格式` triple plus the bare `card_path:` /
   `card_sha256:` header lines. The digest is the EOL-normalized sha256 and
   must agree with `mw_common.sha256_eol_normalized` and the TS leaf
   `shared/card-digest.ts` (three-way parity, driven through real node).
2. Service side (`packages/multi-workers/launcher.py`): the decision to judge
   is the queue row's creation time versus `ENVELOPE_ENFORCE_SINCE`. Before
   the boundary a historical dispatch is exempt; at/after it every row is
   judged regardless of signal — a post-boundary legacy card is refused.

The conductor output is also diffed against the real TS judge
(`inspectEnvelope` / `typeExtrasMissing`) exactly like the T-03 parity test,
so the two implementations cannot drift on the new producer.

T-10 (below, `TestUnconditionalInjection`) closes the residual: T-09's
card-only injection left the card-less auto dispatches (L3 review/repair,
roadmap-writer, phase-writer) without a signal, so the post-cutover service
gate refused them. `dispatch()` now synthesizes a non-empty canonical envelope
from the dispatch metadata for those, and the rendered output passes both the
Python judge and the real TS judge.
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
import mw_common  # noqa: E402
from autopilot import card_audit  # noqa: E402
from autopilot import dispatch  # noqa: E402

_HERMETIC_CONFIG = {
    "credentials": {"timi": {"sources": [{"env": "TIMI_API_KEY"}]}},
    "providers": {"timi": {"api_key_env": "TIMI_API_KEY", "credential": "timi"}},
}

# A complete coding envelope: the three canonical sections plus every coding
# extra, so `render_task_md(..., card=...)` output passes the full judge.
_CODING_CARD_TEXT = (
    "type: coding\n"
    "\n"
    "## 上下文\n"
    "\n"
    "背景：conductor 直写绕过工具层门禁，需要生成端注入同形态信封。\n"
    "\n"
    "## 要求\n"
    "\n"
    "实现 T-09 的生成端注入；AC-001 必须通过。\n"
    "写入允许面: packages/multi-workers/autopilot/dispatch.py\n"
    "写入禁止面: packages/coding-agent/**\n"
    "验收命令: python -X utf8 -m pytest packages/multi-workers/test_mwds_t29_producer_signal.py -q\n"
    "改动历史: trace.log 写入事件\n"
    "\n"
    "## 交付格式\n"
    "\n"
    "产物 packages/multi-workers/autopilot/dispatch.py + report.md。\n"
)

_LEGACY_CARD_TEXT = "type: coding\nDo something useful."


# ── poll harness (T-03 shape, reused) ────────────────────────────────────────

@pytest.fixture()
def providers(tmp_path: pathlib.Path) -> dict:
    p = tmp_path / "providers.json"
    p.write_text(json.dumps(_HERMETIC_CONFIG), encoding="utf-8")
    return launcher._load_providers(p)


@pytest.fixture()
def queue_file(tmp_path: pathlib.Path) -> pathlib.Path:
    agentic = tmp_path / ".agenticdoc"
    agentic.mkdir(exist_ok=True)
    return agentic / "_workers.parallel"


class _FakeProc:
    returncode = None

    def poll(self) -> None:
        return None


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
    monkeypatch.setenv("MW_AUTOPILOT_FILE", str(tmp_path / "absent-machine-config.json"))
    monkeypatch.setenv("TIMI_API_KEY", "test-timi-key")
    monkeypatch.setattr(launcher.shutil, "which", lambda name: str(tmp_path / "pi.CMD"))
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda cmd, **kw: _FakeProc())
    queue_file.write_text(mw_common.serialize_entry(entry) + "\n", encoding="utf-8")
    running: dict = {}
    launcher._poll_once(tmp_path, providers, running, {}, [], None)
    return running


def _refusal_for(tmp_path: pathlib.Path, text: str) -> str | None:
    card = _write_card(tmp_path, text)
    return launcher._envelope_refusal(_entry(card))


# ── 1. conductor generation side (dispatch.py) ───────────────────────────────

class TestConductorInjection:
    def test_render_task_md_card_envelope_passes_the_full_gate(
        self, tmp_path: pathlib.Path,
    ) -> None:
        """A card-backed render carries type + three sections + card lines and
        passes `_envelope_refusal` (sections AND type extras)."""
        card_file = tmp_path / "card.md"
        card_file.write_text(_CODING_CARD_TEXT, encoding="utf-8")
        digest = dispatch.card_digest(card_file)
        text = dispatch.render_task_md(
            "coding", _CODING_CARD_TEXT, loop="L", attempt=1,
            card={
                "path": "tasks/T-09.md",
                "sha256": digest,
                "context": "背景：conductor 直写绕过工具层门禁。",
                "requirements": _CODING_CARD_TEXT.split("## 要求", 1)[1],
                "deliverables": "产物 report.md。",
            },
        )
        assert "card_path: tasks/T-09.md" in text
        assert f"card_sha256: {digest}" in text
        assert "\n## 上下文\n" in text
        assert "\n## 要求\n" in text
        assert "\n## 交付格式\n" in text
        assert _refusal_for(tmp_path, text) is None, "conductor render must pass the gate"

    def test_dispatch_card_backed_is_t02_shaped(
        self, tmp_path: pathlib.Path,
    ) -> None:
        """The real conductor entry (`dispatch()`) resolves the execute-loop
        card `<key>/tasks/<stem>.md` and renders the T-02 shape.

        `phase-writer` is the actual EXECUTE-loop registry type; its card
        declares `type: coding`, but the task.md keeps the registry type (the
        worker's tool set is decided by it) and passes the extras check via
        the single-source vocabulary (T-07/P-08)."""
        card_dir = tmp_path / ".agenticdoc" / "k1" / "tasks"
        card_dir.mkdir(parents=True)
        (card_dir / "T-09.md").write_text(_CODING_CARD_TEXT, encoding="utf-8")
        result = dispatch.dispatch(
            tmp_path, "k1", "T-09", "phase-writer", "Do the task.",
            loop="exec:k1:T-09", attempt=1,
        )
        assert result.ok and result.task_md is not None
        text = result.task_md.read_text(encoding="utf-8")
        assert "type: phase-writer" in text
        assert "card_path: tasks/T-09.md" in text
        assert f"card_sha256: {mw_common.sha256_eol_normalized(card_dir / 'T-09.md')}" in text
        assert "\n## 上下文\n" in text and "\n## 要求\n" in text and "\n## 交付格式\n" in text
        assert launcher.type_extras_missing("phase-writer", text) == []
        entry = _entry(result.task_md, task_key=result.task_key)
        assert launcher._envelope_refusal(entry) is None

    def test_card_less_dispatch_is_enveloped(self, tmp_path: pathlib.Path) -> None:
        """T-10: a card-less auto dispatch no longer renders the bare prompt.

        The conductor synthesizes the canonical envelope from the dispatch
        metadata (never an empty skeleton), so the post-cutover service gate
        accepts it. The bare `card_path:`/`card_sha256:` lines stay card-only.
        """
        result = dispatch.dispatch(
            tmp_path, "k1", "l3-a1", "reviewer", "Review the evidence.",
            loop="l3:k1", attempt=1,
        )
        assert result.ok and result.task_md is not None
        text = result.task_md.read_text(encoding="utf-8")
        assert "card_path:" not in text and "card_sha256:" not in text
        assert "\n## 上下文\n" in text
        assert "\n## 要求\n" in text
        assert "\n## 交付格式\n" in text
        assert "Review the evidence." in text
        entry = _entry(result.task_md, task_key=result.task_key)
        assert launcher._envelope_refusal(entry) is None

    def test_card_backed_dispatch_content_comes_from_the_card(
        self, tmp_path: pathlib.Path,
    ) -> None:
        """T-10 requirement 4-②: a card-backed dispatch renders the card's own
        section bodies (not the synthesized ones)."""
        card_dir = tmp_path / ".agenticdoc" / "k1" / "tasks"
        card_dir.mkdir(parents=True)
        (card_dir / "T-09.md").write_text(_CODING_CARD_TEXT, encoding="utf-8")
        result = dispatch.dispatch(
            tmp_path, "k1", "T-09", "phase-writer", "Do the task.",
            loop="exec:k1:T-09", attempt=1,
        )
        assert result.task_md is not None
        text = result.task_md.read_text(encoding="utf-8")
        assert "背景：conductor 直写绕过工具层门禁" in text
        assert "实现 T-09 的生成端注入" in text
        assert "产物 packages/multi-workers/autopilot/dispatch.py" in text
        # The synthesized card-less context marker must not appear.
        assert "自动派发（无任务卡" not in text
        # section bodies are the card texts, extracted via the families rule
        sections = dispatch.extract_card_sections(_CODING_CARD_TEXT)
        assert sections["context"] in text
        assert sections["deliverables"] in text


# ── 1b. T-10 unconditional envelope (card-less auto dispatch) ────────────────

def _section_body(text: str, title: str) -> str:
    """Body of a `## <title>` section (up to the next `## ` heading)."""
    lines = text.splitlines()
    start = lines.index(f"## {title}")
    body: list[str] = []
    for line in lines[start + 1:]:
        if line.startswith("## "):
            break
        body.append(line)
    return "\n".join(body).strip()


class TestUnconditionalInjection:
    """T-10: the canonical envelope is injected for EVERY conductor dispatch,
    including the card-less auto dispatches (L3 review/repair, roadmap,
    phase-writer). Each section must be non-empty and pass the service gate."""

    @pytest.mark.parametrize(
        "task_type,stem,prompt,loop,attempt",
        [
            ("reviewer", "l3-a1", "L3 质检复评（key k1，第 1 轮）:\n- 审查证据", "l3:k1", 1),
            (
                "repair", "repair-a1",
                "修复 L3 裁决 below 的问题（key k1，第 1 轮）:\n- 首个 FAIL 行：x",
                "repair:k1", 1,
            ),
            (
                "roadmap-writer", "roadmap",
                "# Roadmap proposal: stage 1\n\n目标：交付。",
                "roadmap:stage-1", 1,
            ),
            ("phase-writer", "t-05", "Implement the change.", "exec:k1:t-05", 1),
        ],
    )
    def test_card_less_sections_are_non_empty_and_pass_the_gate(
        self,
        tmp_path: pathlib.Path,
        task_type: str,
        stem: str,
        prompt: str,
        loop: str,
        attempt: int,
    ) -> None:
        result = dispatch.dispatch(
            tmp_path, "k1", stem, task_type, prompt, loop=loop, attempt=attempt,
        )
        assert result.ok and result.task_md is not None
        text = result.task_md.read_text(encoding="utf-8")
        ok, missing, seen_type, detected = launcher.inspect_envelope(text)
        context = _section_body(text, "上下文")
        requirements = _section_body(text, "要求")
        deliverables = _section_body(text, "交付格式")
        print(
            f"[T-10 evidence] {task_type} card-less -> ok={ok} missing={missing} "
            f"type={seen_type} detected={detected} "
            f"section_bytes=({len(context)},{len(requirements)},{len(deliverables)})"
        )
        assert ok and missing == [], (task_type, missing)
        assert seen_type == task_type
        assert all(detected[s] for s in ("context", "requirements", "deliverables"))
        assert launcher.type_extras_missing(seen_type, text) == []
        assert context and requirements and deliverables
        assert f"type={task_type}" in context and f"loop={loop}" in context
        assert pathlib.Path(result.task_md).parent.name in context  # evidence path
        assert prompt.strip() in requirements
        assert "report.md" in deliverables
        assert launcher._envelope_refusal(
            _entry(result.task_md, task_key=result.task_key)
        ) is None

    def test_card_less_render_matches_the_ts_judge(self, tmp_path: pathlib.Path) -> None:
        """The card-less synthesized envelope must judge identically in the real
        TS judge (`inspectEnvelope` / `typeExtrasMissing`) and the Python mirror."""
        rendered = []
        for task_type, stem, prompt in (
            ("reviewer", "l3-a1", "L3 质检复评（key k1，第 1 轮）:\n- 审查证据"),
            ("repair", "repair-a1", "修复 L3 裁决 below 的问题（key k1，第 1 轮）:"),
            ("roadmap-writer", "roadmap", "# Roadmap proposal: stage 1\n\n目标：交付。"),
            ("phase-writer", "t-05", "Implement the change."),
        ):
            result = dispatch.dispatch(
                tmp_path, "k1", stem, task_type, prompt,
                loop=f"{task_type}:k1", attempt=1,
            )
            assert result.task_md is not None
            rendered.append(
                (task_type, result.task_md.read_text(encoding="utf-8"))
            )
        out = _run_ts({"cases": rendered, "digests": {}})
        assert len(out["verdicts"]) == len(rendered)
        for ts, (case_id, text) in zip(out["verdicts"], rendered):
            ok, missing, seen_type, _detected = launcher.inspect_envelope(text)
            py = {
                "id": case_id, "ok": ok, "missing": missing, "type": seen_type,
                "extras": launcher.type_extras_missing(seen_type, text),
            }
            assert py == ts, f"parity drift on {case_id!r}: python={py} ts={ts}"
            assert py["ok"] is True and py["missing"] == []

    def test_rendered_card_interoperates_with_the_t06_audit(
        self, tmp_path: pathlib.Path,
    ) -> None:
        # The injected `card_path` must be the normalized `tasks/<name>.md` form
        # the T-06 audit reads, and the digest must match its recipe (no phantom
        # `missing_cards`).
        card_dir = tmp_path / ".agenticdoc" / "k1" / "tasks"
        card_dir.mkdir(parents=True)
        card = card_dir / "T-09.md"
        card.write_text(_CODING_CARD_TEXT, encoding="utf-8")
        result = dispatch.dispatch(
            tmp_path, "k1", "T-09", "phase-writer", "do",
            loop="exec:k1:T-09", attempt=1,
        )
        assert result.task_md is not None
        assert card_audit.parse_card_path(result.task_md) == "tasks/T-09.md"
        assert dispatch.card_digest(card) == card_audit.card_digest(card)
        audit = card_audit.audit(tmp_path / ".agenticdoc", "k1")
        assert audit["missing_cards"] == []
        assert any(d["card"] == "tasks/T-09.md" for d in audit["dispatched"])

    def test_extract_card_sections_uses_families_with_a_fallback(self) -> None:
        sections = dispatch.extract_card_sections(_CODING_CARD_TEXT)
        assert "conductor 直写" in sections["context"]
        assert "T-09" in sections["requirements"]
        assert "report.md" in sections["deliverables"]
        # A card with a non-family heading: every section gets the body after
        # the first heading (T-02 fallback, content never dropped).
        fallback = dispatch.extract_card_sections("## Something else\n\nbody only\n")
        assert fallback == {
            "context": "body only", "requirements": "body only", "deliverables": "body only",
        }


# ── 2. service-side boundary (launcher.py) ───────────────────────────────────

class TestEnvelopeBoundary:
    def test_before_boundary_legacy_card_is_exempt(
        self, tmp_path: pathlib.Path, providers: dict, queue_file: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """早于边界 + 旧式卡 ⇒ 豁免（spawn，无 envelope missing）。"""
        card = _write_card(tmp_path, _LEGACY_CARD_TEXT)
        # T-12/F-03: the file mtime must not post-date the claimed row time,
        # so the fixture pins the historical time it is simulating.
        _set_mtime(card, "2026-08-14T00:00:00+00:00")
        early = _entry(card, dispatched_at="2026-08-14T00:00:00+00:00")
        running = _poll(tmp_path, providers, queue_file, monkeypatch, early)
        print(
            f"[T-09 evidence] early+legacy -> spawned={sorted(running)} "
            f"status={mw_common.parse_workers_file(queue_file)[0]['status']}"
        )
        assert "t001" in running
        assert mw_common.parse_workers_file(queue_file)[0]["status"] == "running"
        err = capsys.readouterr().err
        assert "envelope missing" not in err

    def test_at_boundary_legacy_card_without_signal_is_refused(
        self, tmp_path: pathlib.Path, providers: dict, queue_file: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """晚于边界 + 无信号 ⇒ 拒绝（同一张旧式卡，仅时间戳不同）。"""
        card = _write_card(tmp_path, _LEGACY_CARD_TEXT)
        late = _entry(card, dispatched_at="2026-10-12T00:00:00+00:00")
        running = _poll(tmp_path, providers, queue_file, monkeypatch, late)
        rows = mw_common.parse_workers_file(queue_file)
        err = capsys.readouterr().err
        print(
            f"[T-09 evidence] boundary+no-signal -> spawned={sorted(running)} "
            f"status={rows[0]['status']} reason={err.strip()}"
        )
        assert running == {}, "a post-boundary signal-less row must not spawn"
        assert rows[0]["status"] == "failed"
        log = (card.parent / "worker.log").read_text(encoding="utf-8")
        assert "[launcher] envelope missing:" in log
        assert str(card) in log

    def test_after_boundary_missing_section_is_refused(
        self, tmp_path: pathlib.Path, providers: dict, queue_file: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # canonical headings present but `## 交付格式` absent -> named missing.
        card_text = (
            "type: coding\n\n## 上下文\n\n动机。\n\n## 要求\n\nAC-001。\n"
            "写入允许面: a.py\n写入禁止面: b/**\n验收命令: pytest -q\n改动历史: trace.log\n"
        )
        card = _write_card(tmp_path, card_text)
        late = _entry(card, dispatched_at="2026-10-13T00:00:00+00:00")
        running = _poll(tmp_path, providers, queue_file, monkeypatch, late)
        assert running == {}
        assert mw_common.parse_workers_file(queue_file)[0]["status"] == "failed"
        log = (card.parent / "worker.log").read_text(encoding="utf-8")
        assert "交付格式" in log and str(card) in log

    def test_row_without_creation_timestamp_is_judged_and_stamped(
        self, tmp_path: pathlib.Path, providers: dict, queue_file: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # No dispatched_at: cannot prove the row is old -> fail-closed, and the
        # failure record carries the `created=` stamp (card requirement 2).
        card = _write_card(tmp_path, _LEGACY_CARD_TEXT)
        monkeypatch.setenv("MW_AUTOPILOT_FILE", str(tmp_path / "absent-machine-config.json"))
        monkeypatch.setenv("TIMI_API_KEY", "test-timi-key")
        monkeypatch.setattr(launcher.shutil, "which", lambda name: str(tmp_path / "pi.CMD"))
        monkeypatch.setattr(launcher.subprocess, "Popen", lambda cmd, **kw: _FakeProc())
        # 7-column row with empty timestamp cells (parse-stable, no creation time).
        queue_file.write_text(
            f"t001 | pending | pi | timi | {card} |  |  |  |\n", encoding="utf-8"
        )
        running: dict = {}
        launcher._poll_once(tmp_path, providers, running, {}, [], None)
        assert running == {}
        rows = mw_common.parse_workers_file(queue_file)
        assert rows[0]["status"] == "failed"
        log = (card.parent / "worker.log").read_text(encoding="utf-8")
        assert "envelope missing" in log
        assert "envelope created=" in log

    def test_enforced_helper_boundary_and_unknown_timestamp(self) -> None:
        assert launcher.ENVELOPE_ENFORCE_SINCE == "2026-10-12"
        assert launcher._envelope_enforced(
            {"dispatched_at": "2026-10-11T23:59:59+00:00"}
        ) is False
        assert launcher._envelope_enforced(
            {"dispatched_at": "2026-10-12T00:00:00+00:00"}
        ) is True
        assert launcher._envelope_enforced({"dispatched_at": "not-a-time"}) is True
        assert launcher._envelope_enforced({}) is True
        # T-12/F-03: `created` was a dead field (no parser/producer emits it),
        # so the branch is removed — `dispatched_at` alone decides, and a
        # post-boundary `dispatched_at` is judged even if a `created` key claims
        # otherwise.
        assert launcher._envelope_enforced(
            {"created": "2026-08-01T00:00:00+00:00", "dispatched_at": "2026-10-20T00:00:00+00:00"}
        ) is True
        # Z-suffixed (TS writer) timestamps parse identically.
        assert launcher._envelope_enforced({"dispatched_at": "2026-10-11T00:00:00Z"}) is False

    def test_enforced_helper_cross_checks_the_artifact(self, tmp_path: pathlib.Path) -> None:
        # T-12/F-03: a row timestamp that directly contradicts the task.md
        # cannot buy the historical exemption.
        legacy = _write_card(tmp_path, _LEGACY_CARD_TEXT)
        _set_mtime(legacy, "2026-08-14T00:00:00+00:00")
        # mtime == claimed time, pre-boundary -> exempt (the honest historical row)
        assert launcher._envelope_enforced(
            {"task_path": str(legacy), "dispatched_at": "2026-08-14T00:00:00+00:00"}
        ) is False
        # mtime later than the claimed time -> judged
        assert launcher._envelope_enforced(
            {"task_path": str(legacy), "dispatched_at": "2026-08-01T00:00:00+00:00"}
        ) is True

        # A canonical G-2 task.md is judged even when both timestamps claim 2026-08.
        canonical = _write_card(
            tmp_path,
            "type: coding\n\n## 上下文\n\n动机。\n\n## 要求\n\nAC-001。\n\n## 交付格式\n\nreport.md。\n",
            key="t002",
        )
        _set_mtime(canonical, "2026-08-14T00:00:00+00:00")
        assert launcher.has_canonical_envelope(canonical.read_text(encoding="utf-8")) is True
        assert launcher._envelope_enforced(
            {"task_path": str(canonical), "dispatched_at": "2026-08-14T00:00:00+00:00"}
        ) is True

        # A post-boundary legacy row is judged on the time axis alone.
        late = _write_card(tmp_path, _LEGACY_CARD_TEXT, key="t003")
        _set_mtime(late, "2026-10-13T00:00:00+00:00")
        assert launcher._envelope_enforced(
            {"task_path": str(late), "dispatched_at": "2026-10-13T00:00:00+00:00"}
        ) is True


# ── 3. TS judge parity + digest three-way parity ─────────────────────────────

_TS_DIR = (
    pathlib.Path(__file__).resolve().parents[1]
    / "coding-agent/src/extensions/agent-team-loop/shared"
)
_TS_CARD = _TS_DIR / "dispatch-card.ts"
_TS_DIGEST = _TS_DIR / "card-digest.ts"

_TS_SCRIPT = r"""
const fs = require("node:fs");
const { pathToFileURL } = require("node:url");
(async () => {
  const card = await import(pathToFileURL(process.env.MW_T29_CARD_MODULE).href);
  const digest = await import(pathToFileURL(process.env.MW_T29_DIGEST_MODULE).href);
  const cases = JSON.parse(fs.readFileSync(process.env.MW_T29_CASES, "utf8"));
  const verdicts = cases.map(([id, text]) => {
    const e = card.inspectEnvelope(text);
    return { id, ok: e.ok, missing: e.missing, type: e.type,
             extras: card.typeExtrasMissing(e.type, text) };
  });
  const digests = Object.fromEntries(
    Object.entries(JSON.parse(process.env.MW_T29_DIGESTS)).map(([k, p]) => [k, digest.cardDigest(p)])
  );
  process.stdout.write("T29_JSON_BEGIN" + JSON.stringify({ verdicts, digests }) + "T29_JSON_END");
})().catch((err) => { console.error(err); process.exit(1); });
"""


def _run_ts(payload: dict) -> dict:
    node = shutil.which("node")
    if node is None:
        pytest.fail("node interpreter not found; TS parity cannot be measured (fail-closed, P-016)")
    if not _TS_CARD.is_file() or not _TS_DIGEST.is_file():
        pytest.fail(f"TS mirror missing under {_TS_DIR} (fail-closed)")
    with tempfile.TemporaryDirectory() as tmp:
        cases_path = pathlib.Path(tmp) / "cases.json"
        cases_path.write_text(json.dumps(payload["cases"]), encoding="utf-8")
        env = dict(os.environ)
        env["MW_T29_CARD_MODULE"] = str(_TS_CARD)
        env["MW_T29_DIGEST_MODULE"] = str(_TS_DIGEST)
        env["MW_T29_CASES"] = str(cases_path)
        env["MW_T29_DIGESTS"] = json.dumps(payload["digests"])
        proc = subprocess.run(
            [node, "--experimental-strip-types", "-e", _TS_SCRIPT],
            capture_output=True, text=True, timeout=180, env=env,
        )
    if proc.returncode != 0 or "T29_JSON_BEGIN" not in proc.stdout:
        pytest.fail(
            f"node TS parity harness failed (exit {proc.returncode}):\n"
            f"stdout:\n{proc.stdout[-2000:]}\nstderr:\n{proc.stderr[-2000:]}"
        )
    body = proc.stdout.split("T29_JSON_BEGIN", 1)[1].split("T29_JSON_END", 1)[0].strip()
    return json.loads(body)


class TestParity:
    def test_python_judge_matches_the_real_ts_judge(self, tmp_path: pathlib.Path) -> None:
        card_file = tmp_path / "card.md"
        card_file.write_text(_CODING_CARD_TEXT, encoding="utf-8")
        rendered = dispatch.render_task_md(
            "vision", _CODING_CARD_TEXT, loop="L", attempt=1,
            card={
                "path": "tasks/T-09.md",
                "sha256": dispatch.card_digest(card_file),
                "context": "背景。",
                "requirements": "AC-001 必须通过。",
                "deliverables": "产物 report.md。",
            },
        )
        cases = [("conductor-render", rendered), ("legacy", _LEGACY_CARD_TEXT)]
        out = _run_ts({"cases": cases, "digests": {}})
        assert len(out["verdicts"]) == len(cases)
        for ts, (case_id, text) in zip(out["verdicts"], cases):
            ok, missing, task_type, _detected = launcher.inspect_envelope(text)
            py = {
                "id": case_id, "ok": ok, "missing": missing, "type": task_type,
                "extras": launcher.type_extras_missing(task_type, text),
            }
            assert py == ts, f"parity drift on {case_id!r}: python={py} ts={ts}"

    def test_card_digest_three_way_and_crlf_equivalent(self, tmp_path: pathlib.Path) -> None:
        lf = tmp_path / "card-lf.md"
        lf.write_text(_CODING_CARD_TEXT, encoding="utf-8", newline="\n")
        crlf = tmp_path / "card-crlf.md"
        crlf.write_bytes(_CODING_CARD_TEXT.replace("\n", "\r\n").encode("utf-8"))

        py_lf = mw_common.sha256_eol_normalized(lf)
        py_crlf = mw_common.sha256_eol_normalized(crlf)
        assert py_lf == py_crlf, "the EOL recipe must fold CRLF to LF"

        out = _run_ts({"cases": [], "digests": {"lf": str(lf), "crlf": str(crlf)}})
        assert out["digests"]["lf"] == py_lf
        assert out["digests"]["crlf"] == py_lf
        # dispatch.card_digest is the same recipe (the three-way agreement).
        assert dispatch.card_digest(lf) == py_lf
