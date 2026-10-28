"""Tests for ``autopilot/task_graph.py`` (key mw-dynamic-concurrency, card T-C-I01).

Covers the parser (card header region + all real declaration forms), V1-V7
validation, the numeric-core join and the dependency frontier, plus a real-card
corpus sweep.

Real-corpus measurement (this run, repo ``.agenticdoc``):

    cards_total       = 445
    cards_with_line   = 150   (bullet deps 12 / bullet 依赖 51 / bare 6 / embedded 81)
    cards_without_line= 295
    dep tokens        = 201   (bindings 180 / ambiguous 10 / unsupported 4 / unknown 7)
    max deps line     = 9

These drift as keys are added (the upstream design probe of 2026-10-14 measured
434 / 117 / 317 and 146 tokens with 125 unique + 10 ambiguous + 11 prose), so
the assertions below encode the measured magnitude with headroom instead of
the historical exact numbers.
"""

from __future__ import annotations

import ast
import pathlib
import textwrap

import pytest

from autopilot import task_graph

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
CARDS_ROOT = REPO_ROOT / ".agenticdoc"

# Lower bounds derived from the measured corpus; headroom absorbs corpus growth.
MIN_CARDS = 400
MIN_WITH_LINE = 100
MIN_WITHOUT_LINE = 250
MIN_BINDINGS = 120
MIN_AMBIGUOUS = 8
MIN_UNSUPPORTED = 2


def card(text: str) -> str:
    """Dedent a synthetic card body."""
    return textwrap.dedent(text).lstrip("\n")


# ---------------------------------------------------------------------------
# parse_card_deps
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    ["-", "—", "无", "none", "None", "无 · 预估: 30-45min", "无（本卡是起点）", ""],
)
def test_parse_no_dependency_forms(value):
    text = card(
        f"""
        # T-01 x

        - 依赖: {value}

        ## 正文
        prose
        """
    )
    assert task_graph.parse_card_deps(text) == []


def test_parse_missing_line_is_no_dependency():
    text = card(
        """
        # T-01 x

        - key: some-key
        - ac_refs: AC-001

        ## 正文
        """
    )
    assert task_graph.parse_card_deps(text) == []


@pytest.mark.parametrize(
    "line, expected",
    [
        ("- deps: T-01, T-02", ["T-01", "T-02"]),
        ("- 依赖: T-01, T-02", ["T-01", "T-02"]),
        ("deps: T-01", ["T-01"]),
        ("- 依赖：T-05", ["T-05"]),
        ("deps:T-07", ["T-07"]),
        ("- deps: [001, 002]", ["001", "002"]),
        ("- 依赖: T-01、T-02", ["T-01", "T-02"]),
        ("- 依赖: T-01,", ["T-01"]),
    ],
)
def test_parse_accepted_forms(line, expected):
    text = card(
        f"""
        # T-09 x

        {line}

        ## 正文
        """
    )
    assert task_graph.parse_card_deps(text) == expected


def test_parse_embedded_boci_form():
    text = card(
        """
        # T-05 x

        - 波次: **1** · 依赖: T-01, T-03
        - AC: AC-022

        ## 正文
        """
    )
    assert task_graph.parse_card_deps(text) == ["T-01", "T-03"]


def test_parse_drops_trailing_annotation_not_later_sections():
    text = card(
        """
        # T-03 x

        - 依赖: T-01, T-02 · 预估: 60-90min

        ## 正文
        """
    )
    assert task_graph.parse_card_deps(text) == ["T-01", "T-02"]


def test_parse_parenthesized_and_bold_annotations():
    text = card(
        """
        # T-17 x

        - 依赖: **T-15 必须先完成**（本任务要重建 dist）、T-16（adapter）

        ## 正文
        """
    )
    assert task_graph.parse_card_deps(text) == ["T-15", "T-16"]


