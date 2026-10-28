"""test_mwds_t13_producer_paralysis.py — T-13 / AC-009 (the producer must not
paralyse the conductor).

Key ``mw-dispatch-card-gate``, AC-009 ("生产者不瘫痪") and P-10 ("门禁在全局
服务层、注入在每个项目的 framework 副本 = 两个版本域").  Incident evidence:
``evidence/incidents/autopilot-producer-paralysis-20261012.md`` — the service
gate (``launcher._envelope_refusal``) judges the **derived** ``task.md``, while
the producer that fills that file is a per-project copy, so a shape the service
accepts but the producer cannot emit turns every dispatch of an unsynced
project into ``failed`` (675 done / 33 failed / 0 pending / 0 running, queue
untouched for two days).

What this file pins (each group prints one ``[T-13 evidence]`` line with the
judge's actual return value):

* **VC-001 producer self-sufficiency** — every production path's rendered
  ``task.md`` fed to the real service judge returns ``None`` (spawnable):
  card-backed ``coding`` (extras as bullets *and* as separate ``##`` headings,
  the F-02 shape), card-less synthesized ``coding``, ``review`` and
  ``research``, plus every conductor registry type through the real
  ``dispatch()`` (``repair`` / ``roadmap-writer`` / ``reviewer`` / ``verifier``
  / ``phase-writer``).
* **VC-002 the paralysis mechanism is executable** — the *old* producer shapes
  (bare prompt body; 3 canonical sections but dropped extras) are refused by
  name, so the incident's failure mode is reproducible rather than narrated.
  T-14 note: once the service layer consumes the producer identity line this
  case must be rewritten to assert "visible upgrade hint + no silent zero
  output"; registered here on purpose.
* **VC-003 producer identity** — ``envelope_producer: <producer>@<version>`` is
  in the header region, parseable by one shared parser, and its version equals
  the lockstep package metadata (no new hardcoded constant).
* **VC-004 no phantom card reference** — a card-less dispatch writes no
  ``card_path:`` line.
* **VC-005 extras are real** — each required item carries a non-empty value
  sourced from dispatch metadata (never an empty skeleton).

``launcher`` is imported read-only (the same module the service runs); this
file never writes it, and the producer itself must not import it at all
(P-10 layering).
"""
import json
import pathlib
import re
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import launcher  # noqa: E402  (read-only import; the producer never imports it)
from autopilot import dispatch  # noqa: E402

OWNER = "k1"
CARD_STEM = "T-13"
_PROMPT = (
    "实现 T-13 的生成端注入。\n"
    "验收命令: python -X utf8 -m pytest packages/multi-workers/test_mwds_t13_producer_paralysis.py -q\n"
    "改动清单: packages/multi-workers/autopilot/dispatch.py\n"
)

# The production card shape of this key's corpus: the §1.2 extras live as
# bullets inside `## 要求` / `## 交付格式` (all cards carry exactly the three
# canonical headings, see tasks/T-*.md).
_CARD_BULLETS = (
    "type: coding\n"
    "\n"
    "## 上下文\n"
    "\n"
    "背景：服务层判据读派生 task.md，生成端必须自足。\n"
    "\n"
    "## 要求\n"
    "\n"
    "实现生成端注入；AC-001 必须通过。\n"
    "\n"
    "## 交付格式\n"
    "\n"
    "写入允许面：packages/multi-workers/autopilot/dispatch.py\n"
    "写入禁止面：packages/coding-agent/**\n"
    "验收命令：python -X utf8 -m pytest packages/multi-workers/test_mwds_t13_producer_paralysis.py -q\n"
    "改动历史：trace.log 写入事件\n"
)

# The F-02 shape: the same declaration written as separate `##` sections. The
# old producer's `extractCardSections` took only the three canonical families
# and dropped these, so a compliant card was still refused.
_CARD_EXTRA_HEADINGS = (
    "type: coding\n"
    "\n"
    "## 上下文\n"
    "\n"
    "动机：extras 判据对象错位（F-02）。\n"
    "\n"
    "## 要求\n"
    "\n"
    "AC-001 必须通过。\n"
    "\n"
    "## 交付格式\n"
    "\n"
    "产物 report.md / output.md。\n"
    "\n"
    "## 写入允许面\n"
    "\n"
    "packages/multi-workers/autopilot/dispatch.py\n"
    "\n"
    "## 写入禁止面\n"
    "\n"
    "packages/coding-agent/**\n"
    "\n"
    "## 验收命令\n"
    "\n"
    "python -X utf8 -m pytest packages/multi-workers/test_mwds_t13_producer_paralysis.py -q\n"
    "\n"
    "## 改动历史\n"
    "\n"
    "trace.log 写入事件\n"
)

