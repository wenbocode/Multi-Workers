"""
test_mwoc_s2_sections.py — T-06 (AC-002 producer half / AC-003): the
`## 交付段契约（本角色）` checklist injected into a card-backed task.md.

Design §4.4 / spec §1.6 S2: before the worker starts, the derived `task.md`
must carry the role's recovery-contract section list, each section given as a
copyable `## <段名>`, so the worker learns the required sections up front
instead of being stopped at settle with `missing section(s): …`. The injection
is producer-side (`autopilot/dispatch.py::_envelope_card_body`) and belongs to
the card-backed branch only, so a legacy `card=None` render stays byte-for-byte
unchanged.

Single source (requirement 3, option **b**): the section names live in the TS
write-side contract `worker/output-sections.ts` (`RECOVERY_SECTIONS` /
`RECOVERY_TYPE_SECTIONS`). Python cannot import a TS module, so
`dispatch.RECOVERY_SECTIONS` / `dispatch.RECOVERY_TYPE_SECTIONS` are a verbatim
mirror and `test_recovery_tables_match_the_ts_source` parses the real TS source
text and fails on any drift (fail-closed when the file is missing, P-016). A
runtime TS parse was rejected: it would couple every dispatch of a deployed
Python bundle to a source file that is not shipped with it, and the mirror +
parity test is the pattern `test_task_type_parity.py` already establishes.

Run: cd packages/multi-workers && python -X utf8 -m pytest -q test_mwoc_s2_sections.py
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

import pytest

_HERE = pathlib.Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
sys.path.insert(0, str(_HERE))

import launcher  # noqa: E402
from autopilot import dispatch  # noqa: E402

OWNER = "woc-t06"

#: The TS write-side recovery contract this module's mirror is locked against.
TS_SOURCE = (
    _REPO
    / "packages"
    / "coding-agent"
    / "src"
    / "extensions"
    / "agent-team-loop"
    / "worker"
    / "output-sections.ts"
)

#: The TS envelope judge this producer must keep satisfying (requirement 5).
TS_CARD_MODULE = (
    _REPO
    / "packages"
    / "coding-agent"
    / "src"
    / "extensions"
    / "agent-team-loop"
    / "shared"
    / "dispatch-card.ts"
)

CARD_TEMPLATE = (
    "type: {task_type}\n\n"
    "## 背景\n\n动机：{task_type} 卡。\n\n"
    "## 要求\n\nAC-003 必须通过。\n\n"
    "## 交付物\n\nreport.md / output.md。\n"
)

#: Card-declared report roles + the writable internal conductor roles that
#: produce report products (injected), versus the internal / out-of-scope
#: roles that must stay uninjected (requirement 2).
CONTRACT_TYPES = (
    "coding", "research", "review", "phase-writer", "roadmap-writer",
)
NON_CONTRACT_TYPES = (
    "vision", "rag-research", "verifier", "reviewer", "repair",
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _true(value: bool) -> str:
    return "true" if value else "false"


def _write_card(tmp_path: pathlib.Path, task_type: str, stem: str, body: str = "") -> None:
    card_dir = tmp_path / ".agenticdoc" / OWNER / "tasks"
    card_dir.mkdir(parents=True, exist_ok=True)
    (card_dir / f"{stem}.md").write_text(
        CARD_TEMPLATE.format(task_type=task_type) + body,
        encoding="utf-8",
        newline="\n",
    )


def _card(tmp_path: pathlib.Path, task_type: str, stem: str = "T-06") -> dict:
    """Resolve a card through the real `dispatch_card` path (never hand-built)."""
    _write_card(tmp_path, task_type, stem)
    card = dispatch.dispatch_card(tmp_path, OWNER, stem)
    assert card is not None, "real dispatch_card path must resolve the card"
    return card


def _render(tmp_path: pathlib.Path, task_type: str, stem: str = "T-06", card: dict | None = None) -> str:
    if card is None:
        card = _card(tmp_path, task_type, stem)
    return dispatch.render_task_md(
        task_type, "作答：按任务书交付。", loop=f"exec:{OWNER}:{stem}", attempt=1,
        card=card,
    )


def _listed_sections(text: str) -> list[str]:
    """The copyable ``- `## <段名>` `` checklist lines, in document order."""
    return re.findall(r"^- `## ([^`]+)`$", text, flags=re.MULTILINE)


# ── single source: Python mirror == TS contract (requirement 3, option b) ─────

_TS_BASE_RE = re.compile(
    r"export const RECOVERY_SECTIONS[^=]*=\s*\[(?P<body>.*?)\]\s*as const;",
    re.DOTALL,
)
_TS_TYPE_RE = re.compile(
    r"export const RECOVERY_TYPE_SECTIONS[^=]*=\s*\{(?P<body>.*?)\n\};",
    re.DOTALL,
)
_TS_TYPE_ENTRY_RE = re.compile(
    r"([A-Za-z_][A-Za-z0-9_]*)\s*:\s*\[(?P<items>[^\]]*)\]", re.DOTALL
)
_TS_STRING_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')


def _ts_tables() -> tuple[tuple[str, ...], dict[str, tuple[str, ...]]]:
    """Parse `RECOVERY_SECTIONS` / `RECOVERY_TYPE_SECTIONS` out of the TS source."""
    if not TS_SOURCE.is_file():
        pytest.fail(f"TS single source missing: {TS_SOURCE} (fail-closed, P-016)")
    source = TS_SOURCE.read_text(encoding="utf-8")
    base_match = _TS_BASE_RE.search(source)
    if base_match is None:
        pytest.fail("RECOVERY_SECTIONS not found in the TS source")
    base = tuple(_TS_STRING_RE.findall(base_match.group("body")))
    type_match = _TS_TYPE_RE.search(source)
    if type_match is None:
        pytest.fail("RECOVERY_TYPE_SECTIONS not found in the TS source")
    extras = {
        key: tuple(_TS_STRING_RE.findall(items))
        for key, items in _TS_TYPE_ENTRY_RE.findall(type_match.group("body"))
    }
    return base, extras


def test_recovery_tables_match_the_ts_source() -> None:
    """The Python mirror is verbatim-equal to the TS contract — no drift."""
    base, extras = _ts_tables()
    assert base == dispatch.RECOVERY_SECTIONS, (base, dispatch.RECOVERY_SECTIONS)
    assert extras == dispatch.RECOVERY_TYPE_SECTIONS, (
        extras, dispatch.RECOVERY_TYPE_SECTIONS,
    )
    assert "上下文来源" in base, base
    # A TS role extra the injection scope does not cover would silently drop
    # that role's role-specific section from the checklist.
    assert set(extras) <= set(dispatch.RECOVERY_CONTRACT_TYPES), (
        sorted(set(extras) - set(dispatch.RECOVERY_CONTRACT_TYPES))
    )
    for task_type in CONTRACT_TYPES:
        expected = base + extras.get(task_type, ())
        assert dispatch.recovery_sections_for(task_type) == expected, task_type
    print(
        f"[VERIFY] ts_parity base={len(base)} extras={len(extras)} equal=true",
        flush=True,
    )


# ── AC-003: the checklist is present and role-correct ────────────────────────

@pytest.mark.parametrize(
    "task_type", CONTRACT_TYPES,
)
def test_contract_role_card_lists_its_sections(tmp_path: pathlib.Path, task_type: str) -> None:
    text = _render(tmp_path, task_type, stem=f"T-06-{task_type}")
    assert dispatch.RECOVERY_CONTRACT_HEADING in text
    listed = _listed_sections(text)
    assert listed == list(dispatch.recovery_sections_for(task_type)), listed
    # `## 上下文来源` is the base section the historical corpus misses most.
    assert "- `## 上下文来源`" in text
    print(
        f"[VERIFY] contract_role type={task_type} sections={len(listed)} "
        f"context_source={_true('- `## 上下文来源`' in text)}",
        flush=True,
    )


def test_review_card_adds_the_coverage_section(tmp_path: pathlib.Path) -> None:
    text = _render(tmp_path, "review")
    assert "- `## 未覆盖面声明`" in text
    print("[VERIFY] review_uncovered_section=true", flush=True)


def test_coding_card_adds_the_change_list(tmp_path: pathlib.Path) -> None:
    text = _render(tmp_path, "coding")
    assert "- `## 改动清单`" in text
    print("[VERIFY] coding_change_list=true", flush=True)


# ── requirement 2: no contract section -> no injection ───────────────────────

@pytest.mark.parametrize("task_type", NON_CONTRACT_TYPES)
def test_roles_without_a_contract_are_not_injected(
    tmp_path: pathlib.Path, task_type: str
) -> None:
    text = _render(tmp_path, task_type, stem=f"T-06-{task_type}")
    assert dispatch.RECOVERY_CONTRACT_HEADING not in text
    assert _listed_sections(text) == []
    print(f"[VERIFY] no_contract type={task_type} injected=false", flush=True)


# ── requirement 4: idempotent ────────────────────────────────────────────────

def test_injection_is_idempotent(tmp_path: pathlib.Path) -> None:
    card = _card(tmp_path, "review")
    first = dispatch.render_task_md("review", "作答。", loop="l", attempt=1, card=card)
    second = dispatch.render_task_md("review", "作答。", loop="l", attempt=1, card=card)
    assert first == second
    assert first.count(dispatch.RECOVERY_CONTRACT_HEADING) == 1

    # A card that already declares the heading is never given a second copy.
    _write_card(
        tmp_path, "review", "T-06-declared",
        body="\n## 交付段契约（本角色）\n\n- `## 结论`\n",
    )
    declared = dispatch.dispatch_card(tmp_path, OWNER, "T-06-declared")
    assert declared is not None
    text = dispatch.render_task_md("review", "作答。", loop="l", attempt=1, card=declared)
    assert text.count(dispatch.RECOVERY_CONTRACT_HEADING) == 1
    print(
        "[VERIFY] idempotent render_twice=true declared_once=true",
        flush=True,
    )


# ── requirement 5: the existing envelope gate and card header survive ─────────

def test_envelope_gate_and_card_header_survive(tmp_path: pathlib.Path) -> None:
    for task_type in CONTRACT_TYPES:
        stem = f"T-06-gate-{task_type}"
        card = _card(tmp_path, task_type, stem)
        text = _render(tmp_path, task_type, stem, card=card)
        assert launcher.has_canonical_envelope(text) is True
        ok, missing, seen_type, _detected = launcher.inspect_envelope(text)
        assert ok and missing == [], (task_type, missing)
        assert seen_type == task_type
        assert f"card_path: {card['path']}" in text
        assert f"card_sha256: {card['sha256']}" in text
        assert launcher.type_extras_missing(task_type, text) == []
    print(
        "[VERIFY] envelope_gate 3/3 canonical=true extras_empty=true "
        "card_header=true",
        flush=True,
    )


# ── AC-003 evidence: two real task books (research / review), hit 2/2 ─────────

def test_two_real_task_books_hit_two_of_two(tmp_path: pathlib.Path) -> None:
    hits = 0
    for task_type in ("research", "review"):
        stem = f"T-06-real-{task_type}"
        text = _render(tmp_path, task_type, stem=stem)
        listed = _listed_sections(text)
        expected = list(dispatch.recovery_sections_for(task_type))
        hit = dispatch.RECOVERY_CONTRACT_HEADING in text and listed == expected
        hits += 1 if hit else 0
        print(
            f"[VERIFY] real_book type={task_type} "
            f"task_key={dispatch.task_key_for(OWNER, stem)} "
            f"sections={len(listed)} hit={_true(hit)}",
            flush=True,
        )
        print(text[text.index(dispatch.RECOVERY_CONTRACT_HEADING):], flush=True)
    assert hits == 2, hits
    print("[VERIFY] ac003_real_books=2/2", flush=True)


# ── requirement 5: the real TS `readEnvelope` judge still accepts the render ──

_TS_SCRIPT = r"""
const fs = require("node:fs");
const { pathToFileURL } = require("node:url");
(async () => {
  const card = await import(pathToFileURL(process.env.MW_S2_CARD_MODULE).href);
  const cases = JSON.parse(fs.readFileSync(process.env.MW_S2_CASES, "utf8"));
  const verdicts = cases.map((c) => {
    const e = card.inspectEnvelope(c.text);
    const r = card.readEnvelope(c.path);
    return {
      id: c.id,
      inspect_ok: e.ok, inspect_missing: e.missing, inspect_type: e.type,
      extras: card.typeExtrasMissing(e.type, c.text),
      read_ok: r.ok, read_missing: r.missing,
    };
  });
  process.stdout.write("S2_JSON_BEGIN" + JSON.stringify({ verdicts }) + "S2_JSON_END");
})().catch((err) => { console.error(err && err.stack ? err.stack : String(err)); process.exit(1); });
"""


def _run_ts(cases: list[dict]) -> dict:
    node = shutil.which("node")
    if node is None:
        pytest.fail("node interpreter not found; TS parity cannot be measured (fail-closed, P-016)")
    if not TS_CARD_MODULE.is_file():
        pytest.fail(f"TS judge missing: {TS_CARD_MODULE} (fail-closed)")
    with tempfile.TemporaryDirectory() as tmp:
        cases_path = pathlib.Path(tmp) / "cases.json"
        cases_path.write_text(json.dumps(cases), encoding="utf-8")
        env = dict(os.environ)
        env["MW_S2_CARD_MODULE"] = str(TS_CARD_MODULE)
        env["MW_S2_CASES"] = str(cases_path)
        proc = subprocess.run(
            [node, "--experimental-strip-types", "-e", _TS_SCRIPT],
            capture_output=True,
            text=True,
            timeout=180,
            env=env,
            encoding="utf-8",
            errors="replace",
        )
    if proc.returncode != 0 or "S2_JSON_BEGIN" not in proc.stdout:
        pytest.fail(
            f"node TS judge harness failed (exit {proc.returncode}):\n"
            f"stdout:\n{proc.stdout[-2000:]}\nstderr:\n{proc.stderr[-2000:]}"
        )
    body = proc.stdout.split("S2_JSON_BEGIN", 1)[1].split("S2_JSON_END", 1)[0].strip()
    return json.loads(body)


def test_ts_read_envelope_accepts_the_injected_task_md(tmp_path: pathlib.Path) -> None:
    """The real TS judge (`inspectEnvelope` + file-reading `readEnvelope`) still
    returns ok with no missing section and no missing extra for the renders
    that carry the new checklist."""
    cases = []
    for task_type in CONTRACT_TYPES:
        stem = f"T-06-ts-{task_type}"
        text = _render(tmp_path, task_type, stem=stem)
        path = tmp_path / f"{stem}.task.md"
        path.write_text(text, encoding="utf-8", newline="\n")
        cases.append({"id": task_type, "text": text, "path": str(path)})
    measured = _run_ts(cases)
    assert len(measured["verdicts"]) == len(cases)
    by_id = {case["id"]: case for case in cases}
    for verdict in measured["verdicts"]:
        task_type = verdict["id"]
        text = by_id[task_type]["text"]
        py_ok, py_missing, py_type, _detected = launcher.inspect_envelope(text)
        assert verdict["inspect_ok"] is True and py_ok is True, (task_type, verdict)
        assert verdict["inspect_missing"] == py_missing == [], (task_type, verdict)
        assert verdict["inspect_type"] == py_type == task_type, (task_type, verdict)
        assert verdict["read_ok"] is True and verdict["read_missing"] == [], verdict
        assert verdict["extras"] == launcher.type_extras_missing(task_type, text) == [], verdict
    print(
        "[VERIFY] ts_readEnvelope 3/3 inspect_ok=true read_ok=true "
        "missing=[] extras=[]",
        flush=True,
    )