def test_parse_slash_and_plus_are_and_separators():
    text = card(
        """
        # T-17 x

        - 依赖: T-05/T-06 + T-07

        ## 正文
        """
    )
    assert task_graph.parse_card_deps(text) == ["T-05", "T-06", "T-07"]


def test_parse_embedded_section_tail_is_not_a_dependency():
    text = card(
        """
        # T-01 x

        key: `k` · 依赖: 无（契约冻结见 plan.md） · 覆盖: VC-001,002,011,012

        ## 正文
        """
    )
    assert task_graph.parse_card_deps(text) == []


def test_parse_header_region_stops_at_body_heading():
    text = card(
        """
        # T-01 x

        ## 输入
        - 依赖: Stage 1 全部完成

        ## 正文
        """
    )
    assert task_graph.parse_card_deps(text) == []


def test_parse_header_region_stops_at_prose_line():
    text = card(
        """
        # T-01 x

        - 依赖: T-02
        Some prose paragraph without a colon
        - 依赖: T-03
        """
    )
    assert task_graph.parse_card_deps(text) == ["T-02"]


def test_parse_metadata_heading_continues_region():
    text = card(
        """
        # T-01 x

        ## 元信息
        - Stage: 3
        - 依赖: T-02
        - Agent: coding worker

        ## 交付物
        """
    )
    assert task_graph.parse_card_deps(text) == ["T-02"]


def test_parse_yaml_frontmatter():
    text = "---\ndeps: T-02, T-03\nkey: k\n---\n# T-01 x\n"
    assert task_graph.parse_card_deps(text) == ["T-02", "T-03"]


def test_parse_without_h1_scans_from_first_line():
    text = "type: coding\ncli: codex\ndeps: T-02, T-03\nstatus: pending\n\nbody\n"
    assert task_graph.parse_card_deps(text) == ["T-02", "T-03"]


def test_parse_scan_window_is_bounded():
    lines = ["# T-01 x", ""]
    lines.extend(f"- k{i}: v" for i in range(task_graph.HEADER_SCAN_LINES + 5))
    lines.append("- 依赖: T-99")
    assert task_graph.parse_card_deps("\n".join(lines)) == []


def test_parse_returns_raw_range_token_unchanged():
    text = card(
        """
        # T-14 x

        - 依赖: T-01…T-13 全部 · 预估: 60-90min
        """
    )
    assert task_graph.parse_card_deps(text) == ["T-01…T-13 全部"]


def test_deps_declaration_lines_counts_none_value():
    text = card(
        """
        # T-01 x

        - 依赖: 无

        ## 正文
        """
    )
    assert task_graph.deps_declaration_lines(text) == (3,)
    assert task_graph.parse_card_deps(text) == []


def test_deps_declaration_lines_empty_when_absent():
    assert task_graph.deps_declaration_lines("# T-01 x\n\nprose\n") == ()


# ---------------------------------------------------------------------------
# numeric_core / join_deps
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value, core",
    [
        ("T-01-x", "01"),
        ("T-1", "1"),
        ("T-001-board-params-config-errors", "001"),
        ("002-py-target-config-parity", "002"),
        ("T1-foo", "1"),
        ("packages/x/T-03-y.md", "03"),
        ("no-digits-here", ""),
        ("T-C-I01-task-graph", ""),
        ("", ""),
    ],
)
def test_numeric_core(value, core):
    assert task_graph.numeric_core(value) == core


def test_join_exact_stem_binding():
    result = task_graph.join_deps(["T-01-file-lock"], ["T-01-file-lock", "T-02-x"])
    assert result["bindings"] == {"T-01-file-lock": "T-01-file-lock"}
    assert result["ambiguous"] == {}


def test_join_numeric_core_unique_binding_and_zero_normalization():
    # ``T-1`` binds ``T-01-*``: core 1 == 01 after normalization.
    result = task_graph.join_deps(["T-1"], ["T-01-skill-dir-parity", "T-02-x"])
    assert result["bindings"] == {"T-1": "T-01-skill-dir-parity"}
    assert result["problems"] == ()