# Pre-T-13 producer output for a coding task: canonical sections, no extras
# (and no producer identity line). This is the exact on-disk shape that the
# service gate refuses — the incident's per-row `failed`.
_OLD_PRODUCER_TASK_MD = (
    "---\n"
    "type: coding\n"
    "origin: conductor\n"
    "loop: exec:k1:T-13\n"
    "attempt: 1\n"
    "---\n"
    "\n"
    "## 上下文\n"
    "\n"
    "autopilot 自动派发（无任务卡）。\n"
    "\n"
    "## 要求\n"
    "\n"
    "实现注入。\n"
    "\n"
    "## 交付格式\n"
    "\n"
    "产物 report.md。\n"
    "\n"
    "以上为种子，不是探索上界；可自行检索补充上下文。\n"
)

# Pre-envelope producer shape (T-09 and earlier): a bare prompt body.
_BARE_LEGACY_TASK_MD = "type: coding\n\nDo something useful.\n"


def _write(tmp_path: pathlib.Path, name: str, text: str) -> pathlib.Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _refusal(tmp_path: pathlib.Path, name: str, text: str) -> str | None:
    """The real service judge over one rendered task.md (read-only)."""
    return launcher._envelope_refusal({"task_path": str(_write(tmp_path, name, text))})


def _render_card(
    tmp_path: pathlib.Path, card_text: str, task_type: str = "coding"
) -> str:
    """Render through the real card-resolution path (``dispatch_card``)."""
    card_dir = tmp_path / ".agenticdoc" / OWNER / "tasks"
    card_dir.mkdir(parents=True, exist_ok=True)
    (card_dir / f"{CARD_STEM}.md").write_text(card_text, encoding="utf-8", newline="\n")
    card = dispatch.dispatch_card(tmp_path, OWNER, CARD_STEM)
    assert card is not None
    return dispatch.render_task_md(
        task_type, _PROMPT, loop=f"exec:{OWNER}:{CARD_STEM}", attempt=1, card=card,
    )


def _card_less(task_type: str, prompt: str = _PROMPT) -> str:
    """Render through the card-less synthesized path (``dispatch()``'s T-10/T-13
    branch), for types ``dispatch()`` refuses because they are not registry
    roles (``coding`` / ``review`` / ``research``)."""
    card = dispatch.synthesized_card(
        OWNER, CARD_STEM, task_type, prompt, f"exec:{OWNER}:{CARD_STEM}", 1
    )
    return dispatch.render_task_md(
        task_type, prompt, loop=f"exec:{OWNER}:{CARD_STEM}", attempt=1, card=card,
    )


def _label_value(text: str, item: str) -> str:
    """Value of the first line whose label is ``item`` (bullet or field form)."""
    pattern = re.compile(
        rf"^\s*(?:[-*+]|\d+[.)])?\s*(?:\*\*)?{re.escape(item)}(?:\*\*)?\s*[:：]\s*(.*)$"
    )
    for raw in text.splitlines():
        match = pattern.match(raw)
        if match:
            return match.group(1).strip()
    return ""


def _true(value: bool) -> str:
    return "true" if value else "false"


# ── VC-001: every production path passes the service gate ─────────────────────

@pytest.mark.parametrize(
    "case_id, task_type, card_text",
    [
        ("card-backed-coding-bullets", "coding", _CARD_BULLETS),
        ("card-backed-coding-headings", "coding", _CARD_EXTRA_HEADINGS),
    ],
)
def test_card_backed_render_passes_the_gate(
    tmp_path: pathlib.Path, case_id: str, task_type: str, card_text: str
) -> None:
    """A card-backed render is self-sufficient: the service judge returns None."""
    text = _render_card(tmp_path, card_text, task_type)
    refusal = _refusal(tmp_path, f"{case_id}.task.md", text)
    print(f"[T-13 evidence] {case_id} -> refusal={refusal!r}")
    assert refusal is None, refusal
    # Card-backed dispatches DO name the real card (requirement 3).
    assert "card_path: tasks/T-13.md" in text
    assert "card_sha256: " in text


def test_card_extra_headings_are_injected_verbatim(tmp_path: pathlib.Path) -> None:
    """F-02 regression: a card's unclassified §1.2 headings reach the derived
    task.md (the old producer's `extractCardSections` dropped them)."""
    text = _render_card(tmp_path, _CARD_EXTRA_HEADINGS)
    for title, body in (
        ("写入允许面", "packages/multi-workers/autopilot/dispatch.py"),
        ("写入禁止面", "packages/coding-agent/**"),
        ("验收命令", "python -X utf8 -m pytest"),
        ("改动历史", "trace.log 写入事件"),
    ):
        assert f"## {title}" in text, title
        assert body in text, (title, body)
    extras = dispatch.extract_card_extras(_CARD_EXTRA_HEADINGS)
    assert [e["title"] for e in extras] == [
        "写入允许面", "写入禁止面", "验收命令", "改动历史",
    ]
    # The 3-key caller contract of `extract_card_sections` is unchanged.
    assert set(dispatch.extract_card_sections(_CARD_EXTRA_HEADINGS)) == {
        "context", "requirements", "deliverables",
    }
    refusal = _refusal(tmp_path, "extras-headings.task.md", text)
    print(f"[T-13 evidence] card-extra-headings -> refusal={refusal!r}")
    assert refusal is None, refusal


