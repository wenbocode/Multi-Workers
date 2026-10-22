"""test_claim_dispatch.py — claim-driven-review T-03 acceptance.

Subject: ``autopilot/dispatch.py`` learns to read a card's ``mw-claims: v1``
block and to price a dispatch's read scope from *that* card (until T-03 the
caps were computed before the card was read, so they could only ever follow the
previous card's budget). Coverage of the card's six requirements:

  1. ``dispatch_card`` returns the parsed claims (+ row-level parse errors) for
     the grammar variants (alias header, full-width row, short row, fenced
     example table);
  2. the derived caps follow the card — ``min(30, Σ(manual?2:1))`` files,
     ``min(393216, 65536 × n)`` bytes — in two dispatches of the same project;
  3. a claims-less card renders **byte-identically** to the pre-change
     renderer;
  4. the synthesized (no card file) path writes no cap lines;
  5. an explicit project-layer cap wins over the derived value (per field);
  6. an invalid gate value falls back to ``advisory`` with one stderr line and
     never blocks the dispatch (fail-open).

The byte-identical left end (③) is the pre-change renderer itself: the HEAD
blob of ``autopilot/dispatch.py`` (``git show HEAD:...``) executed as a module —
the same technique ``test_autopilot_readcap_injection.py`` uses — instead of a
hand-copied golden string nobody can re-derive. Both dispatches run the full
``dispatch()`` pipeline (task.md write + queue row) in two separate fixture
project roots, so the comparison covers the *decision* (which caps to render),
not just the renderer.

Evidence channel is stdout: run with ``-s`` for the ``[VERIFY]`` lines.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import types

MODULE_DIR = pathlib.Path(__file__).resolve().parent
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

from autopilot import dispatch as dispatch_mod  # noqa: E402

FRAMEWORK_ROOT = MODULE_DIR.parent.parent
DISPATCH_RELATIVE = "packages/multi-workers/autopilot/dispatch.py"
OWNER = "claims-key"

CLAIM_HEADER = "| claim | 类型 | 陈述 | 反证条件 | 定位 | 判据 | 预算 |"
CLAIM_RULE = "| --- | --- | --- | --- | --- | --- | --- |"


# ── fixtures ─────────────────────────────────────────────────────────────────

def _row(
    claim_id: str,
    kind: str,
    *,
    statement: str = "X 不再读取 Y",
    falsifier: str = "出现对 Y 的读取",
    locator: str = "src/x.ts",
    judgement: str = "grep: X => count=0",
    budget: str = "1",
) -> str:
    return (
        f"| {claim_id} | {kind} | {statement} | {falsifier} | "
        f"{locator} | {judgement} | {budget} |"
    )


def _card_text(
    *rows: str,
    header: str | None = CLAIM_HEADER,
    prefix: tuple[str, ...] = (),
    write_face: str | None = None,
) -> str:
    """A review card: the three envelope sections + an optional claims block.

    ``write_face`` renders a ``## 写入允许面`` section: two dispatches of the
    same owner in one project must not be refused as `serial-only` (the
    write-face gate serialises *undeclared* faces), so the multi-dispatch
    cases declare disjoint faces.
    """
    lines = [
        "# T-00 fixture card",
        "",
        "## 上下文",
        "",
        "fixture context body",
        "",
        "## 要求",
        "",
        "fixture requirements body",
        "",
    ]
    if header is not None:
        lines += ["<!-- mw-claims: v1 -->", ""]
        lines += list(prefix)
        lines += [header, CLAIM_RULE, *rows]
        lines += [""]
        lines += ["<!-- /mw-claims -->", ""]
    lines += ["## 交付格式", "", "fixture deliverable body", ""]
    if write_face is not None:
        lines += ["", "## 写入允许面", "", f"- {write_face}", ""]
    return "\n".join(lines)


def _make_project(root: pathlib.Path, config: dict | None = None) -> pathlib.Path:
    """Fixture project: ``.agenticdoc/target.yml`` (single mode) + optional
    ``_autopilot/config.json``. No config file is written when ``config`` is
    ``None`` (the zero-footprint shape)."""
    root = pathlib.Path(root)
    agentic = root / ".agenticdoc"
    agentic.mkdir(parents=True, exist_ok=True)
    (agentic / "target.yml").write_text("mode: single\n", encoding="utf-8", newline="\n")
    if config is not None:
        cfg_dir = agentic / "_autopilot"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        (cfg_dir / "config.json").write_text(
            json.dumps(config, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
    return root


def _write_card(root: pathlib.Path, stem: str, text: str) -> pathlib.Path:
    card_dir = pathlib.Path(root) / ".agenticdoc" / OWNER / "tasks"
    card_dir.mkdir(parents=True, exist_ok=True)
    path = card_dir / f"{stem}.md"
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _dispatch(root: pathlib.Path, stem: str):
    return dispatch_mod.dispatch(
        root,
        OWNER,
        stem,
        "reviewer",
        "Judge the evidence.",
        loop="claim-driven-review:003",
        attempt=1,
        read_scope=[f".agenticdoc/{OWNER}"],
    )


def _verify(tag: str, **kv: object) -> None:
    payload = " ".join(f"{key}={value}" for key, value in kv.items())
    print(f"[VERIFY] {tag}: {payload}")


# ── pre-change renderer (byte-identical left end) ────────────────────────────

_HEAD_CACHE: list[types.ModuleType] = []


def _head_module() -> types.ModuleType:
    """The pre-T-03 ``dispatch.py`` (git HEAD blob) executed as a module."""
    if _HEAD_CACHE:
        return _HEAD_CACHE[0]
    proc = subprocess.run(
        ["git", "-C", str(FRAMEWORK_ROOT), "show", f"HEAD:{DISPATCH_RELATIVE}"],
        check=False,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    data = proc.stdout
    module = types.ModuleType("_claim_dispatch_head")
    # Real path: `__file__` drives the module's own sys.path bootstrap and
    # `_repo_root()` (parents[3]); the exec'd source is the HEAD blob.
    module.__file__ = str(MODULE_DIR / "autopilot" / "dispatch.py")
    sys.modules["_claim_dispatch_head"] = module
    exec(compile(data.decode("utf-8"), module.__file__, "exec"), module.__dict__)
    _HEAD_CACHE.append(module)
    return module


# ── ① dispatch_card returns the claims ───────────────────────────────────────

def test_dispatch_card_returns_claims(tmp_path: pathlib.Path) -> None:
    root = _make_project(tmp_path / "project")
    _write_card(
        root,
        "T-00",
        _card_text(
            _row("C-01", "grep", budget="1"),
            # A fenced example table (with its own header) must contribute
            # nothing: format examples are common in cards.
            prefix=(
                "```markdown",
                CLAIM_HEADER,
                CLAIM_RULE,
                _row("C-09", "grep"),
                "```",
                "",
            ),
            # A row after a fenced block needs its own header only because the
            # fence reset the columns state (same rule as the TS parser); the
            # real rows below sit in the real table.
        ),
    )
    _write_card(
        root,
        "T-00b",
        _card_text(_row("C-02", "manual", budget="2")),
    )
    card = dispatch_mod.dispatch_card(root, OWNER, "T-00")
    assert card is not None
    ids = [claim["id"] for claim in card["claims"]]
    assert ids == ["C-01"], ids
    assert card["claim_errors"] == []
    assert [claim["budget"] for claim in card["claims"]] == [1]
    assert [claim["type"] for claim in card["claims"]] == ["grep"]
    assert [claim["row"] for claim in card["claims"]]
    manual_card = dispatch_mod.dispatch_card(root, OWNER, "T-00b")
    assert manual_card is not None
    assert [claim["type"] for claim in manual_card["claims"]] == ["manual"]
    assert manual_card["claims"][0]["budget"] == 2
    _verify("claims", ids=",".join(ids), errors=len(card["claim_errors"]))

    # Alias header (`断言`) + full-width pipes/colon/digits.
    _write_card(
        root,
        "T-01",
        _card_text(
            "｜ C-11 ｜ grep ｜ 陈述 ｜ 反证条件 ｜ src/x.ts ｜ grep: X => count=0 ｜ １ ｜",
            header="｜ 断言 ｜ 类型 ｜ 陈述 ｜ 反证条件 ｜ 定位 ｜ 判据 ｜ 预算 ｜",
        ),
    )
    aliased = dispatch_mod.dispatch_card(root, OWNER, "T-01")
    assert aliased is not None
    assert [claim["id"] for claim in aliased["claims"]] == ["C-11"]
    assert aliased["claims"][0]["budget"] == 1
    assert aliased["claims"][0]["judgement"] == "grep: X => count=0"

    # Short row (missing trailing cells) and a header without the 判据/预算
    # columns: fields come back empty (the gap judge's job), never raised.
    _write_card(
        root,
        "T-02",
        _card_text(
            _row("C-21", "cmd"),
            "| C-22 | cmd | 陈述 | 反证条件 | evidence/claims/a.md#C-22 |",
        ),
    )
    short = dispatch_mod.dispatch_card(root, OWNER, "T-02")
    assert short is not None
    assert [claim["id"] for claim in short["claims"]] == ["C-21", "C-22"]
    assert short["claims"][1]["judgement"] == ""
    assert short["claims"][1]["budget"] is None
    assert short["claim_errors"] == []

    _write_card(
        root,
        "T-02b",
        _card_text(
            "| C-23 | grep | 陈述 | 反证条件 | src/x.ts |",
            header="| claim | 类型 | 陈述 | 反证条件 | 定位 |",
        ),
    )
    no_judgement = dispatch_mod.dispatch_card(root, OWNER, "T-02b")
    assert no_judgement is not None
    assert [claim["id"] for claim in no_judgement["claims"]] == ["C-23"]
    assert no_judgement["claims"][0]["judgement"] == ""
    assert no_judgement["claims"][0]["locator"] == "src/x.ts"

    # A row whose id does not parse is dropped and reported by source line —
    # never an exception (the TS `claim:<line>:unparsable` form).
    _write_card(
        root,
        "T-02c",
        _card_text(_row("C-24", "grep"), "| X-1 | grep | 陈述 | f | loc | j | 1 |"),
    )
    bad_id = dispatch_mod.dispatch_card(root, OWNER, "T-02c")
    assert bad_id is not None
    assert [claim["id"] for claim in bad_id["claims"]] == ["C-24"]
    assert len(bad_id["claim_errors"]) == 1, bad_id["claim_errors"]
    assert bad_id["claim_errors"][0].startswith("claim:")
    assert bad_id["claim_errors"][0].endswith(":unparsable")

    # No claims block at all -> present=False shape, empty list, no exception.
    _write_card(root, "T-03", _card_text(header=None))
    plain = dispatch_mod.dispatch_card(root, OWNER, "T-03")
    assert plain is not None
    assert plain["claims"] == []
    assert plain["claim_errors"] == []
    _verify(
        "dispatch_card",
        alias=len(aliased["claims"]),
        short_rows=len(short["claim_errors"]),
        bad_id_errors=len(bad_id["claim_errors"]),
        plain=len(plain["claims"]),
        ok="True",
    )


def test_parse_claims_block_never_raises() -> None:
    """Garbage around the block is tolerated (P-048: no false refusals).

    A block whose table has no readable header contributes no claim and no
    error — the same tolerance the TS parser has (an id-less row is not a
    header, so there is nothing to key a complaint on).
    """
    block = dispatch_mod.parse_claims_block(
        "<!-- mw-claims: v1 -->\n\nnot a table\n| C-01 |\n| C-02 | grep |\n"
    )
    assert block["present"] is True
    assert block["claims"] == []
    assert block["errors"] == []
    assert dispatch_mod.parse_claims_block("") == {
        "present": False, "claims": [], "errors": [],
    }
    # A header-less table nested in prose is equally inert.
    assert dispatch_mod.parse_claims_block(
        "<!-- mw-claims: v1 -->\n| a | b |\n| 1 | 2 |\n"
    ) == {"present": True, "claims": [], "errors": []}


def test_claims_child_rows_follow_the_parent_type() -> None:
    """`C-01.3` is only legal under a `struct` parent (RQ-3 §5.1/B-10)."""
    under_grep = dispatch_mod.parse_claims_block(
        _card_text(_row("C-01", "grep"), _row("C-01.1", "struct"))
    )
    assert [claim["id"] for claim in under_grep["claims"]] == ["C-01"]
    assert len(under_grep["errors"]) == 1, under_grep["errors"]

    under_struct = dispatch_mod.parse_claims_block(
        _card_text(_row("C-01", "struct"), _row("C-01.1", ""))
    )
    ids = [claim["id"] for claim in under_struct["claims"]]
    assert ids == ["C-01", "C-01.1"], ids
    child = under_struct["claims"][1]
    assert child["parent"] == "C-01"
    # An empty 类型 cell inherits `struct` instead of manufacturing a gap.
    assert child["type"] == "struct"
    assert under_struct["errors"] == []


# ── ② the caps follow the card (budget derivation) ───────────────────────────

def test_caps_follow_the_card(tmp_path: pathlib.Path) -> None:
    root = _make_project(tmp_path / "project")
    # 3 claims, one of them manual -> 2 + 1 + 1 = 4 files; 3 x 65536 bytes.
    _write_card(
        root,
        "T-10",
        _card_text(
            _row("C-01", "grep"), _row("C-02", "struct"), _row("C-03", "manual", budget="2"),
            write_face=f".agenticdoc/{OWNER}/workers/ap-{OWNER}-T-10/**",
        ),
    )
    # 1 manual claim -> 2 files; 1 x 65536 bytes.
    _write_card(
        root,
        "T-11",
        _card_text(
            _row("C-01", "manual", budget="2"),
            write_face=f".agenticdoc/{OWNER}/workers/ap-{OWNER}-T-11/**",
        ),
    )

    wide = _dispatch(root, "T-10")
    narrow = _dispatch(root, "T-11")
    assert wide.ok and wide.row_verified, wide.reason
    assert narrow.ok and narrow.row_verified, narrow.reason
    wide_text = wide.task_md.read_text(encoding="utf-8")
    narrow_text = narrow.task_md.read_text(encoding="utf-8")
    assert "l2_read_file_cap: 4" in wide_text
    assert "l2_read_byte_cap: 196608" in wide_text
    assert "l2_read_file_cap: 2" in narrow_text
    assert "l2_read_byte_cap: 65536" in narrow_text
    # Same project, same pipeline: the caps follow the card, never the
    # previous dispatch (the pre-T-03 order priced the previous card).
    assert "l2_read_file_cap: 4" not in narrow_text

    # Direct derivation: manual counts double, both bounds clamp.
    claims = [{"type": "grep"}, {"type": "manual"}]
    assert dispatch_mod.claim_budget_caps(claims) == (3, 131072)
    assert dispatch_mod.claim_budget_caps(None) == (0, 0)
    assert dispatch_mod.claim_budget_caps([]) == (0, 0)
    flood = [{"type": "grep"}] * 60
    assert dispatch_mod.claim_budget_caps(flood) == (
        dispatch_mod.CLAIM_BUDGET["callCap"],
        dispatch_mod.CLAIM_BUDGET["byteCapMax"],
    )
    _verify(
        "caps",
        wide=(4, 196608),
        narrow=(2, 65536),
        clamp=dispatch_mod.claim_budget_caps(flood),
        ok="True",
    )


# ── ③ a claims-less card is byte-identical to the pre-change renderer ───────

def test_claims_less_card_renders_byte_identical(tmp_path: pathlib.Path) -> None:
    head = _head_module()
    card = _card_text(header=None)
    now_root = _make_project(tmp_path / "now")
    before_root = _make_project(tmp_path / "before")
    _write_card(now_root, "T-20", card)
    _write_card(before_root, "T-20", card)
    now = _dispatch(now_root, "T-20")
    before = head.dispatch(
        before_root,
        OWNER,
        "T-20",
        "reviewer",
        "Judge the evidence.",
        loop="claim-driven-review:003",
        attempt=1,
        read_scope=[f".agenticdoc/{OWNER}"],
    )
    assert now.ok and before.ok, (now.reason, before.reason)
    now_bytes = now.task_md.read_bytes()
    before_bytes = before.task_md.read_bytes()
    assert now_bytes == before_bytes
    text = now_bytes.decode("utf-8")
    assert "l2_read_file_cap" not in text
    assert "l2_read_byte_cap" not in text
    _verify(
        "byte-identity",
        bytes=len(now_bytes),
        caps="absent",
        ok=str(now_bytes == before_bytes),
    )


# ── ④ the synthesized (card-less) path writes no caps ───────────────────────

def test_synthesized_dispatch_writes_no_caps(tmp_path: pathlib.Path) -> None:
    root = _make_project(tmp_path / "project")
    result = _dispatch(root, "T-30")  # no tasks/T-30.md -> synthesized card
    assert result.ok and result.row_verified, result.reason
    text = result.task_md.read_text(encoding="utf-8")
    assert "## 上下文" in text  # the synthesized envelope really rendered
    assert "l2_read_file_cap" not in text
    assert "l2_read_byte_cap" not in text
    assert dispatch_mod._read_scope_caps(root) == (None, None)
    assert dispatch_mod._read_scope_caps(root, None) == (None, None)
    _verify("synthesized", caps="absent", ok="True")


# ── ⑤ the project layer wins over the derived value (per field) ─────────────

def test_explicit_project_caps_win(tmp_path: pathlib.Path) -> None:
    # Only the file cap is configured: it wins, the byte cap is still derived.
    root = _make_project(tmp_path / "partial", {"l2_read_file_cap": 7})
    _write_card(
        root,
        "T-40",
        _card_text(_row("C-01", "grep"), _row("C-02", "struct"), _row("C-03", "grep")),
    )
    partial = _dispatch(root, "T-40")
    assert partial.ok, partial.reason
    partial_text = partial.task_md.read_text(encoding="utf-8")
    assert "l2_read_file_cap: 7" in partial_text
    assert "l2_read_byte_cap: 196608" in partial_text

    # Both configured: no derived value may override either.
    full_root = _make_project(
        tmp_path / "full", {"l2_read_file_cap": 9, "l2_read_byte_cap": 2097152}
    )
    _write_card(full_root, "T-41", _card_text(_row("C-01", "manual", budget="2")))
    full = _dispatch(full_root, "T-41")
    assert full.ok, full.reason
    full_text = full.task_md.read_text(encoding="utf-8")
    assert "l2_read_file_cap: 9" in full_text
    assert "l2_read_byte_cap: 2097152" in full_text
    assert dispatch_mod._read_scope_caps(
        full_root, [{"type": "grep"}]
    ) == (9, 2097152)
    _verify("project-wins", partial=(7, 196608), full=(9, 2097152), ok="True")


# ── ⑥ invalid gate value: fall back to advisory, never block ────────────────

def test_claim_gate_invalid_falls_back(
    tmp_path: pathlib.Path, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("MW_CLAIM_GATE", "bogus")
    assert dispatch_mod.claim_gate() == dispatch_mod.CLAIM_GATE_DEFAULT
    err = capsys.readouterr().err
    assert "[CLAIMS] claim_gate=bogus fallback=advisory" in err, err

    monkeypatch.setenv("MW_CLAIM_GATE", "enforce")
    assert dispatch_mod.claim_gate() == "enforce"
    monkeypatch.setenv("MW_CLAIM_GATE", "  ")
    assert dispatch_mod.claim_gate() == "advisory"
    capsys.readouterr()
    monkeypatch.delenv("MW_CLAIM_GATE")
    assert dispatch_mod.claim_gate() == dispatch_mod.CLAIM_GATE_DEFAULT

    # Fail-open on the dispatch path: an invalid value is diagnostic only.
    root = _make_project(tmp_path / "project")
    _write_card(root, "T-50", _card_text(_row("C-01", "grep")))
    monkeypatch.setenv("MW_CLAIM_GATE", "bogus")
    result = _dispatch(root, "T-50")
    assert result.ok and result.row_verified, result.reason
    assert "claim_gate=bogus fallback=advisory" in capsys.readouterr().err
    _verify("claim_gate", fallback=dispatch_mod.CLAIM_GATE_DEFAULT, dispatched="True")


# ── constants (the T-06 parity lock reads these verbatim) ───────────────────

def test_python_claims_constants_shape() -> None:
    assert dispatch_mod.CLAIM_TYPES == ["cmd", "grep", "struct", "manual"]
    assert dispatch_mod.UNVERIFIED_REASONS == [
        "budget", "no-access", "not-found", "ambiguous", "environment",
        "out-of-scope", "awaiting-input",
    ]
    assert dispatch_mod.CLAIM_GATE_DEFAULT == "advisory"
    assert dispatch_mod.CLAIM_BUDGET == {
        "perClaim": 6,
        "callCap": 30,
        "hardCap": 35,
        "claimByteCap": 65536,
        "byteCapMax": 393216,
    }