def test_join_same_core_multiple_cards_is_ambiguous():
    cards = ["T-01-file-lock", "T-01-task-protocol", "T-02-x"]
    for token in ("T-01", "T-1", "01"):
        result = task_graph.join_deps([token], cards)
        assert result["bindings"] == {}
        assert result["ambiguous"] == {token: ("T-01-file-lock", "T-01-task-protocol")}
        assert result["problems"][0]["kind"] == "deps-ambiguous"


def test_join_dangling_and_unknown_and_cross_key_and_unsupported():
    cards = ["T-01-a"]
    dangling = task_graph.join_deps(["T-99"], cards)
    assert dangling["dangling"] == ("T-99",)
    assert dangling["problems"][0]["kind"] == "deps-dangling"

    prose = task_graph.join_deps(["Stage 1 全部完成"], cards)
    assert prose["unknown"] == ("Stage 1 全部完成",)
    assert prose["problems"][0]["kind"] == "deps-unknown-id"

    for token in ("mw-b/tasks/T-2", "../other/tasks/x.md", "mw-b:T-2"):
        cross = task_graph.join_deps([token], cards)
        assert cross["cross_key"] == (token,)
        assert cross["problems"][0]["kind"] == "deps-cross-key"

    for token in ("T-01…T-13", "T-1~T-3", "T-*", "T-01...T-13"):
        unsupported = task_graph.join_deps([token], cards)
        assert unsupported["unsupported"] == (token,)
        assert unsupported["problems"][0]["kind"] == "deps-unsupported"


# ---------------------------------------------------------------------------
# find_cycle / frontier
# ---------------------------------------------------------------------------


def test_find_cycle_none_on_dag():
    assert task_graph.find_cycle({"a": ("b",), "b": ("c",), "c": ()}) is None


def test_find_cycle_detects_two_node_cycle():
    cycle = task_graph.find_cycle({"a": ("b",), "b": ("a",)})
    assert cycle is not None
    assert cycle[0] == cycle[-1]
    assert set(cycle) == {"a", "b"}


def test_find_cycle_detects_self_loop():
    assert task_graph.find_cycle({"a": ("a",)}) == ["a", "a"]


def _chain():
    # A → B → C: each card depends on the previous one.
    return {"A": (), "B": ("A",), "C": ("B",)}


def test_frontier_chain_stays_one():
    deps = _chain()
    assert task_graph.frontier(deps, set()) == ["A"]
    assert task_graph.frontier(deps, {"A"}) == ["B"]
    assert task_graph.frontier(deps, {"A", "B"}) == ["C"]
    assert task_graph.frontier(deps, {"A", "B", "C"}) == []


def test_frontier_fanout_equals_parallel_width():
    deps = {"R": (), "X": ("R",), "Y": ("R",), "Z": ("R",)}
    assert task_graph.frontier(deps, set()) == ["R"]
    assert task_graph.frontier(deps, {"R"}) == ["X", "Y", "Z"]
    assert task_graph.frontier(deps, {"R", "X"}) == ["Y", "Z"]


def test_frontier_mixed_keeps_input_order():
    deps = {"A": (), "B": ("A",), "C": ("A",), "D": ("B",), "E": ()}
    assert task_graph.frontier(deps, {"A"}) == ["B", "C", "E"]
    assert task_graph.frontier(deps, {"A", "B"}) == ["C", "D", "E"]


def test_frontier_missing_dependency_does_not_block():
    deps = {"A": ("ghost",)}
    assert task_graph.frontier(deps, set()) == ["A"]


# ---------------------------------------------------------------------------
# validate_task_graph (V1-V7)
# ---------------------------------------------------------------------------