@pytest.mark.parametrize("task_type", ["coding", "review", "research"])
def test_card_less_synthesized_render_passes_the_gate(
    tmp_path: pathlib.Path, task_type: str
) -> None:
    """Card-less synthesized dispatches carry their own extras (T-10 envelope
    plus the T-13 §1.2 items) and write no phantom card reference."""
    text = _card_less(task_type)
    refusal = _refusal(tmp_path, f"synth-{task_type}.task.md", text)
    print(f"[T-13 evidence] card-less-{task_type} -> refusal={refusal!r}")
    assert refusal is None, refusal
    assert "card_path:" not in text and "card_sha256:" not in text
    for item in dispatch.PRODUCER_EXTRA_ITEMS[task_type]:
        assert item in text, (task_type, item)
        assert _label_value(text, item), (task_type, item, "empty value")


@pytest.mark.parametrize(
    "owner, stem, task_type, read_scope",
    [
        (OWNER, "repair-a1", "repair", ()),
        (dispatch.SCRATCH_OWNER, "roadmap-s1", "roadmap-writer", (".agenticdoc",)),
        (OWNER, "l3-a1", "reviewer", (".agenticdoc/k1",)),
        (OWNER, "l2-a1", "verifier", (".agenticdoc/k1",)),
        (OWNER, "t-05", "phase-writer", ()),
    ],
)
def test_conductor_dispatch_paths_pass_the_gate(
    tmp_path: pathlib.Path,
    owner: str,
    stem: str,
    task_type: str,
    read_scope: tuple[str, ...],
) -> None:
    """Every registered conductor dispatch type (L2/L3/repair/roadmap/execute)
    produces a task.md the service judge accepts, and carries the producer
    identity line."""
    result = dispatch.dispatch(
        tmp_path, owner, stem, task_type, "Do the work.",
        loop=f"{task_type}:{stem}", attempt=1, read_scope=read_scope,
    )
    assert result.ok and result.task_md is not None, result.reason
    text = result.task_md.read_text(encoding="utf-8")
    refusal = launcher._envelope_refusal(
        {"task_path": str(result.task_md), "task_key": result.task_key}
    )
    print(
        f"[T-13 evidence] dispatch({task_type}, owner={owner}) -> "
        f"refusal={refusal!r} producer={dispatch.parse_producer_identity(text)}"
    )
    assert refusal is None, refusal
    assert dispatch.parse_producer_identity(text) is not None
    # A card-less dispatch must not invent a card reference.
    assert "card_path:" not in text


# ── VC-002: the paralysis mechanism, made executable ─────────────────────────

def test_old_producer_shape_is_refused(tmp_path: pathlib.Path) -> None:
    """The pre-T-13 producer output for a coding task IS refused by the service
    judge — the incident's per-row failure, reproducible.

    T-14 note (registered, not implemented here): after the service layer
    consumes ``envelope_producer``, this same input must produce a visible
    upgrade hint and must NOT be a silent zero-dispatch.  This card only pins
    today's refusal so the mechanism cannot regress unnoticed.
    """
    refusal = _refusal(tmp_path, "old-producer.task.md", _OLD_PRODUCER_TASK_MD)
    print(f"[T-13 evidence] old-producer(coding, no extras) -> refusal={refusal!r}")
    assert refusal is not None
    for item in dispatch.PRODUCER_EXTRA_ITEMS["coding"]:
        assert item in refusal, (item, refusal)
    assert dispatch.parse_producer_identity(_OLD_PRODUCER_TASK_MD) is None
    assert launcher.has_canonical_envelope(_OLD_PRODUCER_TASK_MD)


def test_pre_envelope_shape_is_refused_by_name(tmp_path: pathlib.Path) -> None:
    """The bare-prompt producer shape is refused on the canonical sections and
    the extras (the M2 failure signature: `envelope missing: ...`)."""
    refusal = _refusal(tmp_path, "bare-legacy.task.md", _BARE_LEGACY_TASK_MD)
    print(f"[T-13 evidence] pre-envelope(bare prompt) -> refusal={refusal!r}")
    assert refusal is not None
    assert "envelope missing:" in refusal
    for section in ("上下文", "要求", "交付格式"):
        assert section in refusal, (section, refusal)