def test_validate_clean_graph_is_serializable():
    cards = {
        "T-01-a": "# T-01 a\n\n- deps: -\n",
        "T-02-b": "# T-02 b\n\n- deps: T-01-a\n",
    }
    report = task_graph.validate_task_graph(cards)
    assert report.problems == ()
    assert report.plan_is_serializable is True
    assert report.deps_by_id == {"T-01-a": (), "T-02-b": ("T-01-a",)}


def test_validate_v1_unknown_id_has_line_and_snippet():
    cards = {"T-01-a": "# T-01 a\n\n- 依赖: 等设计冻结后再说\n"}
    report = task_graph.validate_task_graph(cards)
    assert report.plan_is_serializable is False
    problem = next(p for p in report.problems if p.kind == "deps-unknown-id")
    assert problem.line == 3
    assert problem.snippet == "- 依赖: 等设计冻结后再说"
    assert problem.token == "等设计冻结后再说"


def test_validate_v1_node_not_in_card_set():
    cards = {"T-99-x": "# T-99 x\n\n- deps: -\n"}
    report = task_graph.validate_task_graph(cards, ["T-01-a"])
    problem = next(p for p in report.problems if p.kind == "deps-unknown-id")
    assert problem.card_id == "T-99-x"
    assert problem.detail == "node not in the key card set"
    assert report.plan_is_serializable is False


def test_validate_v2_dangling():
    cards = {"T-01-a": "# T-01 a\n\n- deps: T-99\n"}
    report = task_graph.validate_task_graph(cards)
    problem = next(p for p in report.problems if p.kind == "deps-dangling")
    assert problem.token == "T-99"
    assert problem.line == 3
    assert problem.snippet == "- deps: T-99"
    assert report.plan_is_serializable is False


def test_validate_v3_cycle_reports_origin_edge():
    cards = {
        "T-01-a": "# T-01 a\n\n- deps: T-02-b\n",
        "T-02-b": "# T-02 b\n\n- deps: T-01-a\n",
    }
    report = task_graph.validate_task_graph(cards)
    problem = next(p for p in report.problems if p.kind == "deps-cycle")
    assert problem.line == 3
    assert problem.snippet == "- deps: T-02-b"
    assert "->" in problem.detail
    assert report.plan_is_serializable is False


def test_validate_v4_cross_key():
    cards = {"T-01-a": "# T-01 a\n\n- deps: ../other/tasks/T-2\n"}
    report = task_graph.validate_task_graph(cards)
    problem = next(p for p in report.problems if p.kind == "deps-cross-key")
    assert problem.line == 3
    assert problem.snippet == "- deps: ../other/tasks/T-2"
    assert report.plan_is_serializable is False


def test_validate_v5_repeated_id():
    cards = {
        "T-01-a": "# T-01 a\n\n- deps: -\n",
        "T-02-b": "# T-02 b\n\n- deps: T-1, T-01\n",
    }
    report = task_graph.validate_task_graph(cards)
    duplicates = [p for p in report.problems if p.kind == "deps-duplicate"]
    assert len(duplicates) == 1
    assert duplicates[0].line == 3
    assert report.plan_is_serializable is False


def test_validate_v5_second_declaration_line():
    cards = {"T-01-a": "# T-01 a\n\n- deps: -\n- deps: T-01-a\n"}
    report = task_graph.validate_task_graph(cards)
    dup = next(p for p in report.problems if p.kind == "deps-duplicate")
    assert dup.line == 4
    assert dup.detail == "second deps declaration line"


def test_validate_v6_self_reference():
    cards = {"T-05-mw-rag-cmd": "# T-05 x\n\n- deps: T-5\n"}
    report = task_graph.validate_task_graph(cards)
    problem = next(p for p in report.problems if p.kind == "deps-self")
    assert problem.card_id == "T-05-mw-rag-cmd"
    assert problem.line == 3
    assert report.plan_is_serializable is False


def test_validate_v7_range_is_unsupported_not_expanded():
    cards = {"T-14-x": "# T-14 x\n\n- 依赖: T-01…T-13 全部 · 预估: 60-90min\n"}
    report = task_graph.validate_task_graph(cards)
    problem = next(p for p in report.problems if p.kind == "deps-unsupported")
    assert problem.line == 3
    assert problem.snippet == "- 依赖: T-01…T-13 全部 · 预估: 60-90min"
    assert "…" in problem.token
    assert report.plan_is_serializable is False


def test_validate_any_problem_forces_serial_fallback():
    clean = {"T-01-a": "# T-01 a\n\n- deps: -\n"}
    assert task_graph.validate_task_graph(clean).plan_is_serializable is True
    dirty = {"T-01-a": "# T-01 a\n\n- deps: T-9\n"}
    assert task_graph.validate_task_graph(dirty).plan_is_serializable is False


def test_validate_problem_as_dict():
    cards = {"T-01-a": "# T-01 a\n\n- deps: T-99\n"}
    problem = task_graph.validate_task_graph(cards).problems[0]
    payload = problem.as_dict()
    assert set(payload) == {"kind", "card_id", "line", "snippet", "token", "detail"}
    assert payload["kind"] == "deps-dangling"


# ---------------------------------------------------------------------------
# purity / isolation guards
# ---------------------------------------------------------------------------