# ── VC-003: producer identity line ───────────────────────────────────────────

def test_producer_identity_line_is_parseable(tmp_path: pathlib.Path) -> None:
    """`envelope_producer: <producer>@<version>`, in the header region, right
    before the other attribution line, parsed by the one shared parser."""
    result = dispatch.dispatch(
        tmp_path, OWNER, "t-05", "phase-writer", "Write it.",
        loop="exec:k1:t-05", attempt=1,
    )
    assert result.task_md is not None
    text = result.task_md.read_text(encoding="utf-8")
    header = text.split("---\n", 2)[1]
    assert f"envelope_producer: {dispatch.producer_identity()}\n" in header
    # It sits after the semantic headers and before `origin:`.
    assert header.index("type: phase-writer") < header.index("envelope_producer:")
    assert header.index("envelope_producer:") < header.index("origin: conductor")
    # The first header key stays `type:` (worker-mode.ts reads the FIRST one).
    assert text.splitlines()[1] == "type: phase-writer"
    parsed = dispatch.parse_producer_identity(text)
    assert parsed == (dispatch.PRODUCER_NAME, dispatch.producer_version())
    producer, version = parsed
    assert producer == "autopilot-conductor"
    assert version and version != dispatch._PRODUCER_VERSION_UNKNOWN
    print(
        "[T-13 evidence] producer line shape=key:producer@version "
        f"parsed=({producer}, {version})"
    )


def test_producer_version_comes_from_existing_package_metadata() -> None:
    """The version value is read from the lockstep release metadata — no new
    hardcoded constant (requirement 2)."""
    repo_root = pathlib.Path(dispatch.__file__).resolve().parents[3]
    package = json.loads(
        (repo_root / "packages" / "coding-agent" / "package.json").read_text(
            encoding="utf-8"
        )
    )
    source_version = package["version"]
    assert dispatch.producer_version() == source_version
    assert dispatch.producer_identity() == f"autopilot-conductor@{source_version}"
    # No version literal lives in the module: the value above is the only source.
    source = pathlib.Path(dispatch.__file__).read_text(encoding="utf-8")
    assert source_version not in source
    print(
        f"[T-13 evidence] producer_version source=packages/coding-agent/package.json "
        f"value={source_version}"
    )


def test_producer_does_not_depend_on_the_service_layer() -> None:
    """P-10 / requirement 1: the producer is self-sufficient — it must not
    import the service layer it is judged by."""
    source = pathlib.Path(dispatch.__file__).read_text(encoding="utf-8")
    assert "import launcher" not in source
    assert "from launcher" not in source


# ── VC-005: extras are non-empty and come from real metadata ─────────────────

def test_synthesized_extras_reference_real_round_metadata() -> None:
    """A card-less extras value is built from this round's own metadata (worker
    dir / trace.log / the prompt's command) — never an empty placeholder."""
    for task_type in ("coding", "review", "research"):
        text = _card_less(task_type)
        worker_dir = f".agenticdoc/{OWNER}/workers/{dispatch.task_key_for(OWNER, CARD_STEM)}"
        for item in dispatch.PRODUCER_EXTRA_ITEMS[task_type]:
            value = _label_value(text, item)
            assert value, (task_type, item)
            assert not value.endswith(":"), (task_type, item, value)
        if task_type == "coding":
            assert worker_dir in _label_value(text, "写入允许面")
            assert f"{worker_dir}/trace.log" in _label_value(text, "改动历史")
            assert "pytest" in _label_value(text, "验收命令")
        if task_type == "research":
            assert f"{worker_dir}/output.md" in _label_value(text, "唯一证据文件")


def test_extras_fall_back_without_a_worker_dir(tmp_path: pathlib.Path) -> None:
    """A card input without `worker_dir` (a direct caller) still gets non-empty
    extras — the fallback wording is generic, not an empty skeleton."""
    prompt = "修复失败项。"
    card = {
        "path": "", "sha256": "", "extras": [],
        "context": "动机：c。", "requirements": prompt, "deliverables": "产物 report.md。",
    }
    text = dispatch.render_task_md("coding", prompt, loop="l", attempt=1, card=card)
    for item in dispatch.PRODUCER_EXTRA_ITEMS["coding"]:
        assert item in text, item
        assert _label_value(text, item), (item, "empty value")
    # The generic wording still contains no empty skeleton line (`label:` alone).
    for line in text.splitlines():
        assert not re.match(r"^\s*[-*+]?\s*(?:\*\*)?[^:：]{1,20}(?:\*\*)?\s*[:：]\s*$", line), line
    refusal = _refusal(tmp_path, "no-worker-dir.task.md", text)
    print(f"[T-13 evidence] extras-without-worker-dir -> refusal={refusal!r}")
    assert refusal is None, refusal