def test_module_imports_are_stdlib_and_isolated():
    source = pathlib.Path(task_graph.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    # A stdlib-only whitelist is also the proof that neither ``conductor`` nor
    # ``card_audit`` is imported.
    assert imported <= {"__future__", "re", "dataclasses"}
    # No file I/O in a pure module.
    assert "open(" not in source


# ---------------------------------------------------------------------------
# real-card corpus
# ---------------------------------------------------------------------------


def _load_corpus() -> dict[str, dict[str, str]]:
    if not CARDS_ROOT.is_dir():
        pytest.skip(f"card corpus not present at {CARDS_ROOT}")
    corpus: dict[str, dict[str, str]] = {}
    for key_dir in sorted(CARDS_ROOT.iterdir()):
        tasks = key_dir / "tasks"
        if not tasks.is_dir():
            continue
        cards: dict[str, str] = {}
        for path in sorted(tasks.glob("*.md")):
            if path.stem.startswith("_") or path.stem.startswith("."):
                continue
            cards[path.stem] = path.read_text(encoding="utf-8-sig", errors="replace")
        if cards:
            corpus[key_dir.name] = cards
    if not corpus:
        pytest.skip("no cards found")
    return corpus


def _corpus_stats(corpus: dict[str, dict[str, str]]) -> dict[str, int]:
    stats = {
        "cards": 0,
        "with_line": 0,
        "without_line": 0,
        "tokens": 0,
        "bindings": 0,
        "ambiguous": 0,
        "dangling": 0,
        "unknown": 0,
        "cross_key": 0,
        "unsupported": 0,
    }
    for cards in corpus.values():
        ids = list(cards)
        for text in cards.values():
            stats["cards"] += 1
            if task_graph.deps_declaration_lines(text):
                stats["with_line"] += 1
            else:
                stats["without_line"] += 1
            stats["tokens"] += len(task_graph.parse_card_deps(text))
        report = task_graph.validate_task_graph(cards, ids)
        for problem in report.problems:
            if problem.kind == "deps-ambiguous":
                stats["ambiguous"] += 1
            elif problem.kind == "deps-dangling":
                stats["dangling"] += 1
            elif problem.kind == "deps-unknown-id":
                stats["unknown"] += 1
            elif problem.kind == "deps-cross-key":
                stats["cross_key"] += 1
            elif problem.kind == "deps-unsupported":
                stats["unsupported"] += 1
        for text in cards.values():
            for token in task_graph.parse_card_deps(text):
                if task_graph.join_deps([token], ids)["bindings"]:
                    stats["bindings"] += 1
    return stats


def test_real_corpus_distribution():
    corpus = _load_corpus()
    stats = _corpus_stats(corpus)
    # Exact arithmetic invariant, then magnitude assertions with drift headroom.
    assert stats["with_line"] + stats["without_line"] == stats["cards"]
    assert stats["cards"] >= MIN_CARDS
    assert stats["with_line"] >= MIN_WITH_LINE
    assert stats["without_line"] >= MIN_WITHOUT_LINE
    assert stats["bindings"] >= MIN_BINDINGS
    assert stats["ambiguous"] >= MIN_AMBIGUOUS
    assert stats["unsupported"] >= MIN_UNSUPPORTED
    # A card either declares deps or it does not; both buckets must be real.
    assert 0 < stats["with_line"] < stats["cards"]


def test_real_corpus_max_deps_line_within_scan_window():
    corpus = _load_corpus()
    max_line = 0
    for cards in corpus.values():
        for text in cards.values():
            lines = task_graph.deps_declaration_lines(text)
            if lines:
                max_line = max(max_line, max(lines))
    assert 0 < max_line < task_graph.HEADER_SCAN_LINES


def _read_card(key: str, stem: str) -> str:
    path = CARDS_ROOT / key / "tasks" / f"{stem}.md"
    if not path.is_file():
        pytest.skip(f"card moved or removed: {path}")
    return path.read_text(encoding="utf-8-sig", errors="replace")


def _read_key_cards(key: str) -> dict[str, str]:
    tasks = CARDS_ROOT / key / "tasks"
    if not tasks.is_dir():
        pytest.skip(f"key moved or removed: {key}")
    return {
        path.stem: path.read_text(encoding="utf-8-sig", errors="replace")
        for path in sorted(tasks.glob("*.md"))
        if not path.stem.startswith(("_", "."))
    }


def test_real_card_body_dependency_is_not_read():
    # ``- 依赖: Stage 1 全部完成`` lives under ``## 输入`` in the body.
    text = _read_card("timi-gpt-pi-routing", "007-build-verify")
    assert task_graph.parse_card_deps(text) == []


def test_real_card_deps_T_1_joins_T_01_slug():
    cards = _read_key_cards("mw-rag-window-parity")
    text = _read_card("mw-rag-window-parity", "T-4-VERIFY")
    tokens = task_graph.parse_card_deps(text)
    assert tokens == ["T-1", "T-2", "T-3"]
    result = task_graph.join_deps(tokens, list(cards))
    assert result["bindings"] == {
        "T-1": "T-1-SKILL-DIR-PARITY",
        "T-2": "T-2-MW-RAG-CMD",
        "T-3": "T-3-DOCTOR-RAG-ROW",
    }
    assert result["problems"] == ()


def test_real_card_flow_list_numeric_ids_join():
    cards = _read_key_cards("mw-dual-workspace")
    text = _read_card("mw-dual-workspace", "002-py-target-config-parity")
    tokens = task_graph.parse_card_deps(text)
    assert tokens == ["001"]
    assert task_graph.join_deps(tokens, list(cards))["bindings"] == {
        "001": "001-ts-target-config"
    }


def test_real_card_range_form_is_unsupported():
    text = _read_card("mw-vision-role", "T-14-verification-closeout")
    report = task_graph.validate_task_graph({"T-14-verification-closeout": text})
    problem = next(p for p in report.problems if p.kind == "deps-unsupported")
    assert "T-01…T-13" in problem.snippet
    assert report.plan_is_serializable is False


def test_real_key_duplicate_numbering_is_ambiguous():
    cards = _read_key_cards("agent-team-loop")
    text = _read_card("agent-team-loop", "T-05-launcher")
    result = task_graph.join_deps(task_graph.parse_card_deps(text), list(cards))
    assert result["bindings"] == {}
    assert set(result["ambiguous"]) == {"T-02", "T-03", "T-04"}
